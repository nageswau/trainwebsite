"""upc-005 (DEC-SCOPE-127, spec §3): University CSV import -- a head, overseas_admin or super_admin uploads one file; each row is created,
reported as a duplicate (upc-004's key, against the master and earlier rows) or reported invalid with its reason.

The bounded read and the CSV parser are ENH-028's (`school_bulk`). One request = one transaction; imports run one at a time (IM9). The
batch keeps counts and per-row outcomes, never the file, and replays its report for a repeated Idempotency-Key (IM6). Registered before
`partnership_universities` so `/imports` is never read as a university id."""

import hashlib
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, KEY_REUSED, LOCK_TIMEOUT, _lock_timed_out, _read_csv, _read_upload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, UniversityImportBatch, User
from app.services import partnership_universities as svc
from app.services import university_import as imp

logger = get_logger("app.partnership")
router = APIRouter(prefix="/partnership/universities", tags=["partnership-university-import"])

TARGET = "university_import"  # the file-error log label shared with the ENH-028 parser
LOCK_KEY = 290_105  # pg_advisory_xact_lock key serialising university imports (IM9; a fixed constant, bound as a parameter)
NOT_FOUND = "Import not found"
RACED = "Another university with one of these names was just added. Import the file again."
CSV_HEADERS = {"Cache-Control": "private, no-store"}


async def _require_importer(db: AsyncSession, user: User) -> None:
    """IM8: the roles that add universities (upc-003 UM8); an overseas_admin outside the overseas division fails require_reader."""
    await svc.require_reader(db, user)
    if user.role not in svc.CATALOGUE_ROLES:
        svc.log("university_import_refused", user, "-")
        raise HTTPException(403, "Your role cannot import universities")


def _scope(user: User) -> list:
    """IM8: the caller's own imports; super_admin sees all."""
    return [] if user.role == "super_admin" else [UniversityImportBatch.uploaded_by_user_id == user.id]


async def _claim(db: AsyncSession, user: User, key: str, digest: str) -> tuple[UniversityImportBatch, bool]:
    """IM6: insert the batch; the unique (uploader, key) index decides between racing requests. The same key replays the first batch
    when the file is the same, else 422. Returns the batch and whether it is a replay."""
    batch = UniversityImportBatch(uploaded_by_user_id=user.id, idempotency_key=key, file_sha256=digest)
    try:
        async with db.begin_nested():
            db.add(batch)
            await db.flush()
        return batch, False
    except IntegrityError:
        pass
    existing = await db.scalar(select(UniversityImportBatch).where(UniversityImportBatch.uploaded_by_user_id == user.id, UniversityImportBatch.idempotency_key == key))
    if existing is None or existing.file_sha256 != digest:
        raise HTTPException(422, KEY_REUSED)
    return existing, True


async def _report(db: AsyncSession, batch: UniversityImportBatch) -> dict:
    """One shape for the first response, every replay and the history detail."""
    uploader = await db.get_one(User, batch.uploaded_by_user_id)
    return {**imp.summary(batch, uploader), "rows": batch.results_json}


async def _owned(db: AsyncSession, user: User, batch_id: UUID) -> UniversityImportBatch:
    await _require_importer(db, user)
    batch = await db.scalar(select(UniversityImportBatch).where(UniversityImportBatch.id == batch_id, *_scope(user)))
    if batch is None:
        raise HTTPException(404, NOT_FOUND)
    return batch


@router.get("/imports/template")
async def import_template(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _require_importer(db, user)
    return Response(content=",".join(imp.COLUMNS) + "\r\n", media_type="text/csv", headers={**CSV_HEADERS, "Content-Disposition": "attachment; filename=university-import-template.csv"})


@router.post("/import", status_code=201)
async def import_universities(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """201 with the per-row report; a bad file is 422/413 before any row (nothing is created)."""
    started = time.monotonic()
    await _require_importer(db, user)
    key, raw = await _read_upload(file, idempotency_key, TARGET, user)
    filled = _read_csv(raw, target_type=TARGET, user=user, required=imp.REQUIRED, columns=imp.COLUMNS, max_rows=imp.MAX_ROWS, known=imp.COLUMNS)
    try:
        # `set_config(..., true)` is SET LOCAL with a bound parameter: it bounds every lock wait below.
        await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
        batch, replay = await _claim(db, user, key, hashlib.sha256(raw).hexdigest())
        if replay:
            svc.log("university_import_replayed", user, "-", batch_id=str(batch.id))
            return await _report(db, batch)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        results = await imp.run(db, user, batch, filled)
    except IntegrityError:  # a manual create took one of the new slugs in the same instant (UM14); nothing was kept
        await db.rollback()
        raise HTTPException(409, RACED) from None
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
    db.add(
        AuditLog(
            user_id=user.id,
            action="university.import",
            entity_type="university_import_batch",
            entity_id=str(batch.id),
            metadata_json={"total": batch.total_rows, **tally, "file_sha256": batch.file_sha256},
        )
    )
    await db.commit()
    svc.log("university_import_completed", user, "-", batch_id=str(batch.id), total=batch.total_rows, **tally, duration_ms=round((time.monotonic() - started) * 1000))
    return await _report(db, batch)


@router.get("/imports")
async def imports(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """IM8: the caller's imports (super_admin: all), newest first."""
    await _require_importer(db, user)
    filters = _scope(user)
    total = await db.scalar(select(func.count()).select_from(UniversityImportBatch).where(*filters))
    stmt = (
        select(UniversityImportBatch, User)
        .join(User, User.id == UniversityImportBatch.uploaded_by_user_id)
        .where(*filters)
        .order_by(UniversityImportBatch.created_at.desc(), UniversityImportBatch.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [imp.summary(batch, uploader) for batch, uploader in (await db.execute(stmt)).all()]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/imports/{batch_id}")
async def import_report(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _report(db, await _owned(db, user, batch_id))


@router.get("/imports/{batch_id}/report.csv")
async def import_report_csv(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    batch = await _owned(db, user, batch_id)
    return Response(content=imp.report_csv(batch), media_type="text/csv", headers={**CSV_HEADERS, "Content-Disposition": f"attachment; filename=university-import-{batch.id}.csv"})
