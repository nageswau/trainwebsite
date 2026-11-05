"""rec-020 (DEC-SCOPE-148, spec §3): interviews -- the four lists, one interview, an application's interviews, schedule, edit, reschedule and
status.

Scope is the requirement's (rec-007 `caller_scope` through rec-017's `load_scoped`; other roles 403, out of scope 404). Every write is one
transaction -- scope, the application lock, the writer (403), the candidate lock and clash when a time is set, the interview lock and
state, validation, change, history, side effects, audit, one commit here; then the queued emails are published and the event logged."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user, require_permission
from app.api.portfolio_certificates import HEADERS as DOWNLOAD_HEADERS
from app.core.database import get_db
from app.models import User
from app.notifications.dispatch import enqueue_recruiter_email
from app.schemas import (
    InterviewPanelFeedbackIn,
    InterviewPanelIn,
    InterviewResultRelease,
    InterviewResultSettingsIn,
    RecInterviewCancel,
    RecInterviewCreate,
    RecInterviewFeedbackIn,
    RecInterviewReschedule,
    RecInterviewStatusChange,
    RecInterviewUpdate,
)
from app.services import applications, candidates
from app.services import interview_panel as panel
from app.services import interview_results as results
from app.services import interviews as svc
from app.services import profile_sharing as sharing
from app.services.bdm_appointments import db_now
from app.services.stale_guard import require_fresh

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
    """hrc-028 (I5): a change the candidate can see notifies them (`notify`); the reply is the interview, plus `notifications` when sent."""
    interview, application, job = await svc.load_for_write(db, user, interview_id, "interview_update")

    async def current() -> dict:
        return await svc.one(db, user, interview_id, await db_now(db))

    await require_fresh(db, stored=interview.updated_at, expected=payload.expected_updated_at, entity=("interview", interview.id),
                        action_prefix="recruiter_interview.", since=payload.expected_updated_at, current=current)
    changed = await svc.update(db, user, interview, job, payload)
    notices, emails = None, []
    if payload.notify and set(changed) & set(svc.VISIBLE):
        notices, emails = await svc.notify(db, user, interview, application, job, "updated", True)
    await db.commit()
    _publish(emails)
    if changed:
        svc.log("recruiter_interview_updated", user, interview_id, fields=changed, notices=notices)
    out = await svc.one(db, user, interview_id, await db_now(db))
    return out if notices is None else {**out, "notifications": notices}


@router.post("/interviews/{interview_id}/cancel")
async def cancel_interview(interview_id: UUID, payload: RecInterviewCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-028 (I3): from Scheduled, Confirmed, Rescheduled or On Hold (409 otherwise); the reason is required, shown to the candidate and
    never logged; the notice carries a CANCEL invite."""
    interview, application, job = await svc.load_for_write(db, user, interview_id, "interview_cancel")
    previous = svc.cancel(db, user, interview, payload.reason)
    notices, emails = await svc.notify(db, user, interview, application, job, "cancelled", payload.notify)
    await db.commit()
    _publish(emails)
    svc.log("recruiter_interview_cancelled", user, interview_id, from_status=previous, notices=notices)
    return {"interview": await svc.one(db, user, interview_id, await db_now(db)), "notifications": notices}


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
    previous = await svc.change_status(db, user, interview, application, payload.status, payload.note, now)
    await db.commit()
    _publish(results.take_emails(db))  # hrc-030 (R4): an auto-released result's email
    svc.log("recruiter_interview_status_changed", user, interview_id, from_status=previous, to_status=payload.status)
    return {"interview": await svc.one(db, user, interview_id, now)}


