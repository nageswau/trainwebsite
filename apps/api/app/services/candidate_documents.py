"""hrc-015 (DEC-SCOPE-379 D4/D6/D7/D8): candidate documents (certificates and others), document requests, and the short-lived signed
links every resume and document download or preview goes through.

Roles, the pool, the archived rule and the audit/log helpers are rec-009's (services/candidates). Functions only; nothing here commits --
the route owns the transaction. Audit rows and logs carry ids and types, never file names. The candidate's own view (D8) never names
staff: an uploader is "you" or "placement_team"."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CANDIDATE_DOCUMENT_TYPES, Candidate, CandidateDocument, CandidateDocumentRequest, User
from app.services import candidate_previews as previews
from app.services import candidates as svc
from app.services.storage import storage
from app.services.telecaller import _parse

INDIA = ZoneInfo("Asia/Kolkata")
LINK_TTL_SECONDS = 300  # D4

ACCEPTED = frozenset({svc.PDF, svc.DOC, svc.DOCX, svc.PNG, svc.JPEG})
NOT_FOUND = "Document not found"
REQUEST_NOT_FOUND = "Document request not found"
NOT_PENDING = "This request is no longer pending"
DUPLICATE_REQUEST = "A request for this document type is already pending"
DocumentType = Literal[CANDIDATE_DOCUMENT_TYPES]
REQUEST_LABELS = {"document_type": "Document type", "note": "Note", "due_date": "Due date"}


class DocumentRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: DocumentType
    note: str | None = Field(None, max_length=500)
    due_date: date | None = None

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("due_date")
    @classmethod
    def _not_past(cls, value: date | None) -> date | None:
        if value is not None and value < datetime.now(UTC).astimezone(INDIA).date():
            raise ValueError("The due date must be today or later")
        return value


def parse_request(payload) -> DocumentRequestIn:
    return _parse(DocumentRequestIn, payload, "The request body must be an object", REQUEST_LABELS)


def parse_form(document_type: str | None, title: str | None, request_id: str | None) -> tuple[str, str | None, UUID | None]:
    """The multipart fields of an upload; 422 with one sentence."""
    if document_type not in CANDIDATE_DOCUMENT_TYPES:
        raise HTTPException(422, "Choose a document type")
    title = (title or "").strip() or None
    if title and len(title) > 120:
        raise HTTPException(422, "Title must be at most 120 characters")
    if document_type == "other" and not title:
        raise HTTPException(422, "Give the document a title")
    try:
        request = UUID(request_id) if request_id else None
    except ValueError:
        raise HTTPException(422, "Document request is not valid") from None
    return document_type, title, request


async def read_document(file: UploadFile) -> tuple[bytes, str, str | None]:
    return await svc.read_upload(file, svc.MAX_RESUME_BYTES, "The document must be at most 5 MB", ACCEPTED, "Upload a PDF, DOC, DOCX, PNG or JPEG file")


async def upload(
    db: AsyncSession, actor: User, file: UploadFile, fields: tuple[str | None, str | None, str | None], lock_candidate: Callable[[], Awaitable[Candidate]]
) -> tuple[Candidate, CandidateDocument]:
    """One upload, staff's or the candidate's own (D8): validate, store the file before the row lock, then lock the candidate (the caller's
    loader applies its rules) and write. The one exception to "nothing here commits": the stored file is discarded when the transaction
    fails, and the preview is queued only after the commit."""
    document_type, title, request_id = parse_form(*fields)
    data, content_type, file_name = await read_document(file)
    key = svc.store(data, content_type, svc.DOCUMENT_PREFIX)
    try:
        candidate = await lock_candidate()
        row = await add_document(
            db, actor, candidate, document_type=document_type, title=title, request_id=request_id, key=key, content_type=content_type,
            file_name=file_name, size=len(data),
        )  # fmt: skip
        await db.commit()
    except Exception:
        await db.rollback()
        svc.discard(key)
        raise
    if row.preview_status:
        previews.enqueue("document", row.id)
    svc.log("candidate_document_uploaded", actor, candidate, document_id=str(row.id), document_type=document_type)
    return candidate, row


# --- writes --------------------------------------------------------------------------------------------------------------------------
async def add_document(
    db: AsyncSession, actor: User, candidate: Candidate, *, document_type: str, title: str | None, request_id: UUID | None,
    key: str, content_type: str, file_name: str | None, size: int,
) -> CandidateDocument:  # fmt: skip
    """The candidate row is locked by the caller. A request must be this candidate's, pending and of the same type; it becomes received
    in the same transaction (the unique request_id is the database-level guard against two concurrent uploads)."""
    request = None
    if request_id is not None:
        request = await db.scalar(select(CandidateDocumentRequest).where(CandidateDocumentRequest.id == request_id, CandidateDocumentRequest.candidate_id == candidate.id).with_for_update())
        if request is None:
            raise HTTPException(404, REQUEST_NOT_FOUND)
        if request.status != "pending":
            raise HTTPException(409, NOT_PENDING)
        if request.document_type != document_type:
            raise HTTPException(422, "The document type must match the request")
        request.status, request.received_at = "received", datetime.now(UTC)
    row = CandidateDocument(
        candidate_id=candidate.id, document_type=document_type, title=title, storage_key=key, content_type=content_type, file_name=file_name,
        size_bytes=size, preview_status=previews.initial_status(content_type), request_id=request.id if request else None,
        uploaded_by_user_id=actor.id,
    )  # fmt: skip
    db.add(row)
    await db.flush()
    svc.audit(db, actor, "document_upload", candidate, {
        "document_id": str(row.id), "document_type": document_type, "content_type": content_type, "size_bytes": size,
        "request_id": str(request.id) if request else None, "role": actor.role,
    })  # fmt: skip
    return row


async def add_request(db: AsyncSession, actor: User, candidate: Candidate, body: DocumentRequestIn) -> CandidateDocumentRequest:
    pending = await db.scalar(
        select(CandidateDocumentRequest.id).where(
            CandidateDocumentRequest.candidate_id == candidate.id, CandidateDocumentRequest.document_type == body.document_type,
            CandidateDocumentRequest.status == "pending",
        )
    )  # fmt: skip
    if pending:
        raise HTTPException(409, DUPLICATE_REQUEST)
    row = CandidateDocumentRequest(
        candidate_id=candidate.id, document_type=body.document_type, note=body.note, due_date=body.due_date, status="pending",
        requested_by_user_id=actor.id,
    )  # fmt: skip
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:  # a concurrent request of the same type won the partial unique index
        raise HTTPException(409, DUPLICATE_REQUEST) from None
    svc.audit(db, actor, "document_request", candidate, {"request_id": str(row.id), "document_type": body.document_type})
    return row


async def cancel_request(db: AsyncSession, actor: User, candidate: Candidate, request_id: UUID) -> CandidateDocumentRequest:
    row = await db.scalar(select(CandidateDocumentRequest).where(CandidateDocumentRequest.id == request_id, CandidateDocumentRequest.candidate_id == candidate.id).with_for_update())
    if row is None:
        raise HTTPException(404, REQUEST_NOT_FOUND)
    if row.status != "pending":
        raise HTTPException(409, NOT_PENDING)
    row.status, row.cancelled_at, row.cancelled_by_user_id = "cancelled", datetime.now(UTC), actor.id
    svc.audit(db, actor, "document_request_cancel", candidate, {"request_id": str(row.id), "document_type": row.document_type})
    return row


# --- reads and links -----------------------------------------------------------------------------------------------------------------
async def load_document(db: AsyncSession, candidate: Candidate, document_id: UUID) -> CandidateDocument:
    row = await db.scalar(select(CandidateDocument).where(CandidateDocument.id == document_id, CandidateDocument.candidate_id == candidate.id))
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row


def _uploader(row: CandidateDocument, people: dict, viewer: User | None) -> dict | str | None:
    if viewer is not None:  # the candidate's own view
        return "you" if row.uploaded_by_user_id == viewer.id else "placement_team"
    person = people.get(row.uploaded_by_user_id)
    return {"id": person.id, "full_name": person.full_name} if person else None


def document_out(row: CandidateDocument, people: dict, viewer: User | None = None) -> dict:
    return {
        "id": row.id, "document_type": row.document_type, "title": row.title, "file_name": row.file_name, "content_type": row.content_type,
        "size_bytes": row.size_bytes, "preview_status": row.preview_status, "request_id": row.request_id,
        "uploaded_by": _uploader(row, people, viewer), "created_at": row.created_at,
    }  # fmt: skip


def request_out(row: CandidateDocumentRequest, document_id: UUID | None, people: dict, viewer: User | None = None) -> dict:
    out = {
        "id": row.id, "document_type": row.document_type, "note": row.note, "due_date": row.due_date, "status": row.status,
        "created_at": row.created_at, "received_at": row.received_at, "cancelled_at": row.cancelled_at, "document_id": document_id,
    }  # fmt: skip
    if viewer is None:
        person = people.get(row.requested_by_user_id)
        out["requested_by"] = {"id": person.id, "full_name": person.full_name} if person else None
    return out


async def listing(db: AsyncSession, candidate: Candidate, viewer: User | None = None) -> dict:
    """Documents newest first; requests pending first, then newest first. The candidate's own view drops cancelled requests."""
    documents = (await db.scalars(select(CandidateDocument).where(CandidateDocument.candidate_id == candidate.id).order_by(CandidateDocument.created_at.desc()))).all()
    stmt = select(CandidateDocumentRequest).where(CandidateDocumentRequest.candidate_id == candidate.id)
    if viewer is not None:
        stmt = stmt.where(CandidateDocumentRequest.status != "cancelled")
    requests = (await db.scalars(stmt.order_by(CandidateDocumentRequest.created_at.desc()))).all()
    requests = sorted(requests, key=lambda r: r.status != "pending")
    ids = {d.uploaded_by_user_id for d in documents} | {r.requested_by_user_id for r in requests}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids and viewer is None else {}
    fulfilled = {d.request_id: d.id for d in documents if d.request_id}
    return {
        "documents": [document_out(d, people, viewer) for d in documents],
        "requests": [request_out(r, fulfilled.get(r.id), people, viewer) for r in requests],
    }


async def link(db: AsyncSession, kind: str, row, mode: str, filename_stem: str) -> dict:
    """A 300 s signed link (D4). Preview serves the file itself (PDF, image) or the ready rendition (409 / 422 otherwise)."""
    if mode == "preview":
        key, content_type = await previews.target(db, kind, row)
    else:
        key, content_type = row.storage_key, row.content_type
    filename = f"{filename_stem}.{svc.EXTENSION.get(content_type, 'bin')}"
    url = storage.presign_download(key, filename=filename, content_type=content_type, inline=mode == "preview", ttl=LINK_TTL_SECONDS)
    return {"url": url, "expires_in": LINK_TTL_SECONDS}


async def own_candidate(db: AsyncSession, user: User, *, lock: bool = False) -> Candidate | None:
    """D8: the caller's own candidate row while it is in the pool (opted in, not archived)."""
    stmt = select(Candidate).where(Candidate.user_id == user.id, Candidate.opted_in.is_(True), Candidate.archived_at.is_(None))
    return await db.scalar(stmt.with_for_update() if lock else stmt)
