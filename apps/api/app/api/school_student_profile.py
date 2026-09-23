"""ENH-025 -- Student Master photo and career-preference routes (docs/superpowers/specs/
2026-09-23-enh-025-student-master-fields-design.md §3.4, DEC-SCOPE-027). Scope checks are imported from
schools.py (same pattern as portfolio.py), never re-implemented here."""

import hashlib
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _apply_master_fields, _load_readable_student, _master_fields_or_422, _own_school_id, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, SchoolStudent, User
from app.schemas import CAREER_PREFERENCE_KEYS, CareerPreferencesUpdate
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

router = APIRouter(prefix="/school", tags=["school"])
logger = get_logger("app.school.profile")

MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_PREFIX = "school-student-photos"
PHOTO_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Content-Disposition": "inline",
}


def _digest(key: str) -> str:
    """Operators can match an orphan to a file by hashing names; the key itself is never logged (spec §5)."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _discard(key: str, student_id: UUID) -> None:
    try:
        storage.delete(key)
    except Exception:
        logger.warning("student_photo_orphaned", extra={"extra_fields": {"student_id": str(student_id), "key_digest": _digest(key)}})


async def _coordinator_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """Own-school coordinator only; the row is locked so concurrent photo writes serialize (no orphaned objects)."""
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.id == student_id).with_for_update())
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    return student


@router.put("/students/{student_id}/photo")
async def put_student_photo(student_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _coordinator_student(db, user, student_id)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if not data:
        raise HTTPException(422, "photo file is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo must be at most 2 MB")
    content_type = detect_image_type(data)
    if content_type is None:
        raise HTTPException(415, "photo must be a JPEG or PNG image")
    try:
        data = strip_metadata(data, content_type)
    except InvalidImage:
        raise HTTPException(422, "photo could not be read as a valid JPEG or PNG image") from None

    old_key, new_key = student.photo_key, f"{PHOTO_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(new_key, data, content_type)
    except Exception:
        logger.exception("student_photo_store_failed", extra={"extra_fields": {"student_id": str(student.id)}})
        raise HTTPException(500, "Could not store the photo; please try again") from None
    student.photo_key, student.photo_content_type = new_key, content_type
    db.add(AuditLog(user_id=user.id, action="school.student_photo_set", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id), "replaced": old_key is not None, "content_type": content_type, "bytes": len(data)}))
    try:
        await db.commit()
    except Exception:
        _discard(new_key, student.id)
        raise
    if old_key:
        _discard(old_key, student.id)
    logger.info("student_photo_set", extra={"extra_fields": {"student_id": str(student.id), "replaced": old_key is not None, "bytes": len(data)}})
    return {"has_photo": True}


@router.get("/students/{student_id}/photo")
async def get_student_photo(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_readable_student(db, user, student_id)
    if not student.photo_key:
        raise HTTPException(404, "No photo on file")
    try:
        data = storage.read_bytes(student.photo_key)
    except FileNotFoundError:
        logger.warning("student_photo_object_missing", extra={"extra_fields": {"student_id": str(student.id), "key_digest": _digest(student.photo_key)}})
        raise HTTPException(404, "No photo on file") from None
    return Response(content=data, media_type=student.photo_content_type, headers=PHOTO_HEADERS)


@router.delete("/students/{student_id}/photo", status_code=204)
async def delete_student_photo(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _coordinator_student(db, user, student_id)
    old_key = student.photo_key
    if old_key is None:
        return Response(status_code=204)
    student.photo_key, student.photo_content_type = None, None
    db.add(AuditLog(user_id=user.id, action="school.student_photo_remove", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id)}))
    await db.commit()
    _discard(old_key, student.id)
    logger.info("student_photo_removed", extra={"extra_fields": {"student_id": str(student.id)}})
    return Response(status_code=204)


async def _counselor_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    return await _student_in_portfolio(db, user, student_id)


def _career_out(student: SchoolStudent) -> dict:
    return {"student_id": student.id, **{key: getattr(student, key) for key in CAREER_PREFERENCE_KEYS}}


@router.get("/students/{student_id}/career-preferences")
async def get_career_preferences(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _career_out(await _counselor_student(db, user, student_id))


@router.patch("/students/{student_id}/career-preferences")
async def update_career_preferences(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The whole body is validated (extra="forbid"): only the four career fields can ever be written here."""
    student = await _counselor_student(db, user, student_id)
    fields = _master_fields_or_422(CareerPreferencesUpdate, payload)
    changed = _apply_master_fields(student, fields)
    db.add(AuditLog(user_id=user.id, action="school.student_career_preferences_update", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id), "changed_fields": changed}))
    await db.commit()
    logger.info("student_career_preferences_updated", extra={"extra_fields": {"student_id": str(student.id), "changed": len(changed)}})
    return _career_out(student)
