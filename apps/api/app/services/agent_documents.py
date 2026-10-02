"""AGN-009 / DEC-SCOPE-052 -- agency documents: scope, history events, stored files, list items.

Functions only (the shape of services/agent_applications.py); write functions never commit -- the router locks, writes, audits and
commits once. Spec: docs/superpowers/specs/2026-10-02-agn-009-agent-documents-design.md.
"""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models import AgentStudent, AuditLog, DocumentEvent, DocumentRequest, OverseasApplication, StudentDocument, University, User
from app.services.agent_orgs import THROTTLE_WINDOW, org_member_ids, retry_after
from app.services.agent_students import application_scope, student_scope, visible_student_user_ids
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

logger = logging.getLogger("app.agent_documents")

# The type list itself is `schemas.AgentDocumentType` (G3); "Other" needs a label.
OTHER = "Other"
# AGN-010 (DEC-SCOPE-056 O3): uploaded by the agency against one application, never requested from a student.
OFFER_LETTER = "Offer letter"
PDF = "application/pdf"
STORAGE_PREFIX = "agent-documents"
# Per agency per rolling 24 hours (THROTTLE_WINDOW), counted from audit rows under the organisation lock (AGN-008 A14 pattern).
UPLOAD_LIMIT = 500
REQUEST_LIMIT = 200
UPLOAD_ACTIONS = ("document.upload", "document.replace")
REQUEST_ACTIONS = ("document_request.create",)
# DEC-SCOPE-044 P5: an agent never undoes a counselor's or an Overseas/Super Admin's decision.
STAFF_REVIEWER_ROLES = ("counselor", "overseas_admin", "super_admin")

ARCHIVED = "Unarchive this student first"
LABEL_REQUIRED = "Describe the document (2-80 characters) when the type is Other"
LABEL_NOT_ALLOWED = "A description is only used when the type is Other"
EMPTY_FILE = "The file is empty"
WRONG_FILE = "Upload a PDF, JPEG or PNG file"
BAD_IMAGE = "The image could not be read as a valid JPEG or PNG"
UPLOAD_THROTTLED = "Too many documents uploaded today -- try again later"
REQUEST_THROTTLED = "Too many document requests today -- try again later"


def document_scope(user: User) -> list[ColumnElement]:
    """The documents an agency member may reach. A document attached to an application follows the application (the AGN-003 review
    rule); an unattached one follows its owner -- the agency record, or the linked student's account. Staff therefore reach only
    their assigned students' documents (G4). Never compares a NULL `student_id` (`== None` would compile to IS NULL and match every
    no-login student)."""
    scoped_applications = select(OverseasApplication.id).where(*application_scope(user))
    scoped_records = select(AgentStudent.id).where(*student_scope(user))
    return [
        or_(
            and_(StudentDocument.application_id.is_not(None), StudentDocument.application_id.in_(scoped_applications)),
            and_(
                StudentDocument.application_id.is_(None),
                or_(
                    StudentDocument.agent_student_id.in_(scoped_records),
                    # The account path is for documents no agency owns (the student's own, or made before AGN-009): a student
                    # linked to two agencies must not open one agency's records to the other.
                    and_(StudentDocument.agent_student_id.is_(None), StudentDocument.student_id.in_(visible_student_user_ids(user))),
                ),
            ),
        )
    ]


async def in_scope(db: AsyncSession, user: User, document_id) -> bool:
    return bool(await db.scalar(select(StudentDocument.id).where(StudentDocument.id == document_id, *document_scope(user))))


def add_event(
    db: AsyncSession,
    *,
    event: str,
    actor: User | None,
    document: StudentDocument | None = None,
    request: DocumentRequest | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    notes: str | None = None,
    file_key: str | None = None,
) -> None:
    """One history row, in the caller's transaction (append-only; never updated)."""
    db.add(
        DocumentEvent(
            document_id=document.id if document else None,
            request_id=request.id if request else None,
            event=event,
            actor_user_id=actor.id if actor else None,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
            file_key=file_key,
        )
    )


def clean_label(document_type: str, label: str | None) -> str | None:
    """G3: "Other" needs a 2-80 character label; every other type takes none."""
    label = (label or "").strip() or None
    if document_type == OTHER:
        if label is None or not 2 <= len(label) <= 80:
            raise HTTPException(422, LABEL_REQUIRED)
        return label
    if label is not None:
        raise HTTPException(422, LABEL_NOT_ALLOWED)
    return None


