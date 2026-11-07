"""pob-006 (DEC-SCOPE-418, spec docs/superpowers/specs/2026-11-06-pob-006-company-import-merge-design.md): the company and contact import, and the two merges.

`preview` checks a file and writes nothing; the commit sends the same file with an Idempotency-Key and creates, matches or rejects each row in one transaction. A
repeated key or the same file replays the stored report (I8). Imports run one at a time. Every import route needs `crm.import`, every merge route `crm.merge`; the
grant never widens company scope (G3). History is the caller's own, a manager's also their team's, super_admin's everyone's (I10)."""

import csv
import hashlib
import io
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, KEY_PATTERN, KEY_REUSED, LOCK_TIMEOUT, _lock_timed_out
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, CrmImportBatch, User
from app.schemas import RecCompanyMergeBody, RecContactMergeBody
from app.services import company_import as imports
from app.services import company_merge as merges
from app.services import recruiter_companies as companies
from app.services.recruiter import MANAGER_ROLE

logger = get_logger("app.recruiter")
router = APIRouter(prefix="/recruiter", tags=["recruiter-companies"])
LOCK_KEY = 290_006  # pg_advisory_xact_lock key serialising company imports (a fixed constant, bound as a parameter)
NOT_FOUND = "Import not found"


def _scope(user: User) -> list:
    if user.role == "super_admin":
        return []
    mine = CrmImportBatch.uploaded_by_user_id == user.id
    return [or_(mine, CrmImportBatch.uploaded_by_user_id.in_(companies.team_ids(user)))] if user.role == MANAGER_ROLE else [mine]


async def _rows(file: UploadFile) -> tuple[bytes, list]:
    raw = await file.read(imports.MAX_BYTES + 1)
    return raw, imports.read_file(file.filename or "", raw)


@router.get("/company-imports/template")
async def template(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await imports.require_importer(db, user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(imports.COLUMNS)
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=company-import-template.csv", **NO_STORE})


@router.post("/company-imports/preview")
async def preview(file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """I8: every row's outcome if the file were imported now. Read only: no batch, row, company, contact or audit is written."""
    await imports.require_importer(db, user)
    _, rows = await _rows(file)
    results = await imports.run(db, user, rows)
    return {**imports.counts(results), "rows": results}


async def _replay(db: AsyncSession, user: User, key: str, digest: str) -> CrmImportBatch | None:
    """I8: the batch this key made (422 when it was another file), else the same file imported cleanly under another key. A file with row errors may run again: the
    rows it matched stay matched, and what was fixed since (a catalogue value, a restored company) goes in, as its preview says."""
    mine = CrmImportBatch.uploaded_by_user_id == user.id
    batch = await db.scalar(select(CrmImportBatch).where(mine, CrmImportBatch.idempotency_key == key))
    if batch is not None:
        if batch.file_sha256 != digest:
            raise HTTPException(422, KEY_REUSED)
        return batch
    return await db.scalar(select(CrmImportBatch).where(mine, CrmImportBatch.file_sha256 == digest, CrmImportBatch.error_count == 0).order_by(CrmImportBatch.created_at).limit(1))


@router.post("/company-imports", status_code=201)
async def commit(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """201 with the per-row report; a bad file or key is 422 before any row (nothing is created)."""
    started = time.monotonic()
    await imports.require_importer(db, user)
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    if not KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 1-120 letters, digits or . _ : -")
    raw, rows = await _rows(file)
    digest = hashlib.sha256(raw).hexdigest()
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    if (batch := await _replay(db, user, idempotency_key, digest)) is not None:
        logger.info("company_import_replayed", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id)}})
        return await imports.report(db, user, batch, replayed=True)
    batch = CrmImportBatch(uploaded_by_user_id=user.id, idempotency_key=idempotency_key, file_sha256=digest, file_name=(file.filename or "upload")[:200])
    db.add(batch)
    await db.flush()
    try:
        results = await imports.run(db, user, rows, batch.id)
    except DBAPIError as exc:
        if _lock_timed_out(exc):  # a company row held past lock_timeout by a concurrent edit
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    await imports.store(db, batch, results)
    tally = {"created": batch.created_count, "matched": batch.matched_count, "error": batch.error_count, "companies_created": batch.companies_created, "contacts_created": batch.contacts_created}
    db.add(AuditLog(user_id=user.id, action="crm.import", entity_type="crm_import_batches", entity_id=str(batch.id), metadata_json={"total": batch.total_rows, **tally, "file_sha256": digest}))
    await db.commit()
    logger.info(
        "company_import_completed",
        extra={"extra_fields": {"batch_id": str(batch.id), "actor_id": str(user.id), "total": batch.total_rows, **tally, "duration_ms": round((time.monotonic() - started) * 1000)}},
    )
    return await imports.report(db, user, batch)


@router.get("/company-imports")
async def history(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await imports.require_importer(db, user)
    filters = _scope(user)
    total = await db.scalar(select(func.count()).select_from(CrmImportBatch).where(*filters))
    stmt = (select(CrmImportBatch, User).join(User, User.id == CrmImportBatch.uploaded_by_user_id).where(*filters)
            .order_by(CrmImportBatch.created_at.desc(), CrmImportBatch.id.desc()).limit(limit).offset(offset))  # fmt: skip
    return {"items": [imports.summary(batch, uploader) for batch, uploader in (await db.execute(stmt)).all()], "total": total or 0, "limit": limit, "offset": offset}


async def _batch(db: AsyncSession, user: User, batch_id: UUID) -> CrmImportBatch:
    await imports.require_importer(db, user)
    batch = await db.scalar(select(CrmImportBatch).where(CrmImportBatch.id == batch_id, *_scope(user)))
    if batch is None:
        raise HTTPException(404, NOT_FOUND)
    return batch


@router.get("/company-imports/{batch_id}")
async def import_report(batch_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    response.headers.update(NO_STORE)
    return await imports.report(db, user, await _batch(db, user, batch_id))


@router.get("/company-imports/{batch_id}/report.csv")
async def import_report_csv(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    body = await imports.report(db, user, await _batch(db, user, batch_id))
    return Response(content=imports.report_csv(body), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=company-import-{batch_id}.csv", **NO_STORE})


# --- merges -----------------------------------------------------------------------------------------------------------------------------


@router.get("/companies/{company_id}/merge")
async def company_merge_preview(company_id: UUID, victim: str = Query(min_length=1, max_length=20), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.require_crm(db, user, "merge", merges.NO_MERGE)
    return await merges.preview(db, user, company_id, victim)


@router.post("/companies/{company_id}/merge")
async def company_merge(company_id: UUID, payload: RecCompanyMergeBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.require_crm(db, user, "merge", merges.NO_MERGE)
    body = await merges.merge(db, user, company_id, payload.victim_code, payload.use_victim, payload.reason)
    await db.commit()
    return body


@router.get("/contacts/{contact_id}/merge")
async def contact_merge_preview(contact_id: UUID, victim: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.require_crm(db, user, "merge", merges.NO_MERGE)
    return await merges.contact_preview(db, user, contact_id, victim)


@router.post("/contacts/{contact_id}/merge")
async def contact_merge(contact_id: UUID, payload: RecContactMergeBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.require_crm(db, user, "merge", merges.NO_MERGE)
    body = await merges.merge_contact(db, user, contact_id, payload.victim_id, payload.use_victim, payload.reason)
    await db.commit()
    return body
