"""itc-026 (DEC-SCOPE-350): an IT student's resume versions -- append-only, PDF / DOC / DOCX judged by the bytes, an IT Admin-configurable
size limit -- and the audit row for every upload and download (the access log).

Who (R8): the student (own), their itc-003 counselor (linked students), the IT Admin (any IT student) read and upload; HR (nehn-017
population and grants) reads `hr` versions only. Another role is 403; a student out of reach is the same 404 as a missing one.
Logs and audit rows carry ids, versions, sizes and types only -- never a file name or content."""

import logging
import zipfile
from uuid import UUID, uuid4

from fastapi import HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.portfolio_certificates import HEADERS
from app.models import STUDENT_RESUME_VISIBILITIES, AuditLog, StudentResume, StudentResumeSetting, User
from app.services import hr_reviews, hr_students, malware_scan
from app.services import it_student_profiles as profiles
from app.services.audit_changes import audit_change
from app.services.permissions import user_has_grant
from app.services.storage import storage

logger = logging.getLogger("app.student_resumes")

MB = 1024 * 1024
DEFAULT_MAX_BYTES = 5 * MB
MIN_MB, CEILING_MB = 1, 10
PDF, DOC = "application/pdf", "application/msword"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXTENSION = {PDF: "pdf", DOC: "doc", DOCX: "docx"}
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
STORAGE_PREFIX = "student-resumes"
UPLOADED, DOWNLOADED, SETTINGS_UPDATED = "it.resume.upload", "it.resume.download", "it.resume.settings_update"
SCAN_REJECTED = "it.resume.scan_rejected"  # itc-033 C5
NOT_FOUND = "Resume version not found"
ADMIN_ONLY = "Only the IT Admin can change the resume limit"


# --- scope -----------------------------------------------------------------------------------------------------------------------
async def student_for(db: AsyncSession, user: User, student_id: UUID | None, portal: str) -> User:
    """The student this request may reach on `portal` ("me", "counselor", "admin" or "hr"), else 403 / 404."""
    if portal == "me":
        return profiles.require_student(user)
    if portal == "hr":
        return await _hr_student(db, user, student_id, "view")
    return await profiles.staff_student(db, user, student_id, portal=portal)


async def _hr_student(db: AsyncSession, user: User, student_id: UUID, action: str) -> User:
    """nehn-017's gate: the `student_documents.<action>` grant, an HR role, then the HR population (404 outside it)."""
    if not await user_has_grant(db, user, "student_documents", action) or user.role not in hr_students.HR_ROLES | {"super_admin"}:
        raise HTTPException(403, "You don't have permission to view this")
    student = await db.scalar(select(User).where(User.id == student_id, User.id.in_(hr_students.population())))
    if student is None:
        raise HTTPException(404, profiles.STUDENT_NOT_FOUND)
    return student


async def hr_download_student(db: AsyncSession, user: User, student_id: UUID) -> User:
    return await _hr_student(db, user, student_id, "download")


# --- the limit -------------------------------------------------------------------------------------------------------------------
async def max_bytes(db: AsyncSession) -> int:
    row = await db.get(StudentResumeSetting, 1)
    return row.max_bytes if row else DEFAULT_MAX_BYTES