async def read_upload(file: UploadFile) -> tuple[bytes, str, str | None]:
    """G8: the type is decided by the bytes, never by the name or the client's Content-Type; image metadata (EXIF GPS on a passport
    photo) is stripped. Returns (bytes, content type, display file name)."""
    data = await file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(422, EMPTY_FILE)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"The file must be at most {max(1, settings.max_upload_bytes // (1024 * 1024))} MB")
    content_type = PDF if data.startswith(b"%PDF-") else detect_image_type(data)
    if content_type is None:
        raise HTTPException(415, WRONG_FILE)
    if content_type != PDF:
        try:
            data = strip_metadata(data, content_type)
        except InvalidImage:
            raise HTTPException(422, BAD_IMAGE) from None
    name = Path(file.filename or "").name[:255] or None  # display only; never part of a storage path
    return data, content_type, name


async def wait_seconds(db: AsyncSession, user: User, actions: tuple[str, ...], limit: int) -> int:
    """Seconds before the caller's agency may do another of `actions`; 0 while under the budget. Runs under the organisation lock."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action.in_(actions), AuditLog.user_id.in_(org_member_ids(user)), AuditLog.created_at > now - THROTTLE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    return retry_after(list(recent), limit, now)


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """G7: a server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("agent_document_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit. Only keys this module generated are ever deleted; a failure leaves an
    orphan, logged by key digest (never the key)."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        logger.error("agent_document_discard_refused", extra={"extra_fields": {"key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("agent_document_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


_Account = aliased(User)
_Uploader = aliased(User)
_Reviewer = aliased(User)


def items_stmt() -> Select:
    """Documents with what a list item shows. Every join is outer, so a document with no account (or no uploader, application or
    reviewer) is never dropped."""
    return (
        select(StudentDocument, AgentStudent.full_name, _Account.full_name, _Uploader.full_name, University.name, _Reviewer.role)
        .outerjoin(AgentStudent, AgentStudent.id == StudentDocument.agent_student_id)
        .outerjoin(_Account, _Account.id == StudentDocument.student_id)
        .outerjoin(_Uploader, _Uploader.id == StudentDocument.uploaded_by_user_id)
        .outerjoin(OverseasApplication, OverseasApplication.id == StudentDocument.application_id)
        .outerjoin(University, University.id == OverseasApplication.university_id)
        .outerjoin(_Reviewer, _Reviewer.id == StudentDocument.verified_by_id)
    )


def decided_by_staff(document: StudentDocument, reviewer_role: str | None) -> bool:
    return document.verification_status != "pending" and reviewer_role in STAFF_REVIEWER_ROLES


def item(row: tuple) -> dict:
    document, record_name, account_name, uploader, university, reviewer_role = row
    return {
        "id": document.id,
        "agent_student_id": document.agent_student_id,
        "student": record_name or account_name or "Student",
        "has_login": document.student_id is not None,
        "document_type": document.document_type,
        "document_label": document.document_label,
        "verification_status": document.verification_status,
        "reviewer_notes": document.reviewer_notes,
        "application_id": document.application_id,
        "university": university,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "file_size": document.file_size,
        "uploaded_by": uploader,
        "fulfils_request_id": document.fulfils_request_id,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        # G6: only the agency's own uploads, and never over a counselor's or admin's decision (P5).
        "replaceable": document.agent_student_id is not None and not decided_by_staff(document, reviewer_role),
    }


async def item_by_id(db: AsyncSession, user: User, document_id) -> dict:
    row = (await db.execute(items_stmt().where(StudentDocument.id == document_id, *document_scope(user)).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, "Document not found")
    return item(tuple(row))


async def load_scoped(db: AsyncSession, user: User, document_id, *, lock: bool = False) -> StudentDocument:
    """The caller's document or 404 -- the scope is in the WHERE clause, never checked after loading."""
    stmt = select(StudentDocument).where(StudentDocument.id == document_id, *document_scope(user)).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update(of=StudentDocument) if lock else stmt)
    if row is None:
        raise HTTPException(404, "Document not found")
    return row


async def reviewer_role(db: AsyncSession, document: StudentDocument) -> str | None:
    return await db.scalar(select(User.role).where(User.id == document.verified_by_id)) if document.verified_by_id else None


_Actor = aliased(User)


async def history_page(db: AsyncSession, document: StudentDocument, *, limit: int, offset: int) -> dict:
    """AC5: the document's events in the order they happened (`seq`), plus the `requested` event of the request it fulfilled. The
    replaced file's key is never returned."""
    clause = DocumentEvent.document_id == document.id
    if document.fulfils_request_id is not None:
        clause = or_(clause, and_(DocumentEvent.request_id == document.fulfils_request_id, DocumentEvent.document_id.is_(None)))
    total = await db.scalar(select(func.count()).select_from(DocumentEvent).where(clause))
    rows = (
        await db.execute(select(DocumentEvent, _Actor.full_name).outerjoin(_Actor, _Actor.id == DocumentEvent.actor_user_id).where(clause).order_by(DocumentEvent.seq).limit(limit).offset(offset))
    ).all()
    items = [{"id": e.id, "event": e.event, "actor": actor, "from_status": e.from_status, "to_status": e.to_status, "notes": e.notes, "created_at": e.created_at} for e, actor in rows]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


def student_clause(record: AgentStudent) -> ColumnElement:
    """One student's documents: those of the agency record, plus (for a student with a login) those on the account."""
    if record.student_id is None:
        return StudentDocument.agent_student_id == record.id
    return or_(StudentDocument.agent_student_id == record.id, StudentDocument.student_id == record.student_id)


async def list_page(db: AsyncSession, user: User, *, view: str, record: AgentStudent | None, limit: int, offset: int) -> dict:
    """G9: Pending = awaiting review; Uploaded = every in-scope document. Newest first."""
    clauses = [*document_scope(user)]
    if view == "pending":
        clauses.append(StudentDocument.verification_status == "pending")
    if record is not None:
        clauses.append(student_clause(record))
    total = await db.scalar(select(func.count()).select_from(StudentDocument).where(*clauses))
    rows = (await db.execute(items_stmt().where(*clauses).order_by(StudentDocument.created_at.desc(), StudentDocument.id).limit(limit).offset(offset))).all()
    return {"items": [item(tuple(r)) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


# --- requests (G4/G5) -----------------------------------------------------------------------------------------------------------

REQUEST_EXISTS = "An open request for this document already exists"
REQUEST_CLOSED = "This request has already been fulfilled or cancelled"
REQUEST_OTHER_STUDENT = "This request is for another student"

_Requester = aliased(User)


def request_scope(user: User) -> list[ColumnElement]:
    return [DocumentRequest.agent_student_id.in_(select(AgentStudent.id).where(*student_scope(user)))]


def requests_stmt() -> Select:
    return (
        select(DocumentRequest, AgentStudent.full_name, _Account.full_name, _Requester.full_name, StudentDocument.id)
        .join(AgentStudent, AgentStudent.id == DocumentRequest.agent_student_id)
        .outerjoin(_Account, _Account.id == AgentStudent.student_id)
        .outerjoin(_Requester, _Requester.id == DocumentRequest.requested_by_user_id)
        .outerjoin(StudentDocument, StudentDocument.fulfils_request_id == DocumentRequest.id)
    )


def request_item(row: tuple) -> dict:
    request, record_name, account_name, requester, document_id = row
    return {
        "id": request.id,
        "agent_student_id": request.agent_student_id,
        "student": record_name or account_name or "Student",
        "document_type": request.document_type,
        "document_label": request.document_label,
        "note": request.note,
        "status": request.status,
        "requested_by": requester,
        "fulfilled_by_document_id": document_id,
        "created_at": request.created_at,
        "closed_at": request.closed_at,
    }


async def request_by_id(db: AsyncSession, user: User, request_id) -> dict:
    row = (await db.execute(requests_stmt().where(DocumentRequest.id == request_id, *request_scope(user)).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, "Request not found")
    return request_item(tuple(row))


async def request_page(db: AsyncSession, user: User, *, status: str, record: AgentStudent | None, limit: int, offset: int) -> dict:
    clauses = [*request_scope(user)]
    if status == "open":
        clauses.append(DocumentRequest.status == "open")
    if record is not None:
        clauses.append(DocumentRequest.agent_student_id == record.id)
    total = await db.scalar(select(func.count()).select_from(DocumentRequest).where(*clauses))
    rows = (await db.execute(requests_stmt().where(*clauses).order_by(DocumentRequest.created_at.desc(), DocumentRequest.id).limit(limit).offset(offset))).all()
    return {"items": [request_item(tuple(r)) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def load_request(db: AsyncSession, user: User, request_id, *, lock: bool = False) -> DocumentRequest:
    stmt = select(DocumentRequest).where(DocumentRequest.id == request_id, *request_scope(user)).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update(of=DocumentRequest) if lock else stmt)
    if row is None:
        raise HTTPException(404, "Request not found")
    return row


async def open_request_exists(db: AsyncSession, record: AgentStudent, document_type: str, label: str | None) -> bool:
    label_clause = DocumentRequest.document_label.is_(None) if label is None else func.lower(DocumentRequest.document_label) == label.lower()
    return bool(
        await db.scalar(select(DocumentRequest.id).where(DocumentRequest.agent_student_id == record.id, DocumentRequest.status == "open", DocumentRequest.document_type == document_type, label_clause))
    )


def close_request(request: DocumentRequest, status: str, actor: User) -> None:
    request.status, request.closed_by_user_id, request.closed_at = status, actor.id, datetime.now(UTC)