@router.put("/interviews/{interview_id}/feedback")
async def save_interview_feedback(interview_id: UUID, payload: RecInterviewFeedbackIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """rec-021 (FB1-FB4; AC1): the whole form replaces the one current feedback; a decision moves the interview as the status route does.
    The text is never logged."""
    interview, application, _job = await svc.load_for_write(db, user, interview_id, "interview_feedback")
    now = await db_now(db)
    sent = payload.model_dump()
    previous = await svc.save_feedback(db, user, interview, application, sent, now)
    await db.commit()
    _publish(results.take_emails(db))
    svc.log("recruiter_interview_feedback_saved", user, interview_id, final_decision=sent["final_decision"], from_status=previous)
    return {"interview": await svc.one(db, user, interview_id, now)}


# --- hrc-029 (DEC-SCOPE-405): the interview panel -------------------------------------------------------------------------------------
@router.get("/interviews/{interview_id}/interviewer-options")
async def interviewer_options(interview_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V2: the internal interviewers and the requirement company's employer users a writer can assign."""
    job = await panel.load_for_options(db, user, interview_id)
    return {"items": await panel.options(db, job)}


@router.put("/interviews/{interview_id}/interviewers")
async def assign_interviewers(interview_id: UUID, payload: InterviewPanelIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V3: the whole panel replaces the saved one; newly added people are notified (V10)."""
    interview, application, job = await svc.load_for_write(db, user, interview_id, "interview_panel")
    added = await panel.assign(db, user, interview, application, job, payload.interviewers)
    await db.commit()
    svc.log("recruiter_interview_panel_saved", user, interview_id, size=len(payload.interviewers), added=len(added))
    return {"interview": await svc.one(db, user, interview_id, await db_now(db))}


# --- hrc-030 (DEC-SCOPE-409 R4-R7, R11): the result queue, publishing and the release switch --------------------------------------------
results_router = APIRouter(prefix="/recruiter/interview-results", tags=["recruiter-interviews"])
RELEASER = require_permission("results", "release", "You cannot publish interview results")


@results_router.get("")
async def result_queue(state: Literal["pending_approval", "released"] = "pending_approval", limit: int = LIMIT, offset: int = OFFSET,
                       user: User = Depends(RELEASER), db: AsyncSession = Depends(get_db)):  # fmt: skip
    return await results.queue(db, user, state, limit, offset)


@results_router.get("/settings")
async def result_settings(user: User = Depends(RELEASER), db: AsyncSession = Depends(get_db)):
    return await results.settings_out(db, user)


@results_router.put("/settings")
async def save_result_settings(payload: InterviewResultSettingsIn, user: User = Depends(RELEASER), db: AsyncSession = Depends(get_db)):
    await results.save_settings(db, user, payload.auto_release)
    await db.commit()
    svc.log("interview_result_settings_saved", user, None, auto_release=payload.auto_release)
    return await results.settings_out(db, user)


@results_router.post("/{result_id}/release")
async def release_result(result_id: UUID, payload: InterviewResultRelease, user: User = Depends(RELEASER), db: AsyncSession = Depends(get_db)):
    """R6/R7: publish once (409 after); never the approver's own decision (403). The message is never logged."""
    row = await results.release(db, user, result_id, payload.candidate_message)
    await db.commit()
    _publish(results.take_emails(db))
    svc.log("interview_result_released", user, row.interview_id, result_id=str(result_id), outcome=row.outcome)
    return await results.one(db, user, result_id)


interviewer_router = APIRouter(prefix="/interviewer", tags=["interviewer"])


@interviewer_router.get("/interviews")
async def my_interviews(view: Literal["upcoming", "past"] = "upcoming", limit: int = LIMIT, offset: int = OFFSET,
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    """V6: the interviews the caller (an internal interviewer or an employer user) is assigned to; other roles 403."""
    return await panel.list_page(db, user, view, await db_now(db), limit, offset)


@interviewer_router.get("/interviews/{interview_id}")
async def my_interview(interview_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V6: not assigned = 404, the same as a missing id."""
    return await panel.one(db, user, interview_id, await db_now(db))


@interviewer_router.get("/interviews/{interview_id}/resume")
async def my_interview_resume(interview_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V4/V5: the resume version shared with the caller, inside the access window; audited before any byte leaves."""
    resume, candidate = await panel.resume(db, user, interview_id, await db_now(db))
    data = candidates.read_file(resume)
    await db.commit()
    svc.log("interviewer_resume_downloaded", user, interview_id)
    name = sharing.resume_name(candidate, resume)
    return Response(content=data, media_type=resume.content_type, headers={**DOWNLOAD_HEADERS, "Content-Disposition": f'attachment; filename="{name}"'})


@interviewer_router.put("/interviews/{interview_id}/feedback")
async def save_my_feedback(interview_id: UUID, payload: InterviewPanelFeedbackIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V7: the caller's own feedback, created or replaced; never moves the interview (V8). The notes are never logged."""
    now = await db_now(db)
    changed = await panel.save_feedback(db, user, interview_id, payload.model_dump(), now)
    await db.commit()
    svc.log("interviewer_feedback_saved", user, interview_id, fields=changed)
    return await panel.one(db, user, interview_id, now)
