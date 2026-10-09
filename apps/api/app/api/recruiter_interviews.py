"""rec-020 (DEC-SCOPE-139, spec §3): interviews -- the four lists, one interview, an application's interviews, schedule, edit, reschedule and
status.

Scope is the requirement's (rec-007 `caller_scope` through rec-017's `load_scoped`; other roles 403, out of scope 404). Every write is one
transaction -- scope, the application lock, the writer (403), the candidate lock and clash when a time is set, the interview lock and
state, validation, change, history, side effects, audit, one commit here; then the queued emails are published and the event logged."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.notifications.dispatch import enqueue_recruiter_email
from app.schemas import RecInterviewCreate, RecInterviewReschedule, RecInterviewStatusChange, RecInterviewUpdate
from app.services import applications
from app.services import interviews as svc
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-interviews"])


def _publish(message_ids: list[UUID]) -> None:
    """After the commit (rec-026 MS7): a broker failure leaves the email queued for the sweep."""
    for message_id in message_ids:
        enqueue_recruiter_email(message_id)


@router.get("/interviews")
async def list_interviews(
    view: Literal["upcoming", "awaiting_update", "on_hold", "closed"] = "upcoming",
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """IV12: a recruiter's requirements, a manager's team and the unassigned queue (read only), the assigned BDM's (read only),
    super_admin all."""
    return await svc.list_page(db, user, view, await db_now(db), limit, offset)


@router.get("/interviews/{interview_id}")
async def get_interview(interview_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.check_readable(db, user, interview_id)
    return await svc.one(db, user, interview_id, await db_now(db))


@router.get("/applications/{application_id}/interviews")
async def application_interviews(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, job = await applications.load_scoped(db, user, application_id)
    return await svc.for_application(db, user, application, job, await db_now(db))


@router.post("/interviews", status_code=201)
async def schedule_interview(payload: RecInterviewCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry is refused by the clash, since it is the same candidate at the same time)."""
    application, job = await applications.load_scoped(db, user, payload.application_id, lock=True)
    applications.require_writer(user, application.id, "interview_create")
    now = await db_now(db)
    interview = await svc.create(db, user, application, job, payload, now)
    notices, emails = await svc.notify(db, user, interview, application, job, "scheduled", payload.notify)
    await db.commit()
    _publish(emails)
    svc.log("recruiter_interview_scheduled", user, interview.id, application_id=str(application.id), round=payload.round, notices=notices)
    return {"interview": await svc.one(db, user, interview.id, now), "notifications": notices}


@router.patch("/interviews/{interview_id}")
async def update_interview(interview_id: UUID, payload: RecInterviewUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    interview, _application, job = await svc.load_for_write(db, user, interview_id, "interview_update")
    changed = await svc.update(db, user, interview, job, payload)
    await db.commit()
    if changed:
        svc.log("recruiter_interview_updated", user, interview_id, fields=changed)
    return await svc.one(db, user, interview_id, await db_now(db))


@router.post("/interviews/{interview_id}/reschedule")
async def reschedule_interview(interview_id: UUID, payload: RecInterviewReschedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """IV4 / AC1: the old and new times are kept on the event; the reason is never logged."""
    interview, application, job = await svc.load_for_write(db, user, interview_id, "interview_reschedule")
    now = await db_now(db)
    await svc.reschedule(db, user, interview, application, payload.scheduled_at, payload.reason, now)
    notices, emails = await svc.notify(db, user, interview, application, job, "rescheduled", payload.notify)
    await db.commit()
    _publish(emails)
    svc.log("recruiter_interview_rescheduled", user, interview_id, notices=notices)
    return {"interview": await svc.one(db, user, interview_id, now), "notifications": notices}


@router.post("/interviews/{interview_id}/status")
async def change_interview_status(interview_id: UUID, payload: RecInterviewStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """IV3 / AC2; IV8 feeds the application."""
    interview, application, _job = await svc.load_for_write(db, user, interview_id, "interview_status")
    now = await db_now(db)
    previous = svc.change_status(db, user, interview, application, payload.status, payload.note, now)
    await db.commit()
    svc.log("recruiter_interview_status_changed", user, interview_id, from_status=previous, to_status=payload.status)
    return {"interview": await svc.one(db, user, interview_id, now)}
