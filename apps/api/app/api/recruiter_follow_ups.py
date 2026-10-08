"""rec-024 (DEC-SCOPE-131, spec §3): recruiter follow-ups -- the Today / Overdue / Upcoming lists, a company's follow-ups, create,
reschedule/edit, complete and cancel.

Scope is the company's (rec-003 `caller_scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the company
lock, `can_edit` (FU3), the follow-up lock and state, validation, change, audit, one commit here, log."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmAppointmentReason, RecFollowUpComplete, RecFollowUpCreate, RecFollowUpUpdate
from app.services import recruiter_companies as companies
from app.services import recruiter_follow_ups as svc
from app.services.bdm_appointments import db_now
from app.services.lead_follow_ups import check_due

router = APIRouter(prefix="/recruiter", tags=["recruiter-follow-ups"])


@router.get("/follow-ups")
async def list_follow_ups(
    due: Literal["today", "overdue", "upcoming"] = "today",
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§18 "automatically generate the daily follow-up list" (AC1, FU2): computed on every read in IST. A recruiter's own companies, a
    manager's team and the unassigned queue (read only), the assigned BDM's companies (read only), super_admin all."""
    return await svc.list_page(db, user, due, await db_now(db), limit, offset)


@router.get("/companies/{company_id}/follow-ups")
async def company_follow_ups(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.load_scoped(db, user, company_id)
    return await svc.company_page(db, user, company_id, await db_now(db), limit, offset)


@router.post("/companies/{company_id}/follow-ups", status_code=201)
async def create_follow_up(company_id: UUID, payload: RecFollowUpCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry adds a second follow-up; the per-company cap bounds it)."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "follow_up_create")
    now = await db_now(db)
    fu = await svc.create(db, user, company, payload, now)
    await db.commit()
    svc.log("recruiter_follow_up_created", user, fu.id, company_id=str(company_id), reason=payload.reason)
    return await svc.one(db, user, fu.id, now)


@router.patch("/follow-ups/{fu_id}")
async def update_follow_up(fu_id: UUID, payload: RecFollowUpUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Reschedule (FU5) or edit an open follow-up. Values equal to the stored ones are not changes (no audit); only a changed due time
    must be in the future, so an overdue follow-up's notes can still be edited."""
    company, fu = await svc.load_for_write(db, user, fu_id, "follow_up_update")
    now = await db_now(db)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(key for key, value in changes.items() if getattr(fu, key) != value)
    if "due_at" in changed:
        check_due(changes["due_at"], now)
    await svc.check_links(db, company.id, {k: changes[k] for k in changed}, fu)
    for key in changed:
        setattr(fu, key, changes[key])
    if changed:
        svc.audit(db, user, "update", fu.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("recruiter_follow_up_updated", user, fu_id, fields=changed)
    return await svc.one(db, user, fu_id, now)


@router.post("/follow-ups/{fu_id}/complete")
async def complete_follow_up(fu_id: UUID, payload: RecFollowUpComplete, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """FU7. The company's next follow-up moves on by itself (FU9, AC2). A second complete meets `done` under the lock -> 409."""
    _, fu = await svc.load_for_write(db, user, fu_id, "follow_up_complete")
    now = await db_now(db)
    fu.status, fu.completed_at, fu.completed_by_user_id, fu.outcome = "done", now, user.id, payload.outcome
    svc.audit(db, user, "complete", fu.id, {"with_outcome": payload.outcome is not None})
    await db.commit()
    svc.log("recruiter_follow_up_completed", user, fu_id)
    return await svc.one(db, user, fu_id, now)


@router.post("/follow-ups/{fu_id}/cancel")
async def cancel_follow_up(fu_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """FU7: the reason is kept and never logged."""
    _, fu = await svc.load_for_write(db, user, fu_id, "follow_up_cancel")
    now = await db_now(db)
    fu.status, fu.cancelled_at, fu.cancel_reason = "cancelled", now, payload.reason
    svc.audit(db, user, "cancel", fu.id)
    await db.commit()
    svc.log("recruiter_follow_up_cancelled", user, fu_id)
    return await svc.one(db, user, fu_id, now)
