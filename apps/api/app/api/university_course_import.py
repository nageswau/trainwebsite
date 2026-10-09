"""upc-017 (DEC-SCOPE-145 CO14, spec §3): a university's course CSV import -- the template and the upload, by the university's writers (CO1).

The bounded read and the CSV parser are ENH-028's (`school_bulk`), the batch and replay are upc-005's (IM6): one request = one transaction
under the university row lock; the batch keeps counts and per-row outcomes, never the file, and replays its report for a repeated
Idempotency-Key from the same uploader with the same file."""

import hashlib
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, KEY_REUSED, LOCK_TIMEOUT, _lock_timed_out, _read_csv, _read_upload
from app.api.university_courses import _writable
from app.core.database import get_db
from app.models import AuditLog, CourseImportBatch, University, User
from app.services import course_import as imp
from app.services import partnership_universities as unis

router = APIRouter(prefix="/partnership/universities", tags=["partnership-course-import"])
TARGET = "course_import"  # the file-error log label shared with the ENH-028 parser


async def _claim(db: AsyncSession, user: User, uni: University, key: str, digest: str) -> tuple[CourseImportBatch, bool]:
    """The unique (uploader, key) index decides between racing requests; the same key replays only the same file to the same university."""
    batch = CourseImportBatch(university_id=uni.id, uploaded_by_user_id=user.id, idempotency_key=key, file_sha256=digest)
    try:
        async with db.begin_nested():
            db.add(batch)
            await db.flush()
        return batch, False
    except IntegrityError:
        pass
    existing = await db.scalar(select(CourseImportBatch).where(CourseImportBatch.uploaded_by_user_id == user.id, CourseImportBatch.idempotency_key == key))
    if existing is None or existing.file_sha256 != digest or existing.university_id != uni.id:
        raise HTTPException(422, KEY_REUSED)
    return existing, True


async def _report(db: AsyncSession, batch: CourseImportBatch) -> dict:
    return {**imp.summary(batch, await db.get_one(User, batch.uploaded_by_user_id)), "rows": batch.results_json}


@router.get("/{university_id}/courses/imports/template")
async def course_import_template(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await unis.require_reader(db, user)
    uni = await unis.load(db, university_id)
    unis.require(user, uni, await unis.team_of(db, user), "can_edit", "course_import_template")
    headers = {"Cache-Control": "private, no-store", "Content-Disposition": "attachment; filename=course-import-template.csv"}
    return Response(content=",".join(imp.COLUMNS) + "\r\n", media_type="text/csv", headers=headers)


@router.post("/{university_id}/courses/import", status_code=201)
async def import_courses(
    university_id: UUID,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """201 with the per-row report; a bad file is 422/413 before any row (nothing is created)."""
    started = time.monotonic()
    key, raw = await _read_upload(file, idempotency_key, TARGET, user)
    filled = _read_csv(raw, target_type=TARGET, user=user, required=imp.REQUIRED, columns=imp.COLUMNS, max_rows=imp.MAX_ROWS, known=imp.COLUMNS)
    try:
        await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
        uni = await _writable(db, user, university_id, "course_import")
        batch, replay = await _claim(db, user, uni, key, hashlib.sha256(raw).hexdigest())
        if replay:
            return await _report(db, batch)
        results = await imp.run(db, user, uni, batch, filled)
    except DBAPIError as exc:
        if not _lock_timed_out(exc):
            raise
        await db.rollback()
        raise HTTPException(409, IN_PROGRESS) from exc
    batch.results_json = results
    batch.total_rows = len(results)
    batch.created_count = sum(r["status"] == "created" for r in results)
    batch.duplicate_count = sum(r["status"] == "duplicate" for r in results)
    batch.invalid_count = batch.total_rows - batch.created_count - batch.duplicate_count
    tally = {"created": batch.created_count, "duplicate": batch.duplicate_count, "invalid": batch.invalid_count}
    meta = {"university_id": str(uni.id), "total": batch.total_rows, **tally, "file_sha256": batch.file_sha256}
    db.add(AuditLog(user_id=user.id, action="university_course.import", entity_type="course_import_batch", entity_id=str(batch.id), metadata_json=meta))
    await db.commit()
    unis.log("university_course_import_completed", user, uni.id, batch_id=str(batch.id), **tally, duration_ms=round((time.monotonic() - started) * 1000))
    return await _report(db, batch)
