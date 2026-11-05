"""pob-003 (DEC-SCOPE-406 D6-D8): a company's document store -- rules, storage, audit and output (the rec-030 contract-document pattern).

Functions only; nothing here commits -- the route owns the transaction. Every read goes through `recruiter_companies.caller_scope` (out of
scope = 404, as an unknown id); uploads need the company's `can_edit`. A recruitment agreement is signed client terms, so it follows
pob-001's `commercials.client` grant (view to download, effective edit to upload); that one exists is not a term, so it is always listed.
Audit metadata and logs carry ids, kinds, content types and sizes only -- never the file name or the storage key."""

import hashlib
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Company, CompanyDocument, RecruiterMeeting, User
from app.services import recruiter_companies as companies
from app.services import recruiter_contracts as contracts
from app.services.agent_orgs import retry_after
from app.services.storage import storage

AGREEMENT = "recruitment_agreement"
STORAGE_PREFIX = "company-documents"
UPLOAD_ACTION = "recruiter_company_document.uploaded"
UPLOAD_LIMIT = 20  # per user per rolling hour (the rec-030 budget)
UPLOAD_WINDOW = timedelta(hours=1)
MAX_PER_COMPANY = 200  # bounds the store; uploads past it are 409
THROTTLED = "Too many uploads. Try again later."
FULL = "This company already has the maximum number of documents"
NOT_FOUND = "Document not found"
MEETING_INVALID = "Choose a meeting of this company"
MISSING = "The file is no longer available"

logger = logging.getLogger("app.recruiter")


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    storage.write_bytes(key, data, content_type)
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit. A failure leaves a logged orphan."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("recruiter_company_document_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


async def upload_wait(db: AsyncSession, user: User) -> int:
    """Seconds before the caller may upload again (their audit rows in the last hour; shared by every API instance)."""
    at = contracts.now()
    stmt = (
        select(AuditLog.created_at)
        .where(AuditLog.user_id == user.id, AuditLog.action == UPLOAD_ACTION, AuditLog.created_at > at - UPLOAD_WINDOW)
        .order_by(AuditLog.created_at.desc())
        .limit(UPLOAD_LIMIT)
    )
    return retry_after(list((await db.scalars(stmt)).all()), UPLOAD_LIMIT, at, UPLOAD_WINDOW)


async def check_upload(db: AsyncSession, user: User, company: Company, kind: str, meeting_id: UUID | None) -> None:
    """Under the company lock: the agreement grant (403), the meeting (422), the per-company cap (409), the hourly budget (429)."""
    if kind == AGREEMENT:
        await contracts.require_terms(db, user, "company_document_upload", edit=True)
    if meeting_id is not None and not await db.scalar(select(RecruiterMeeting.id).where(RecruiterMeeting.id == meeting_id, RecruiterMeeting.company_id == company.id)):
        raise HTTPException(422, MEETING_INVALID)
    if (await db.scalar(select(func.count()).select_from(CompanyDocument).where(CompanyDocument.company_id == company.id)) or 0) >= MAX_PER_COMPANY:
        raise HTTPException(409, FULL)
    wait = await upload_wait(db, user)
    if wait:
        log("recruiter_company_document_throttled", user, company.id, wait_seconds=wait)
        raise HTTPException(429, THROTTLED, headers={"Retry-After": str(wait)})


async def load_scoped(db: AsyncSession, user: User, document_id: UUID) -> tuple[CompanyDocument, Company]:
    """A document through its company's read scope; unknown and out of scope give the same 404 (IDOR)."""
    stmt = select(CompanyDocument, Company).join(Company, Company.id == CompanyDocument.company_id)
    row = (await db.execute(stmt.where(CompanyDocument.id == document_id, *await companies.caller_scope(db, user)))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


def read(document: CompanyDocument) -> bytes:
    try:
        return storage.read_bytes(document.storage_key)
    except FileNotFoundError:
        logger.warning("recruiter_company_document_missing", extra={"extra_fields": {"document_id": str(document.id), "key_digest": _digest(document.storage_key)}})
        raise HTTPException(404, MISSING) from None


def audit(db: AsyncSession, user: User, action: str, document: CompanyDocument, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed)."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_company_document.{action}", entity_type="company_document", entity_id=str(document.id),
                    metadata_json={"company_id": str(document.company_id), "kind": document.kind, **(metadata or {})}))  # fmt: skip


def log(event: str, user: User, company_id, **extra) -> None:
    companies.log(event, user, company_id, **extra)


def _rows(where: list):
    """The rows with their uploader and meeting in one query (no N+1), newest first."""
    return (
        select(CompanyDocument, User, RecruiterMeeting)
        .join(User, User.id == CompanyDocument.uploaded_by_user_id)
        .outerjoin(RecruiterMeeting, RecruiterMeeting.id == CompanyDocument.meeting_id)
        .where(*where)
        .order_by(CompanyDocument.created_at.desc(), CompanyDocument.id.desc())
    )


async def page(db: AsyncSession, user: User, company: Company, kind: str | None, meeting_id: UUID | None, limit: int, offset: int) -> dict:
    where = [CompanyDocument.company_id == company.id]
    if kind:
        where.append(CompanyDocument.kind == kind)
    if meeting_id:
        where.append(CompanyDocument.meeting_id == meeting_id)
    total = await db.scalar(select(func.count()).select_from(CompanyDocument).where(*where))
    view, edit = await contracts.commercial_access(db, user)
    rows = (await db.execute(_rows(where).limit(limit).offset(offset))).all()
    can_upload = companies.permissions(user, company)["can_edit"]
    return {
        "items": [out(d, uploader, meeting, view) for d, uploader, meeting in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "can_upload": can_upload,
        "can_upload_agreement": can_upload and edit,
    }


async def one(db: AsyncSession, user: User, document_id: UUID) -> dict:
    document, uploader, meeting = (await db.execute(_rows([CompanyDocument.id == document_id]))).one()
    return out(document, uploader, meeting, await contracts.sees_commercials(db, user))


def out(document: CompanyDocument, uploader: User, meeting: RecruiterMeeting | None, sees_commercials: bool) -> dict:
    return {
        "id": document.id,
        "kind": document.kind,
        "name": document.name,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "meeting": {"id": meeting.id, "code": meeting.meeting_code, "starts_at": meeting.starts_at} if meeting else None,
        "uploaded_by": companies.person(uploader),
        "created_at": document.created_at,
        "can_download": sees_commercials or document.kind != AGREEMENT,
    }
