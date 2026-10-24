"""tel-011 (DEC-SCOPE-094, spec §3): follow-ups on a lead -- the day / overdue lists, a lead's follow-ups, create, reschedule/edit,
complete and cancel.

Scope is the lead's (tel-004 `lead_pipeline.scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the lead
lock, role (only the lead's telecaller, F2), handover, the follow-up lock and state, validation, change, audit, one commit here, log.

ccrm-003 (DEC-SCOPE-243, A4): `/counselor/...` -- the same lead list, create and follow-up actions for the counselor a lead is handed to,
in `lead_handover.counselor_scope` (owner + division; other roles 403, another counselor's lead 404). The handlers below serve both."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Enquiry, User
from app.schemas import BdmAppointmentReason, LeadFollowUpCreate, LeadFollowUpUpdate
from app.services import lead_follow_ups as svc
from app.services import lead_handover, lead_pipeline, telecaller_leads
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/telecaller", tags=["telecaller-follow-ups"])
counselor_router = APIRouter(prefix="/counselor", tags=["telecaller-follow-ups"])


def _telecaller_scope(user: User) -> list:
    return lead_pipeline.scope(user)[1]


@router.get("/follow-ups")
async def list_follow_ups(
    view: Literal["day", "overdue"] = "day",
    day: date | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§7 "Today's follow-ups" (AC1, `day` defaults to today in IST) and the overdue list (F1): a telecaller's own leads, a manager's
    reports' leads (read only), super_admin all."""
    _, scope = lead_pipeline.scope(user)
    now = await db_now(db)
    return await svc.list_page(db, user, scope, view, day or today_ist(now), now, limit, offset)


@counselor_router.get("/follow-ups")
async def counselor_follow_ups(
    view: Literal["day", "overdue"] = "day",
    day: date | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ccrm-029 (T7, spec AC 7): the counselor's own day / overdue follow-ups, on the leads handed to them."""
    scope = lead_handover.counselor_scope(user)
    now = await db_now(db)
    return await svc.list_page(db, user, scope, view, day or today_ist(now), now, limit, offset, whose=true())


async def _lead_follow_ups(db: AsyncSession, user: User, lead_id: UUID, scope: list, limit: int, offset: int) -> dict:
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *scope)) is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await svc.lead_page(db, user, lead_id, await db_now(db), limit, offset)


@router.get("/leads/{lead_id}/follow-ups")
async def lead_follow_ups(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _lead_follow_ups(db, user, lead_id, _telecaller_scope(user), limit, offset)


@counselor_router.get("/leads/{lead_id}/follow-ups")
async def counselor_lead_follow_ups(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    return await _lead_follow_ups(db, user, lead_id, lead_handover.counselor_scope(user), limit, offset)


async def _create(db: AsyncSession, user: User, lead: Enquiry, payload: LeadFollowUpCreate) -> dict:
    now = await db_now(db)
    fu = await svc.create(db, user, lead, payload, now)
    await db.commit()
    svc.log("lead_follow_up_created", user, fu.id, lead_id=str(lead.id), reason=payload.reason)
    return await svc.one(db, user, fu.id, now)


@router.post("/leads/{lead_id}/follow-ups", status_code=201)
async def create_follow_up(lead_id: UUID, payload: LeadFollowUpCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry adds a second follow-up; the per-lead cap bounds it)."""
    lead = await lead_pipeline.locked_lead(db, lead_id, *_telecaller_scope(user))
    svc.require_telecaller(user)
    telecaller_leads.require_writable(user, lead)
    return await _create(db, user, lead, payload)


@counselor_router.post("/leads/{lead_id}/follow-ups", status_code=201)
async def counselor_create_follow_up(lead_id: UUID, payload: LeadFollowUpCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A4: `move_to_follow_up` goes through the counselor's stage rules (A2: the lead needs its next action)."""
    lead = await lead_pipeline.locked_lead(db, lead_id, *lead_handover.counselor_scope(user))
    return await _create(db, user, lead, payload)


async def _update(db: AsyncSession, user: User, fu_id: UUID, scope: list, payload: LeadFollowUpUpdate) -> dict:
    """Reschedule or edit an open follow-up. Values equal to the stored ones are not changes (no audit); only a changed due time must be
    in the future, so an overdue follow-up's notes can still be edited."""
    fu = await svc.load_for_write(db, user, fu_id, scope)
    now = await db_now(db)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(key for key, value in changes.items() if getattr(fu, key) != value)
    if "due_at" in changed:
        svc.check_due(changes["due_at"], now)
    for key in changed:
        setattr(fu, key, changes[key])
    if changed:
        svc.audit(db, user, "update", fu.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("lead_follow_up_updated", user, fu_id, fields=changed)
    return await svc.one(db, user, fu_id, now)


async def _complete(db: AsyncSession, user: User, fu_id: UUID, scope: list) -> dict:
    """A second complete meets `done` under the lock -> 409. A call is never needed first (F1)."""
    fu = await svc.load_for_write(db, user, fu_id, scope)
    now = await db_now(db)
    fu.status, fu.completed_at, fu.completed_by_user_id = "done", now, user.id
    svc.audit(db, user, "complete", fu.id)
    await db.commit()
    svc.log("lead_follow_up_completed", user, fu_id)
    return await svc.one(db, user, fu_id, now)


async def _cancel(db: AsyncSession, user: User, fu_id: UUID, scope: list, reason: str) -> dict:
    """The reason is kept and never logged."""
    fu = await svc.load_for_write(db, user, fu_id, scope)
    now = await db_now(db)
    fu.status, fu.cancelled_at, fu.cancel_reason = "cancelled", now, reason
    svc.audit(db, user, "cancel", fu.id)
    await db.commit()
    svc.log("lead_follow_up_cancelled", user, fu_id)
    return await svc.one(db, user, fu_id, now)


@router.patch("/follow-ups/{fu_id}")
async def update_follow_up(fu_id: UUID, payload: LeadFollowUpUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _update(db, user, fu_id, _telecaller_scope(user), payload)


@router.post("/follow-ups/{fu_id}/complete")
async def complete_follow_up(fu_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _complete(db, user, fu_id, _telecaller_scope(user))


@router.post("/follow-ups/{fu_id}/cancel")
async def cancel_follow_up(fu_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _cancel(db, user, fu_id, _telecaller_scope(user), payload.reason)


@counselor_router.patch("/follow-ups/{fu_id}")
async def counselor_update_follow_up(fu_id: UUID, payload: LeadFollowUpUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _update(db, user, fu_id, lead_handover.counselor_scope(user), payload)


@counselor_router.post("/follow-ups/{fu_id}/complete")
async def counselor_complete_follow_up(fu_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _complete(db, user, fu_id, lead_handover.counselor_scope(user))


@counselor_router.post("/follow-ups/{fu_id}/cancel")
async def counselor_cancel_follow_up(fu_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _cancel(db, user, fu_id, lead_handover.counselor_scope(user), payload.reason)
