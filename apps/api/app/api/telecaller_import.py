"""tel-006 (DEC-SCOPE-091, spec §3): CSV lead import per campaign -- a manager uploads one file for one active campaign, and each row is
created, attached to a known person's lead (T12) or rejected with its line and reason (IM1).

The bounded read and the CSV parser are ENH-028's (`school_bulk`); each row goes through `lead_intake.import_row`. One request = one
transaction with a SAVEPOINT per row; imports run one at a time (R7b). The batch keeps counts and per-row outcomes, never the file or a
name, phone or email (R9), and replays its report for a repeated Idempotency-Key (R8)."""

import csv
import hashlib
import io
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, KEY_REUSED, LOCK_TIMEOUT, _lock_timed_out, _read_csv, _read_upload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, Enquiry, LeadImportBatch, TelCampaign, User
from app.schemas import LeadImportRow, validation_message
from app.services import lead_intake
from app.services.telecaller import require_manager
from app.services.telecaller_catalogue import locked_active_product
from app.worker import sync_enquiry_to_crm_task

logger = get_logger("app.leads")
router = APIRouter(prefix="/telecaller", tags=["telecaller-import"])

TARGET = "lead_import"  # the file-error log label shared with the ENH-028 parser
COLUMNS = tuple(LeadImportRow.model_fields)
REQUIRED = ("name", "phone")
MAX_ROWS = 500
LOCK_KEY = 290_006  # pg_advisory_xact_lock key serialising lead imports (R7b; a fixed constant, bound as a parameter)
ROW_CONFLICT = "This row conflicts with a change made at the same time; upload it again"
NOT_FOUND = "Import not found"
DEADLOCK = "40P01"


def _scope(user: User) -> list:
    """R11: a manager sees their own imports; super_admin sees all."""
    require_manager(user)
    return [] if user.role == "super_admin" else [LeadImportBatch.uploaded_by_user_id == user.id]


async def _campaign(db: AsyncSession, campaign_id: UUID, division: str | None):
    """R2: an active campaign (FOR SHARE, so a concurrent deactivation waits) with an active product, and the team its leads join."""
    campaign = await db.scalar(select(TelCampaign).where(TelCampaign.id == campaign_id).with_for_update(read=True))
    if campaign is None or not campaign.active:
        raise HTTPException(422, "Choose an active campaign")
    product = await locked_active_product(db, campaign.product_id)
    return campaign, product, lead_intake.lead_team(product, division)


async def _claim(db: AsyncSession, user: User, key: str, digest: str, campaign: TelCampaign, division: str) -> tuple[LeadImportBatch, bool]:
    """R8: insert the batch; the unique (uploader, key) index decides between racing requests. The loser replays the winner's batch when
    the file, campaign and division are the same, else 422. Returns the batch and whether it is a replay."""
    batch = LeadImportBatch(campaign_id=campaign.id, division=division, uploaded_by_user_id=user.id, idempotency_key=key, file_sha256=digest)
    try:
        async with db.begin_nested():
            db.add(batch)
            await db.flush()
        return batch, False
    except IntegrityError:
        pass
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    existing = await db.scalar(select(LeadImportBatch).where(LeadImportBatch.uploaded_by_user_id == user.id, LeadImportBatch.idempotency_key == key))
    if existing is None or (existing.file_sha256, existing.campaign_id, existing.division) != (digest, campaign.id, division):
        raise HTTPException(422, KEY_REUSED)
    return existing, True


async def _serialise(db: AsyncSession, user: User) -> None:
    """R7b: one import at a time -- two files naming the same people in different orders would deadlock on the per-person locks."""
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            logger.warning("lead_import_lock_timeout", extra={"extra_fields": {"actor_id": str(user.id)}})
            raise HTTPException(409, IN_PROGRESS) from exc
        raise


async def _rows(db: AsyncSession, user: User, batch: LeadImportBatch, campaign, product, division: str, filled) -> tuple[list[dict], list[UUID]]:
    """Each row in its own savepoint: a failure undoes that row only. Returns the outcomes and the ids of the created leads."""
    results, created = [], []
    for line, cells in filled:
        status, lead_id, error = "rejected", None, None
        try:
            row = LeadImportRow.model_validate({name: value for name, value in cells.items() if value})
        except ValidationError as exc:
            error = validation_message(exc)
        else:
            try:
                async with db.begin_nested():
                    lead, attached = await lead_intake.import_row(db, user, campaign, product, division, row, batch.id)
                status, lead_id = ("attached" if attached else "created"), lead.id
            except DBAPIError as exc:
                # R7: a lock wait past lock_timeout, or a deadlock with a concurrent manual/website intake of the same person
                if not (_lock_timed_out(exc) or getattr(exc.orig, "sqlstate", None) == DEADLOCK):
                    raise
                error = ROW_CONFLICT
                logger.warning("lead_import_row_conflict", extra={"extra_fields": {"batch_id": str(batch.id), "row_number": line}})
        if status == "created":
            created.append(lead_id)
        results.append({"row_number": line, "status": status, "lead_id": str(lead_id) if lead_id else None, "error": error})
    return results, created