def settings_out(limit: int) -> dict:
    return {"max_mb": limit // MB, "max_bytes": limit, "min_mb": MIN_MB, "max_mb_ceiling": CEILING_MB}


def require_admin(user: User) -> None:
    if (user.role, user.division) != ("it_admin", "it"):
        raise HTTPException(403, ADMIN_ONLY)


async def save_settings(db: AsyncSession, admin: User, max_mb: int) -> dict:
    """R4: the new limit applies to the next upload; stored versions are never touched. Audited with before/after (itc-001)."""
    require_admin(admin)
    row = await db.get(StudentResumeSetting, 1, with_for_update=True)
    before = row.max_bytes // MB if row else DEFAULT_MAX_BYTES // MB
    if row is None:
        row = StudentResumeSetting(id=1)
        db.add(row)
    row.max_bytes, row.updated_by_user_id = max_mb * MB, admin.id
    audit_change(db, admin, SETTINGS_UPDATED, "student_resume_settings", 1, {"max_mb": before}, {"max_mb": max_mb})
    await db.commit()
    return settings_out(max_mb * MB)


# --- upload ----------------------------------------------------------------------------------------------------------------------
def _type_of(stream) -> str | None:
    """R3: PDF, a legacy OLE2 .doc, or a ZIP holding word/document.xml (only the central directory is read)."""
    stream.seek(0)
    head = stream.read(1024)
    stream.seek(0)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(OLE2):
        return DOC
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(stream) as archive:
                return DOCX if "word/document.xml" in archive.namelist() else None
        except zipfile.BadZipFile:
            return None
        finally:
            stream.seek(0)
    return None


async def _checked(db: AsyncSession, file: UploadFile) -> tuple[int, str]:
    """The spooled upload's size and type, without reading it into memory; 422 empty, 413 over the limit, 415 not a resume type."""
    stream = file.file
    stream.seek(0, 2)
    size = stream.tell()
    if size == 0:
        raise HTTPException(422, "The file is empty")
    limit = await max_bytes(db)
    if size > limit:
        raise HTTPException(413, f"The resume must be at most {limit // MB} MB")
    content_type = _type_of(stream)
    if content_type is None:
        raise HTTPException(415, "Upload a PDF, DOC or DOCX file")
    return size, content_type


async def _scanned(db: AsyncSession, actor: User, student: User, file: UploadFile, size: int, content_type: str) -> None:
    """itc-033 (DEC-SCOPE-357 C5): when a scanner is configured, nothing is stored until it says clean. Infected -> 422 with an audit row
    (the signature name, never the file name); no verdict -> 503 (fail closed). No scanner configured -> no scan (itc-026 R2)."""
    if not malware_scan.enabled():
        return
    try:
        signature = await malware_scan.scan(file.file)
    except malware_scan.ScanUnavailable:
        raise HTTPException(503, "Virus scanning is unavailable; please try again later") from None
    if signature is None:
        return
    db.add(AuditLog(user_id=actor.id, action=SCAN_REJECTED, entity_type="user", entity_id=str(student.id),
                    metadata_json={"signature": signature, "content_type": content_type, "size_bytes": size, "role": actor.role}))  # fmt: skip
    await db.commit()
    logger.warning("student_resume_scan_rejected", extra={"extra_fields": {"actor_id": str(actor.id), "student_id": str(student.id)}})
    raise HTTPException(422, "The file failed a virus scan and was not uploaded")


def store(file: UploadFile, content_type: str) -> str:
    """A server-generated key (a random id, safe to log); the client never names a path."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_stream(key, file.file, content_type)
    except Exception:
        logger.exception("student_resume_store_failed", extra={"extra_fields": {"key": key}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete a file stored for a write that did not commit; a failure leaves a logged orphan."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("student_resume_orphaned", extra={"extra_fields": {"key": key}})


async def _next_version(db: AsyncSession, student: User) -> int:
    """The student's user row is locked, so two uploads for one student serialise; the unique pair is the backstop."""
    await db.execute(select(User.id).where(User.id == student.id).with_for_update())
    return (await db.scalar(select(func.max(StudentResume.version)).where(StudentResume.student_user_id == student.id)) or 0) + 1


async def upload(db: AsyncSession, actor: User, student: User, file: UploadFile, visibility: str) -> dict:
    if visibility not in STUDENT_RESUME_VISIBILITIES:
        raise HTTPException(422, "Visibility must be 'hr' or 'private'")
    size, content_type = await _checked(db, file)
    await _scanned(db, actor, student, file, size, content_type)
    key = store(file, content_type)
    try:
        resume = StudentResume(
            student_user_id=student.id, version=await _next_version(db, student), storage_key=key, content_type=content_type,
            file_name=(file.filename or "").replace("\\", "/").rsplit("/", 1)[-1][:255] or None, size_bytes=size, visibility=visibility,
            uploaded_by_user_id=actor.id,
        )  # fmt: skip
        db.add(resume)
        db.add(AuditLog(user_id=actor.id, action=UPLOADED, entity_type="user", entity_id=str(student.id),
                        metadata_json={"version": resume.version, "content_type": content_type, "size_bytes": size, "visibility": visibility,
                                       "role": actor.role}))  # fmt: skip
        if visibility == "hr":  # itc-027 (DEC-SCOPE-354 H2): a version shared with HR opens or updates the student's review task
            await db.flush()
            await hr_reviews.on_resume_shared(db, actor, student, resume.id, resume.version)
        await db.commit()
    except Exception:  # a lost race on the version pair or a failed commit: nothing references the stored file
        await db.rollback()
        discard(key)
        raise
    logger.info("student_resume_uploaded", extra={"extra_fields": {"actor_id": str(actor.id), "student_id": str(student.id), "version": resume.version}})
    return _out(resume, actor)


# --- read ------------------------------------------------------------------------------------------------------------------------
def _out(resume: StudentResume, uploader: User | None) -> dict:
    return {
        "version": resume.version, "file_name": resume.file_name, "content_type": resume.content_type, "size_bytes": resume.size_bytes,
        "visibility": resume.visibility, "uploaded_by": {"id": uploader.id, "full_name": uploader.full_name} if uploader else None,
        "uploaded_by_role": uploader.role if uploader else None, "created_at": resume.created_at,
    }  # fmt: skip


def _versions(student: User, hr_only: bool):
    stmt = select(StudentResume).where(StudentResume.student_user_id == student.id)
    return stmt.where(StudentResume.visibility == "hr") if hr_only else stmt


async def listing(db: AsyncSession, student: User, *, hr_only: bool = False) -> dict:
    """Newest first (the first is current); HR's list holds `hr` versions only and has no upload."""
    stmt = _versions(student, hr_only).add_columns(User).outerjoin(User, User.id == StudentResume.uploaded_by_user_id)
    rows = (await db.execute(stmt.order_by(StudentResume.version.desc()))).all()
    return {"items": [_out(resume, uploader) for resume, uploader in rows], "max_bytes": await max_bytes(db), "can_upload": not hr_only}


async def download(db: AsyncSession, actor: User, student: User, version: int, *, hr_only: bool = False) -> Response:
    """R7: the audit row commits before a byte leaves (fail closed); served as an attachment named from the Student ID."""
    resume = await db.scalar(_versions(student, hr_only).where(StudentResume.version == version))
    if resume is None:
        raise HTTPException(404, NOT_FOUND)
    try:
        data = storage.read_bytes(resume.storage_key)
    except FileNotFoundError:
        logger.warning("student_resume_missing", extra={"extra_fields": {"key": resume.storage_key}})
        raise HTTPException(404, "Resume file not found") from None
    db.add(AuditLog(user_id=actor.id, action=DOWNLOADED, entity_type="user", entity_id=str(student.id), metadata_json={"version": version, "role": actor.role}))
    await db.commit()
    logger.info("student_resume_downloaded", extra={"extra_fields": {"actor_id": str(actor.id), "student_id": str(student.id), "version": version}})
    filename = f"resume-{student.student_code or 'student'}-v{version}.{EXTENSION[resume.content_type]}"
    return Response(content=data, media_type=resume.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
