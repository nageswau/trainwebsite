"""ENH-021 -- internship certificate upload/download/remove (docs/superpowers/specs/
2026-09-27-enh-021-026-internship-and-counselling-record-design.md §5.2, DEC-SCOPE-032 I5, security S5/S6/S13).
Modelled on ENH-025's photo routes (school_student_profile.py): content-sniffed type, size cap before a full read,
image metadata stripped, server-generated key, write -> commit -> delete the old object (a failed commit deletes the new
one). Scope and write rules are portfolio.py's own, imported -- never re-implemented here."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio import CERTIFICATE_PREFIX, _load_portfolio_entry, _require_portfolio_write, discard_certificate
from app.api.schools import _load_student_for_reader, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, PortfolioEntry, SchoolStudent, User
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

router = APIRouter(prefix="/school", tags=["school-portfolio"])
logger = get_logger("app.portfolio.certificate")

MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024
PDF = "application/pdf"
EXTENSION = {PDF: "pdf", "image/jpeg": "jpg", "image/png": "png"}
CERTIFICATE_URL = "/students/{student_id}/portfolio/entries/{entry_id}/certificate"
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}


def _content_type(data: bytes) -> str | None:
    """Decided by the bytes, never by the file name or the client's Content-Type (S5)."""
    return PDF if data.startswith(b"%PDF-") else detect_image_type(data)


async def _writable_internship(db: AsyncSession, user: User, student_id: UUID, entry_id: UUID) -> tuple[SchoolStudent, PortfolioEntry]:
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    if entry.section != "internship":
        raise HTTPException(404, "Internship entry not found")
    return student, entry


@router.put(CERTIFICATE_URL)
async def put_certificate(student_id: UUID, entry_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student, entry = await _writable_internship(db, user, student_id, entry_id)
    if entry.completion_status != "completed":
        raise HTTPException(422, "A certificate can only be attached to a completed internship")
    await require_school_entitlement(db, user, student.school_id, "internships", grandfathered_since=entry.created_at)
    data = await file.read(MAX_CERTIFICATE_BYTES + 1)
    if not data:
        raise HTTPException(422, "Certificate file is empty")
    if len(data) > MAX_CERTIFICATE_BYTES:
        raise HTTPException(413, "Certificate must be at most 5 MB")
    content_type = _content_type(data)
    if content_type is None:
        raise HTTPException(415, "Certificate must be a PDF, JPEG or PNG file")
    if content_type != PDF:
        try:
            data = strip_metadata(data, content_type)
        except InvalidImage:
            raise HTTPException(422, "Certificate could not be read as a valid JPEG or PNG image") from None

    old_key, new_key = entry.certificate_key, f"{CERTIFICATE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(new_key, data, content_type)
    except Exception:
        logger.exception("internship_certificate_store_failed", extra={"extra_fields": {"entry_id": str(entry.id)}})
        raise HTTPException(500, "Could not store the certificate; please try again") from None
    entry_id_str = str(entry.id)
    entry.certificate_key, entry.certificate_content_type, entry.updated_by_user_id = new_key, content_type, user.id
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_set", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"school_student_id": str(student.id), "replaced": old_key is not None, "content_type": content_type, "bytes": len(data)}))
    try:
        await db.commit()
    except Exception:
        discard_certificate(new_key, entry_id_str)
        raise
    if old_key:
        discard_certificate(old_key, entry_id_str)
    logger.info("internship_certificate_set", extra={"extra_fields": {"actor_id": str(user.id), "entry_id": entry_id_str, "replaced": old_key is not None, "bytes": len(data)}})
    return {"has_certificate": True, "content_type": content_type}


@router.get(CERTIFICATE_URL)
async def get_certificate(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    if entry.section != "internship" or not entry.certificate_key:
        raise HTTPException(404, "No certificate on file")
    try:
        data = storage.read_bytes(entry.certificate_key)
    except FileNotFoundError:
        logger.warning("internship_certificate_object_missing", extra={"extra_fields": {"entry_id": str(entry.id)}})
        raise HTTPException(404, "No certificate on file") from None
    media_type = entry.certificate_content_type or "application/octet-stream"
    entry_id_str = str(entry.id)
    # S13: the audit row is committed before any byte leaves; a failed commit serves nothing.
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_download", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"school_student_id": str(student.id), "role": user.role}))
    await db.commit()
    headers = {**HEADERS, "Content-Disposition": f'attachment; filename="internship-certificate.{EXTENSION.get(media_type, "bin")}"'}
    return Response(content=data, media_type=media_type, headers=headers)


@router.delete(CERTIFICATE_URL, status_code=204)
async def delete_certificate(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student, entry = await _writable_internship(db, user, student_id, entry_id)
    await require_school_entitlement(db, user, student.school_id, "internships", grandfathered_since=entry.created_at)
    old_key = entry.certificate_key
    if old_key is None:
        return Response(status_code=204)
    entry_id_str = str(entry.id)
    entry.certificate_key, entry.certificate_content_type, entry.updated_by_user_id = None, None, user.id
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_remove", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"school_student_id": str(student.id)}))
    await db.commit()
    discard_certificate(old_key, entry_id_str)
    logger.info("internship_certificate_removed", extra={"extra_fields": {"actor_id": str(user.id), "entry_id": entry_id_str}})
    return Response(status_code=204)