def _counts(batch: LeadImportBatch) -> dict:
    return {"total_rows": batch.total_rows, "created_count": batch.created_count, "attached_count": batch.attached_count,
            "rejected_count": batch.rejected_count}


async def _report(db: AsyncSession, batch: LeadImportBatch) -> dict:
    """One shape for the first response, every replay and the history detail: Lead IDs are read back by the stored lead ids."""
    ids = [UUID(r["lead_id"]) for r in batch.results_json if r["lead_id"]]
    codes = dict((await db.execute(select(Enquiry.id, Enquiry.lead_code).where(Enquiry.id.in_(ids)))).all()) if ids else {}
    name = await db.scalar(select(TelCampaign.name).where(TelCampaign.id == batch.campaign_id))
    rows = [r | {"lead_code": codes.get(UUID(r["lead_id"])) if r["lead_id"] else None} for r in batch.results_json]
    return {"id": batch.id, "campaign": {"id": batch.campaign_id, "name": name}, "division": batch.division, **_counts(batch),
            "created_at": batch.created_at, "rows": rows}


@router.get("/imports/template")
async def import_template(user: User = Depends(get_current_user)):
    require_manager(user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(COLUMNS)
    return Response(content=buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=lead-import-template.csv", "Cache-Control": "private, no-store"})


@router.post("/imports", status_code=201)
async def import_leads(
    file: UploadFile = File(...),
    campaign_id: UUID = Form(...),
    division: Literal["it", "overseas"] | None = Form(None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """IM1: 201 with the per-row report; a bad file or campaign is 422 before any row (nothing is created)."""
    started = time.monotonic()
    require_manager(user)
    key, raw = await _read_upload(file, idempotency_key, TARGET, user)
    filled = _read_csv(raw, target_type=TARGET, user=user, required=REQUIRED, columns=COLUMNS, max_rows=MAX_ROWS, known=COLUMNS)
    # `set_config(..., true)` is SET LOCAL with a bound parameter: it bounds every lock wait below.
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    campaign, product, team = await _campaign(db, campaign_id, division)
    batch, replay = await _claim(db, user, key, hashlib.sha256(raw).hexdigest(), campaign, team)
    if replay:
        logger.info("lead_import_replayed", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id)}})
        return await _report(db, batch)
    await _serialise(db, user)

    results, created = await _rows(db, user, batch, campaign, product, team, filled)
    batch.results_json = results
    batch.total_rows = len(results)
    batch.created_count = len(created)
    batch.attached_count = sum(r["status"] == "attached" for r in results)
    batch.rejected_count = batch.total_rows - batch.created_count - batch.attached_count
    counts = {"created": batch.created_count, "attached": batch.attached_count, "rejected": batch.rejected_count}
    db.add(AuditLog(user_id=user.id, action="lead.import", entity_type="lead_import_batch", entity_id=str(batch.id),
                    metadata_json={"campaign_id": str(campaign.id), "total": batch.total_rows, **counts, "file_sha256": batch.file_sha256}))
    await db.commit()
    for lead_id in created:  # R6: like every other new lead, queued for the CRM only after the commit
        sync_enquiry_to_crm_task.delay(str(lead_id))
    logger.info("lead_import_completed", extra={"extra_fields": {
        "batch_id": str(batch.id), "actor_id": str(user.id), "total": batch.total_rows, **counts, "duration_ms": round((time.monotonic() - started) * 1000)}})
    return await _report(db, batch)


@router.get("/imports")
async def imports(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """R11: the caller's imports (super_admin: all), newest first."""
    filters = _scope(user)
    total = await db.scalar(select(func.count()).select_from(LeadImportBatch).where(*filters))
    stmt = (select(LeadImportBatch, TelCampaign.name, User.full_name)
            .join(TelCampaign, TelCampaign.id == LeadImportBatch.campaign_id).join(User, User.id == LeadImportBatch.uploaded_by_user_id)
            .where(*filters).order_by(LeadImportBatch.created_at.desc(), LeadImportBatch.id.desc()).limit(limit).offset(offset))
    items = [
        {"id": batch.id, "campaign": {"id": batch.campaign_id, "name": campaign}, "division": batch.division,
         "uploaded_by": {"id": batch.uploaded_by_user_id, "full_name": uploader}, **_counts(batch), "created_at": batch.created_at}
        for batch, campaign, uploader in (await db.execute(stmt)).all()
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/imports/{batch_id}")
async def import_report(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    batch = await db.scalar(select(LeadImportBatch).where(LeadImportBatch.id == batch_id, *_scope(user)))
    if batch is None:
        raise HTTPException(404, NOT_FOUND)
    return await _report(db, batch)
