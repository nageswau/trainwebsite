"""rec-009 (DEC-SCOPE-122, spec §4-§5): the candidate master -- who may read and write it, the pool filter, the Q-07 duplicate block,
codes, resume files and the output shapes.

Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows carry ids and field names, never a name,
mobile or email."""

import hashlib
import io
import logging
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CANDIDATE_CODE_SEQ, AuditLog, Candidate, CandidateResume, RecCandidateSource, User
from app.notifications.phone import normalise_phone
from app.schemas import NO_CONTACT
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.storage import storage

logger = logging.getLogger("app.candidates")

WRITERS = frozenset({ROLE, MANAGER_ROLE, "super_admin"})  # R11: every recruiter edits the whole pool
READERS = WRITERS | {"hr_team"}  # the backlog's rec-009 roles line: hr_team reads
NOT_FOUND = "Candidate not found"
ARCHIVED = "Restore this candidate first"
DUPLICATE = "This person is already a candidate"
UNIQUE_INDEXES = ("uq_candidates_mobile", "uq_candidates_email")
MATCH_LIMIT = 5
# Q-09 (recommended default): PDF or DOCX, judged by the bytes, at most 5 MB (the /public/career-upload limit).
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXTENSION = {PDF: "pdf", DOCX: "docx"}
MAX_RESUME_BYTES = 5 * 1024 * 1024
STORAGE_PREFIX = "candidate-resumes"


def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view candidates")


def require_writer(user: User) -> None:
    if user.role not in WRITERS:
        raise HTTPException(403, "Your role cannot change candidates")


def pool_filter() -> list:
    """External candidates (no login) and students who opted in (rec-010). Backfilled students who have not opted in never surface."""
    return [or_(Candidate.user_id.is_(None), Candidate.opted_in.is_(True))]


async def load(db: AsyncSession, candidate_id: UUID, *, lock: bool = False) -> Candidate:
    stmt = select(Candidate).where(Candidate.id == candidate_id, *pool_filter())
    candidate = await db.scalar(stmt.with_for_update() if lock else stmt)
    if candidate is None:
        raise HTTPException(404, NOT_FOUND)
    return candidate


async def next_code(db: AsyncSession) -> str:
    return f"CAN-{await db.scalar(select(CANDIDATE_CODE_SEQ.next_value())):06d}"


async def active_source(db: AsyncSession, source_id: UUID) -> RecCandidateSource:
    """FOR SHARE: a concurrent deactivation of this source waits for the candidate's commit (the tel-002 P4 rule)."""
    source = await db.scalar(select(RecCandidateSource).where(RecCandidateSource.id == source_id).with_for_update(read=True))
    if source is None or not source.active:
        raise HTTPException(422, "Choose an active candidate source")
    return source


def keys(mobile: str | None, email: str | None) -> tuple[str | None, str | None]:
    """Q-07's match keys: the E.164 mobile (None when unparseable) and the lower-cased email."""
    return normalise_phone(mobile), (email.strip().lower() or None) if email else None


async def find_matches(db: AsyncSession, mobile_key: str | None, email_key: str | None, exclude_id: UUID | None = None) -> list[dict]:
    """Every candidate with the mobile or the email, archived ones too (both indexed), oldest first. No contact data is returned."""
    conditions = []
    if mobile_key:
        conditions.append(Candidate.mobile_normalized == mobile_key)
    if email_key:
        conditions.append(func.lower(Candidate.email) == email_key)
    if not conditions:
        return []
    stmt = select(Candidate, RecCandidateSource.name).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Candidate.id != exclude_id)
    rows = (await db.execute(stmt.order_by(Candidate.created_at, Candidate.id).limit(MATCH_LIMIT))).all()
    return [
        {
            # str(): an HTTPException detail is not run through FastAPI's JSON encoder, so a UUID would fail to serialise.
            "id": str(c.id),
            "candidate_code": c.candidate_code,
            "name": c.name,
            "source_name": source_name,
            "status": c.status,
            "archived": c.archived_at is not None,
            "matched_on": [k for k, hit in (("mobile", mobile_key and c.mobile_normalized == mobile_key), ("email", email_key and (c.email or "").lower() == email_key)) if hit],
        }
        for c, source_name in rows
    ]


def duplicate_conflict(matches: list[dict]) -> HTTPException:
    return HTTPException(409, {"message": DUPLICATE, "code": "duplicate_candidate", "matches": matches})


async def block_duplicates(db: AsyncSession, candidate: Candidate) -> None:
    """Before the write: no autoflush, so an edit's pending change never reaches the unique index ahead of the friendly 409."""
    with db.no_autoflush:
        matches = await find_matches(db, candidate.mobile_normalized, candidate.email, exclude_id=candidate.id)
    if matches:
        raise duplicate_conflict(matches)


