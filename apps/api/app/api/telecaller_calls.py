"""tel-010 (DEC-SCOPE-096, spec §4): calls on a lead -- the lead's calls, log a call (with its pipeline effect and optional next follow-up),
same-day edit and delete, and the day counts.

Scope is the lead's (tel-004 `lead_pipeline.scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the lead
lock, role, handover, the rules, the change, audit, one commit here, then the log."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.lead_stages import label
from app.models import Enquiry, User
from app.schemas import LeadCallCreate, LeadCallUpdate
from app.services import lead_calls as svc
from app.services import lead_pipeline, telecaller_leads
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/telecaller", tags=["telecaller-calls"])


@router.get("/calls/day-counts")
async def call_day_counts(day: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: calls made on one IST day (default today) by the caller scope, per outcome, with the connected / not connected totals."""
    filters = svc.caller_filter(user)
    return await svc.day_counts(db, filters, day or today_ist(await db_now(db)))


@router.get("/leads/{lead_id}/calls")
async def lead_calls(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, scope = lead_pipeline.scope(user)
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *scope))
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await svc.lead_page(db, user, lead, await db_now(db), limit, offset)


@router.post("/leads/{lead_id}/calls", status_code=201)
async def log_call(lead_id: UUID, payload: LeadCallCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry logs a second call; the daily cap bounds it). Returns the call, the lead's stage after the outcome's effect
    and the id of the follow-up it created."""
    _, scope = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *scope)
    svc.require_telecaller(user)
    telecaller_leads.require_writable(user, lead)
    now = await db_now(db)
    call, follow_up_id = await svc.create(db, user, lead, payload, now)
    stage = {"id": lead.id, "status": lead.status, "status_label": label(lead.status), "stage_changed_at": lead.stage_changed_at}
    await db.commit()
    svc.log("lead_call_logged", user, call.id, lead_id=str(lead_id), outcome=payload.outcome, follow_up=follow_up_id is not None)
    return {"call": await svc.one(db, user, call.id, now), "lead": stage, "follow_up_id": follow_up_id}


@router.patch("/calls/{call_id}")
async def update_call(call_id: UUID, payload: LeadCallUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL4: same IST day, by the caller; the outcome is locked."""
    _, scope = lead_pipeline.scope(user)
    now = await db_now(db)
    call = await svc.load_for_write(db, user, call_id, scope, now)
    changed = svc.apply_update(db, user, call, payload.model_dump(exclude_unset=True), now)
    await db.commit()
    if changed:
        svc.log("lead_call_updated", user, call_id, fields=changed)
    return await svc.one(db, user, call_id, now)


@router.delete("/calls/{call_id}", status_code=204)
async def delete_call(call_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CL4: no reversal -- a stage move or a follow-up the call made stays."""
    _, scope = lead_pipeline.scope(user)
    call = await svc.load_for_write(db, user, call_id, scope, await db_now(db))
    svc.audit(db, user, "delete", call.id, {"lead_id": str(call.lead_id), "outcome": call.outcome})
    await db.delete(call)
    await db.commit()
    svc.log("lead_call_deleted", user, call_id)
    return Response(status_code=204)
