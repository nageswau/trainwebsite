"""rec-028 (DEC-SCOPE-134, spec §3): recruiter meetings with a company -- the four lists, a company's meetings, the participant picker,
schedule, edit/reschedule, outcome and cancel.

Scope is the company's (rec-003 `caller_scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the company
lock, `can_edit` (MT9), the meeting lock and state, validation, change, history, audit, one commit here, log."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import User
from app.schemas import BdmAppointmentReason, RecMeetingCreate, RecMeetingOutcome, RecMeetingUpdate
from app.services import recruiter_companies as companies
from app.services import recruiter_meetings as svc
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-meetings"])


@router.get("/meetings")
async def list_meetings(
    view: Literal["upcoming", "awaiting_outcome", "completed", "cancelled"] = "upcoming",
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MT10: a recruiter's own companies, a manager's team and the unassigned queue (read only), the assigned BDM's companies (read
    only), super_admin all."""
    return await svc.list_page(db, user, view, await db_now(db), limit, offset)


@router.get("/meetings/recruiter-options")
async def recruiter_options(q: str | None = SEARCH, limit: int = LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MT5's picker: active placement users, names only. For the people who can create companies (recruiters, managers, super_admin)."""
    companies.require_creator(user)
    return await svc.recruiter_options(db, _matching(like_pattern(q), User.full_name), limit)


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.check_readable(db, user, meeting_id)
    return await svc.one(db, user, meeting_id, await db_now(db))


@router.get("/companies/{company_id}/meetings")
async def company_meetings(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.load_scoped(db, user, company_id)
    return await svc.company_page(db, user, company_id, await db_now(db), limit, offset)


@router.post("/companies/{company_id}/meetings", status_code=201)
async def schedule_meeting(company_id: UUID, payload: RecMeetingCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry schedules a second meeting). AC1: the company moves to Meeting Scheduled when earlier in the pipeline."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "meeting_create")
    now = await db_now(db)
    meeting = await svc.create(db, user, company, payload, now)
    await db.commit()
    svc.log("recruiter_meeting_scheduled", user, meeting.id, company_id=str(company_id), meeting_type=payload.meeting_type)
    return await svc.one(db, user, meeting.id, now)


@router.patch("/meetings/{meeting_id}")
async def update_meeting(meeting_id: UUID, payload: RecMeetingUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Edit or reschedule a scheduled meeting (MT6). Values equal to the stored ones are not changes (no audit, no history)."""
    company, meeting = await svc.load_for_write(db, user, meeting_id, "meeting_update")
    now = await db_now(db)
    changed = await svc.update(db, user, company, meeting, payload, now)
    await db.commit()
    if changed:
        svc.log("recruiter_meeting_updated", user, meeting_id, fields=changed)
    return await svc.one(db, user, meeting_id, now)


@router.post("/meetings/{meeting_id}/outcome")
async def record_outcome(meeting_id: UUID, payload: RecMeetingOutcome, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MT7 / AC2: a second outcome meets `completed` under the lock -> 409."""
    company, meeting = await svc.load_for_write(db, user, meeting_id, "meeting_outcome")
    now = await db_now(db)
    await svc.record_outcome(db, user, company, meeting, payload, now)
    await db.commit()
    svc.log("recruiter_meeting_completed", user, meeting_id, with_next_action=meeting.follow_up_id is not None)
    return await svc.one(db, user, meeting_id, now)


@router.post("/meetings/{meeting_id}/cancel")
async def cancel_meeting(meeting_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MT6: the reason is kept and never logged."""
    _, meeting = await svc.load_for_write(db, user, meeting_id, "meeting_cancel")
    now = await db_now(db)
    svc.cancel(db, user, meeting, payload.reason, now)
    await db.commit()
    svc.log("recruiter_meeting_cancelled", user, meeting_id)
    return await svc.one(db, user, meeting_id, now)