async def flush_candidate(db: AsyncSession, candidate: Candidate) -> None:
    """The unique indexes decide a duplicate under a race: the transaction rolls back and the caller gets the same 409 panel."""
    mobile_key, email_key, own_id = candidate.mobile_normalized, candidate.email, candidate.id
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if any(index in str(exc.orig) for index in UNIQUE_INDEXES):
            raise duplicate_conflict(await find_matches(db, mobile_key, email_key, exclude_id=own_id)) from None
        raise


def apply_fields(candidate: Candidate, values: dict) -> list[str]:
    """Set each sent field (the schema already trimmed them and lower-cased the email); returns the names that changed (the audit
    form). The mobile's match key follows the mobile."""
    changed = []
    for key, value in values.items():
        if getattr(candidate, key) != value:
            setattr(candidate, key, value)
            changed.append(key)
    if "mobile" in changed:
        candidate.mobile_normalized = normalise_phone(candidate.mobile)
    if candidate.mobile is None and candidate.email is None:
        raise HTTPException(422, NO_CONTACT)
    return sorted(changed)


def audit(db: AsyncSession, user: User, action: str, candidate: Candidate, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"candidate.{action}", entity_type="candidates", entity_id=str(candidate.id), metadata_json=metadata))


def log(event: str, user: User, candidate: Candidate, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "candidate_id": str(candidate.id), **extra}})


# --- resumes ---------------------------------------------------------------------------------------------------------------------
def _is_docx(data: bytes) -> bool:
    """A DOCX is a ZIP with a word/document.xml part; only the central directory is read, nothing is extracted."""
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


async def read_resume(file: UploadFile) -> tuple[bytes, str, str | None]:
    """The type is decided by the bytes, never by the name or the client's Content-Type. Returns (bytes, content type, display name)."""
    data = await file.read(MAX_RESUME_BYTES + 1)
    if not data:
        raise HTTPException(422, "The file is empty")
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(413, "The resume must be at most 5 MB")
    content_type = PDF if data.startswith(b"%PDF-") else DOCX if _is_docx(data) else None
    if content_type is None:
        raise HTTPException(415, "Upload a PDF or DOCX file")
    return data, content_type, Path(file.filename or "").name[:255] or None


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("candidate_resume_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; only this module's keys. A failure leaves a logged orphan."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("candidate_resume_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read_file(resume: CandidateResume) -> bytes:
    try:
        return storage.read_bytes(resume.storage_key)
    except FileNotFoundError:
        logger.warning("candidate_resume_missing", extra={"extra_fields": {"key_digest": _digest(resume.storage_key)}})
        raise HTTPException(404, "Resume file not found") from None


# --- output ----------------------------------------------------------------------------------------------------------------------
def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


def item_out(candidate: Candidate, source: RecCandidateSource) -> dict:
    return {
        "id": candidate.id,
        "candidate_code": candidate.candidate_code,
        "name": candidate.name,
        "location": candidate.location,
        "experience_months": candidate.experience_months,
        "preferred_role": candidate.preferred_role,
        "source": {"id": source.id, "name": source.name, "active": source.active},
        "source_detail": candidate.source_detail,
        "status": candidate.status,
        "archived": candidate.archived_at is not None,
        "created_at": candidate.created_at,
    }


DETAIL_FIELDS = (
    "mobile",
    "email",
    "qualification",
    "college",
    "passing_year",
    "current_company",
    "current_salary",
    "expected_salary",
    "notice_days",
    "preferred_locations",
    "linkedin",
    "archived_at",
    "updated_at",
)


async def detail_out(db: AsyncSession, user: User, candidate: Candidate) -> dict:
    """Every field, the people, and the resume versions newest first (the first one is current)."""
    await db.refresh(candidate)
    source = await db.get(RecCandidateSource, candidate.source_id)
    ids = {candidate.created_by_user_id, candidate.updated_by_user_id} - {None}
    resumes = (
        await db.execute(
            select(CandidateResume, User).outerjoin(User, User.id == CandidateResume.uploaded_by_user_id).where(CandidateResume.candidate_id == candidate.id).order_by(CandidateResume.version.desc())
        )
    ).all()
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}
    return {
        **item_out(candidate, source),
        **{field: getattr(candidate, field) for field in DETAIL_FIELDS},
        "created_by": _person(people.get(candidate.created_by_user_id)),
        "updated_by": _person(people.get(candidate.updated_by_user_id)),
        "resumes": [
            {"version": r.version, "file_name": r.file_name, "content_type": r.content_type, "size_bytes": r.size_bytes, "uploaded_by": _person(uploader), "created_at": r.created_at}
            for r, uploader in resumes
        ],
        "can_edit": user.role in WRITERS,
    }
