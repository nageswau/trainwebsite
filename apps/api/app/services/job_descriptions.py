"""rec-008 (DEC-SCOPE-132, spec §1-§3): a requirement's versioned JD -- numbers, versions, files, the contact rule and the output.

Functions only; nothing here commits -- the route owns the transaction. Scope and write permission are the requirement's
(services.recruiter_requirements.load_scoped / require, JD7). Logs and audit rows carry ids, versions and field names, never JD text."""

import hashlib
import logging
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JD_NUMBER_SEQ, AuditLog, CompanyContact, Job, JobDescription, User
from app.schemas import REC_JD_FIELDS
from app.services.candidates import EXTENSION, read_pdf_or_docx
from app.services.recruiter_companies import person
from app.services.recruiter_requirements import permissions
from app.services.storage import storage

logger = logging.getLogger("app.recruiter")

MAX_BYTES = 5 * 1024 * 1024  # JD5: the rec-009 resume limit
STORAGE_PREFIX = "job-descriptions"
FILE_COLUMNS = ("storage_key", "file_name", "content_type", "size_bytes")
CONTACT_INVALID = "Choose an active contact of this company"


async def read_file(file) -> tuple[bytes, str, str | None]:
    return await read_pdf_or_docx(file, MAX_BYTES, "The JD file must be at most 5 MB")


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("job_description_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; only this module's keys. A failure leaves a logged orphan."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("job_description_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def file_bytes(jd: JobDescription) -> bytes:
    try:
        return storage.read_bytes(jd.storage_key)
    except FileNotFoundError:
        logger.warning("job_description_file_missing", extra={"extra_fields": {"key_digest": _digest(jd.storage_key)}})
        raise HTTPException(404, "JD file not found") from None


async def current(db: AsyncSession, job_id: UUID) -> JobDescription | None:
    return await db.scalar(select(JobDescription).where(JobDescription.job_id == job_id, JobDescription.is_current.is_(True)))


def fields_from_requirement(job: Job) -> dict:
    """JD4: a first upload's fields, from the requirement."""
    return {
        "role": job.title, "location": job.location, "qualification": job.qualification, "openings": job.vacancies,
        "closing_date": job.closes_on, "description": job.description or None,
    }


async def check_contact(db: AsyncSession, job: Job, contact_id: UUID | None, kept: UUID | None) -> None:
    """An active contact of the requirement's company when set or changed (FOR SHARE); keeping a since-deactivated one is allowed."""
    if contact_id is None or contact_id == kept:
        return
    contact = await db.scalar(select(CompanyContact).where(CompanyContact.id == contact_id).with_for_update(read=True))
    if contact is None or contact.company_id != job.company_id or not contact.active:
        raise HTTPException(422, CONTACT_INVALID)


async def add_version(db: AsyncSession, user: User, job: Job, fields: dict | None, file: dict | None) -> JobDescription:
    """JD1/JD4: the caller holds the requirement's row lock, so versions are numbered one writer at a time. `fields` None = carry the
    current fields (an upload); `file` None = carry the current file (a create or edit)."""
    previous = await current(db, job.id)
    if fields is None:
        fields = {k: getattr(previous, k) for k in REC_JD_FIELDS} if previous else fields_from_requirement(job)
    if file is None:
        file = {k: getattr(previous, k) for k in FILE_COLUMNS} if previous else {}
    last = await db.scalar(select(func.max(JobDescription.version)).where(JobDescription.job_id == job.id))
    number = previous.jd_number if previous else f"JD-{await db.scalar(select(JD_NUMBER_SEQ.next_value())):06d}"
    if previous:
        previous.is_current = False
        await db.flush()  # the partial unique index sees the old current row cleared before the new one arrives
    jd = JobDescription(job_id=job.id, jd_number=number, version=(last or 0) + 1, is_current=True, created_by_user_id=user.id, **fields, **file)
    db.add(jd)
    await db.flush()
    return jd


def _version_out(jd: JobDescription, job: Job, contacts: dict, people: dict) -> dict:
    contact = contacts.get(jd.contact_id)
    return {
        "version": jd.version,
        "is_current": jd.is_current,
        **{k: getattr(jd, k) for k in REC_JD_FIELDS if k != "contact_id"},
        "contact": {"id": contact.id, "name": contact.name, "active": contact.active} if contact else None,
        "closing_date_differs": jd.closing_date is not None and jd.closing_date != job.closes_on,  # JD8
        "file": {"name": jd.file_name, "content_type": jd.content_type, "size_bytes": jd.size_bytes} if jd.storage_key else None,
        "created_by": person(people.get(jd.created_by_user_id)),
        "created_at": jd.created_at,
    }


async def jd_out(db: AsyncSession, user: User, job: Job) -> dict:
    """GET's shape, returned by every write: the versions newest first (the first is current)."""
    versions = (await db.scalars(select(JobDescription).where(JobDescription.job_id == job.id).order_by(JobDescription.version.desc()))).all()
    contact_ids = {v.contact_id for v in versions} - {None}
    user_ids = {v.created_by_user_id for v in versions}
    contacts = {c.id: c for c in (await db.scalars(select(CompanyContact).where(CompanyContact.id.in_(contact_ids)))).all()} if contact_ids else {}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()} if user_ids else {}
    return {
        "jd_number": versions[0].jd_number if versions else None,
        "versions": [_version_out(v, job, contacts, people) for v in versions],
        "can_edit": permissions(user, job)["can_edit"],
    }


def download_name(jd: JobDescription) -> str:
    return f"{jd.jd_number}-v{jd.version}.{EXTENSION.get(jd.content_type, 'bin')}"


def audit(db: AsyncSession, user: User, action: str, job: Job, metadata: dict) -> None:
    """Same transaction as the write (fail closed); entity = the requirement, so its audit trail lists its JD versions."""
    db.add(AuditLog(user_id=user.id, action=f"job_description.{action}", entity_type="job", entity_id=str(job.id), metadata_json=metadata))


def log(event: str, user: User, job: Job, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), **extra}})
