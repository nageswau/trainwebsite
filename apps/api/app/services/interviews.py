"""rec-020 (DEC-SCOPE-148, spec §1-§3): interview management -- rounds, statuses and their moves, reschedule with history, the per-candidate
clash, the side effects on the application (rec-017) and the company (rec-005), the notices (Q-20), the lists and the output.

An interview belongs to its application, so every recruiter read and write resolves through rec-017's `load_scoped` (rec-007's
requirement scope: out of scope = the same 404 as missing). The legacy /workflows and employer routes come through `insert`, so every
interview gets its code, its first event and the clash check. Lock order: the application, then the candidate (when a time is set), then
the interview. Functions only; nothing here commits -- the route owns the transaction. Logs and audit carry ids, keys and field names,
never a note, a reason, a name or an address."""

import logging
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models import (
    FEEDBACK_DECISIONS,
    AuditLog,
    Candidate,
    Company,
    CompanyContact,
    Interview,
    InterviewEvent,
    InterviewFeedback,
    InterviewInterviewer,
    InterviewPanelFeedback,
    Job,
    JobApplication,
    Notification,
    RecruiterMessage,
    User,
)
from app.notifications.dispatch import queue_deliveries
from app.schemas import RecInterviewCreate, RecInterviewUpdate
from app.services import applications, calendar_ics, company_pipeline, contact_status, mailer, recruiter_companies, recruitment_history
from app.services import recruiter_requirements as requirements

logger = logging.getLogger("app.recruiter")

ROUND_LABELS = {"hr_round": "HR Round", "technical_round": "Technical Round", "manager_round": "Manager Round", "final_round": "Final Round", "client_round": "Client Round"}
STATUS_LABELS = {
    "scheduled": "Scheduled", "confirmed": "Confirmed", "completed": "Completed", "rescheduled": "Rescheduled", "no_show": "No Show",
    "selected": "Selected", "rejected": "Rejected", "on_hold": "On Hold", "cancelled": "Cancelled",
}
# hrc-028 (DEC-SCOPE-400 I1): the meeting platforms, in the models' order
PLATFORM_LABELS = {"google_meet": "Google Meet", "microsoft_teams": "Microsoft Teams", "zoom": "Zoom", "zoho_meeting": "Zoho Meeting", "other": "Other"}
OPEN = ("scheduled", "confirmed", "rescheduled")
MOVES = {  # IV3: target -> the statuses it may come from
    "confirmed": ("scheduled", "rescheduled"),
    "completed": OPEN,
    "no_show": OPEN,
    "on_hold": (*OPEN, "completed"),
    "selected": ("completed", "on_hold"),
    "rejected": ("completed", "on_hold"),
}
AFTER_START = ("completed", "no_show", "selected", "rejected")  # AC2: only once the scheduled time has passed
FINAL = ("selected", "rejected")
CANCELLABLE = (*OPEN, "on_hold")  # hrc-028 (I3): not yet held; a cancelled interview is final
CLOSED = (*FINAL, "cancelled")  # no edit
# hrc-028 (I5): the PATCH fields the candidate reads -- a change to one of them notifies
VISIBLE = ("round", "round_number", "mode", "platform", "meeting_url", "location", "phone_details", "instructions", "documents_required", "ends_at",
           "time_zone", "interviewer")  # fmt: skip
MAX_LENGTH = timedelta(hours=12)
DEFAULT_LENGTH = timedelta(minutes=60)  # the invite's end when none is set


def unreleased_status(status: str) -> str:
    """hrc-001 (DEC-SCOPE-371 H3): until hrc-030 adds the release step, a decision reads as Completed outside the staff screens."""
    return "completed" if status in (*FINAL, "on_hold") else status
RESCHEDULABLE = (*OPEN, "on_hold", "no_show")
DECIDING_ROUNDS = ("final_round", "client_round")  # IV8: only these rounds' Selected selects the application
# rec-021 (DEC-SCOPE-175): FB2 -- first recorded on a Completed interview, then editable while the decision it led to stands
FEEDBACK_EDITABLE = ("completed", *FEEDBACK_DECISIONS)
FEEDBACK_FIELDS = (
    "technical_rating", "communication_rating", "overall_rating", "strengths", "weaknesses", "recruiter_comments", "company_feedback",
    "next_round", "final_decision",
)
IST = ZoneInfo("Asia/Kolkata")
INVITE_KIND = "interview_invite"  # hrc-028 (I6): the delivery context the worker sends through the mailer with the .ics

NOT_FOUND = "Interview not found"
CLASH = "This candidate already has an interview scheduled at this time"
NOT_STARTED = "You can mark this once the interview time has passed"
APPLICATION_CLOSED = "Interviews can be scheduled only for an open application"
REQUIREMENT_ENDED = "Interviews cannot be scheduled on a closed or cancelled requirement"
DECIDED = "This interview is already decided"
CANCELLED = "This interview is cancelled"
NOT_CANCELLABLE = "Only an interview that has not been held can be cancelled"
END_ORDER = "Choose an end time after the start, within 12 hours"
SAME_TIME = "Choose a different time to reschedule"
CONTACT_INVALID = "Choose an active contact of this requirement's company"
TIME_PAST = "Choose an interview time in the future"
TIME_FAR = "Choose an interview time within the next 12 months"
NOT_COMPLETED = "Feedback can be recorded once the interview is Completed"


HORIZON = timedelta(days=366)  # tel-011's horizon, as rec-028's meetings (not imported: workflows.py -> here must not reach the telecaller modules)


def field_error(field: str, msg: str, value=None) -> RequestValidationError:
    """The validation-error shape, so the form can place a service rule on its field."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_time(when: datetime, now: datetime) -> None:
    """IV4 / IV5: in the future and within 366 days."""
    if when <= now or when > now + HORIZON:
        raise field_error("scheduled_at", TIME_PAST if when <= now else TIME_FAR, when.isoformat())


def check_end(start: datetime, end: datetime | None) -> None:
    """hrc-028 (I1): after the start and at most 12 hours later (ck_interviews_ends_after_start)."""
    if end is not None and not start < end <= start + MAX_LENGTH:
        raise field_error("ends_at", END_ORDER, end.isoformat())


def round_label(key: str | None) -> str | None:
    return ROUND_LABELS.get(key, key) if key else None


def round_text(interview: Interview) -> str:
    """The round as the candidate reads it: "HR Round (round 2)"."""
    label = round_label(interview.round) or "Interview"
    return f"{label} (round {interview.round_number})" if interview.round_number else label


def local_when(interview: Interview) -> str:
    """hrc-028 (I2): the start and end in the candidate's zone with its UTC offset -- "12 Nov 2026, 10:00 AM – 11:00 AM Asia/Dubai (UTC+04:00)"."""
    zone = ZoneInfo(interview.time_zone) if interview.time_zone else IST
    start = interview.scheduled_at.astimezone(zone)
    text = f"{start:%d %b %Y, %I:%M %p}"
    if interview.ends_at is not None:
        end = interview.ends_at.astimezone(zone)
        text += f" – {end:%I:%M %p}" if end.date() == start.date() else f" – {end:%d %b %Y, %I:%M %p}"
    offset = start.strftime("%z")
    return f"{text} {'IST' if zone == IST else zone.key} (UTC{offset[:3]}:{offset[3:]})"


def status_label(key: str) -> str:
    return STATUS_LABELS.get(key, key)


def allowed(interview: Interview, now: datetime) -> list[str]:
    """The moves open now: from the current status, and the after-start ones only once the time has passed."""
    return [t for t, sources in MOVES.items() if interview.status in sources and (t not in AFTER_START or interview.scheduled_at <= now)]


# --- the core: clash, insert, events ------------------------------------------------------------------------------------------------
async def check_clash(db: AsyncSession, candidate_id: UUID, when: datetime, exclude: UUID | None = None) -> None:
    """IV6: another open interview of the candidate (on any requirement) at the same minute. The candidate row lock serialises it."""
    await db.execute(select(Candidate.id).where(Candidate.id == candidate_id).with_for_update())
    stmt = (
        select(Interview.id)
        .join(JobApplication, JobApplication.id == Interview.application_id)
        .where(
            JobApplication.candidate_id == candidate_id,
            Interview.status.in_(OPEN),
            func.date_trunc("minute", Interview.scheduled_at) == when.replace(second=0, microsecond=0),
        )
    )
    if exclude is not None:
        stmt = stmt.where(Interview.id != exclude)
    if await db.scalar(stmt.limit(1)):
        raise HTTPException(409, CLASH)


def _event(db: AsyncSession, interview: Interview, actor: User | None, event: str, *, from_status=None, old=None, note=None, **link) -> None:
    """`link`: a `details` event's old and new meeting link / location (hrc-028 I4)."""
    db.add(InterviewEvent(
        interview_id=interview.id, event=event, from_status=from_status, to_status=interview.status,
        old_scheduled_at=old, new_scheduled_at=interview.scheduled_at if event in ("scheduled", "rescheduled") else None, note=note,
        actor_user_id=actor.id if actor else None, **link,
    ))


async def insert(db: AsyncSession, actor: User, application: JobApplication, scheduled_at: datetime, **fields) -> Interview:
    """Every creator (recruiter, legacy staff, employer): the clash, the row (the database numbers it) and its `scheduled` event."""
    await check_clash(db, application.candidate_id, scheduled_at)
    interview = Interview(application_id=application.id, scheduled_at=scheduled_at, status="scheduled", created_by_user_id=actor.id, **fields)
    db.add(interview)
    await db.flush()
    _event(db, interview, actor, "scheduled")
    return interview


# --- recruiter writes ---------------------------------------------------------------------------------------------------------------
async def _check_contact(db: AsyncSession, company_id: UUID, contact_id: UUID | None, kept: UUID | None = None) -> None:
    if contact_id is None or contact_id == kept:
        return
    found = await db.scalar(select(CompanyContact.id).where(CompanyContact.id == contact_id, CompanyContact.company_id == company_id, CompanyContact.active))
    if found is None:
        raise field_error("contact_id", CONTACT_INVALID, str(contact_id))


async def create(db: AsyncSession, user: User, application: JobApplication, job: Job, payload: RecInterviewCreate, now: datetime) -> Interview:
    """IV5: the caller locked the application and checked the writer. Then the side effects (IV8): the application to Interview, the
    company to Interview (forward only)."""
    if job.status in requirements.ENDED:
        raise HTTPException(409, REQUIREMENT_ENDED)
    if application.status not in applications.OPEN:
        raise HTTPException(409, APPLICATION_CLOSED)
    check_time(payload.scheduled_at, now)
    check_end(payload.scheduled_at, payload.ends_at)
    await _check_contact(db, job.company_id, payload.contact_id)
    fields = payload.model_dump(exclude={"application_id", "scheduled_at", "notify"})
    interview = await insert(db, user, application, payload.scheduled_at, **fields)
    applications.follow(db, user, application, "interview", f"Interview scheduled: {ROUND_LABELS[payload.round]}")
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update().execution_options(populate_existing=True))
    moved = await company_pipeline.apply_event(db, company, "interview_scheduled", user)
    audit(db, user, "create", interview, {"application_id": str(application.id), "round": payload.round, "mode": payload.mode, "stage_moved": moved})
    return interview


async def load_for_write(db: AsyncSession, user: User, interview_id: UUID, route: str) -> tuple[Interview, JobApplication, Job]:
    """In scope (404) -> the application lock -> the writer (403) -> the interview lock."""
    application_id = await db.scalar(select(Interview.application_id).where(Interview.id == interview_id))
    if application_id is None:
        raise HTTPException(404, NOT_FOUND)
    application, job = await _scoped(db, user, application_id, lock=True)
    applications.require_writer(user, interview_id, route)
    interview = await db.scalar(select(Interview).where(Interview.id == interview_id).with_for_update().execution_options(populate_existing=True))
    return interview, application, job


async def update(db: AsyncSession, user: User, interview: Interview, job: Job, payload: RecInterviewUpdate) -> list[str]:
    """Only changed values count (no audit for none). Returns the changed field names. hrc-028 (I4): a changed link or location is kept,
    old and new, on a `details` event (staff history only)."""
    if interview.status in CLOSED:
        raise HTTPException(409, CANCELLED if interview.status == "cancelled" else DECIDED)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_updated_at", "notify"})
    changed = sorted(key for key, value in changes.items() if getattr(interview, key) != value)
    if "contact_id" in changed:
        await _check_contact(db, job.company_id, changes["contact_id"], kept=interview.contact_id)
    if "ends_at" in changed:
        check_end(interview.scheduled_at, changes["ends_at"])
    before = {key: getattr(interview, key) for key in changed}
    for key in changed:
        setattr(interview, key, changes[key])
    if {"meeting_url", "location"} & set(changed):
        _event(db, interview, user, "details", from_status=interview.status, old_meeting_url=before.get("meeting_url", interview.meeting_url),
               new_meeting_url=interview.meeting_url, old_location=before.get("location", interview.location), new_location=interview.location)
    if changed:
        audit(db, user, "update", interview, {"fields": changed, "changes": recruitment_history.diff(before, {key: changes[key] for key in changed})})
    return changed


async def reschedule(db: AsyncSession, user: User | None, interview: Interview, application: JobApplication, when: datetime, reason: str | None,
                     now: datetime | None) -> None:
    """IV4 / AC1: a new time (future and within a year, unless `now` is None -- the legacy PATCH), the clash, status Rescheduled and the
    old -> new event."""
    if interview.status not in RESCHEDULABLE:
        raise HTTPException(409, DECIDED if interview.status in FINAL else f"A {status_label(interview.status)} interview cannot be rescheduled")
    if now is not None:
        check_time(when, now)
    if when == interview.scheduled_at:
        raise field_error("scheduled_at", SAME_TIME, when.isoformat())
    await check_clash(db, application.candidate_id, when, exclude=interview.id)
    old, previous = interview.scheduled_at, interview.status
    if interview.ends_at is not None:  # hrc-028 (I2): the duration is kept
        interview.ends_at = when + (interview.ends_at - old)
    interview.scheduled_at, interview.status = when, "rescheduled"
    _event(db, interview, user, "rescheduled", from_status=previous, old=old, note=reason)
    if user is not None:
        audit(db, user, "reschedule", interview, {"from_status": previous, "changes": recruitment_history.diff(
            {"scheduled_at": old, "status": previous}, {"scheduled_at": when, "status": "rescheduled"})})


def cancel(db: AsyncSession, user: User, interview: Interview, reason: str) -> str:
    """hrc-028 (I3): from a status not yet held (409 otherwise); a `status` event carries the reason (never logged or audited as text). The
    application does not move -- another round can be scheduled. Returns the previous status."""
    if interview.status not in CANCELLABLE:
        raise HTTPException(409, CANCELLED if interview.status == "cancelled" else NOT_CANCELLABLE)
    previous = interview.status
    interview.status, interview.cancel_reason = "cancelled", reason
    _event(db, interview, user, "status", from_status=previous, note=reason)
    audit(db, user, "cancel", interview, {"from": previous, "to": "cancelled", "changes": {"status": [previous, "cancelled"]}})
    return previous


def change_status(db: AsyncSession, user: User | None, interview: Interview, application: JobApplication, target: str, note: str | None, now: datetime) -> str:
    """IV3 / AC2: the move (409), then the time (422). IV8: Rejected rejects the application; Selected selects it on a deciding round.
    Returns the previous status."""
    if interview.status not in MOVES[target]:
        raise HTTPException(409, f"An interview cannot move from {status_label(interview.status)} to {status_label(target)}")
    if target in AFTER_START and interview.scheduled_at > now:
        raise HTTPException(422, NOT_STARTED)
    previous = interview.status
    interview.status = target
    _event(db, interview, user, "status", from_status=previous, note=note)
    label = round_label(interview.round) or "Interview"
    if target == "rejected" or (target == "selected" and interview.round in DECIDING_ROUNDS):
        applications.follow(db, user, application, target, f"{label}: {status_label(target)}")
    if user is not None:
        audit(db, user, "status", interview, {"from": previous, "to": target, "changes": {"status": [previous, target]}})
    return previous


async def legacy_update(db: AsyncSession, user: User, interview: Interview, application: JobApplication, scheduled_at: datetime | None,
                        result: str | None, now: datetime) -> None:
    """IV11: the legacy PATCH keeps its fields -- a changed time on a reschedulable interview is a reschedule (the clash applies, the
    future-time rule does not); on a decided one it is stored as before. A result the catalogue knows also sets the status when the move is
    allowed now; otherwise only `result` changes, as it always did."""
    if scheduled_at is not None and scheduled_at != interview.scheduled_at:
        if interview.status in RESCHEDULABLE:
            await reschedule(db, user, interview, application, scheduled_at, None, None)
        else:
            interview.scheduled_at = scheduled_at
    if result in allowed(interview, now):
        previous = interview.status
        interview.status = result
        _event(db, interview, user, "status", from_status=previous)


# --- feedback (rec-021, FB1-FB4) ----------------------------------------------------------------------------------------------------
async def _feedback_row(db: AsyncSession, interview_id: UUID) -> InterviewFeedback | None:
    stmt = select(InterviewFeedback).where(InterviewFeedback.interview_id == interview_id).execution_options(populate_existing=True)
    return await db.scalar(stmt)


def can_feedback(user: User, status: str, recorded: bool) -> bool:
    return applications.can_write(user) and (status == "completed" or (recorded and status in FEEDBACK_EDITABLE))


async def save_feedback(db: AsyncSession, user: User, interview: Interview, application: JobApplication, sent: dict, now: datetime) -> str | None:
    """The caller holds `load_for_write`'s locks. FB2 (409), FB4 the decision's move through `change_status` (its 409 refuses changing a
    decided outcome, before anything is written), FB1 the one row replaced and audited by field name. Returns the previous status when
    the decision moved it."""
    row = await _feedback_row(db, interview.id)
    if interview.status != "completed" and not (row is not None and interview.status in FEEDBACK_EDITABLE):
        raise HTTPException(409, NOT_COMPLETED)
    decision = sent["final_decision"]
    previous = change_status(db, user, interview, application, decision, "Feedback", now) if decision and decision != interview.status else None
    changed = [f for f in FEEDBACK_FIELDS if row is None or getattr(row, f) != sent[f]]
    before = {f: getattr(row, f) for f in FEEDBACK_FIELDS} if row is not None else {}  # hrc-004: feedback text is redacted
    if changed:
        if row is None:
            row = InterviewFeedback(interview_id=interview.id, recorded_by_user_id=user.id)
            db.add(row)
        for field in FEEDBACK_FIELDS:
            setattr(row, field, sent[field])
        row.recorded_by_user_id = user.id  # updated_at: TimestampMixin's onupdate
        audit(db, user, "feedback", interview, {"fields": sorted(changed), "final_decision": decision,
                                                "changes": recruitment_history.diff(before, {f: sent[f] for f in FEEDBACK_FIELDS})})
    return previous


async def _feedback(db: AsyncSession, ids: list[UUID]) -> dict[UUID, dict]:
    """The saved feedback of these interviews, in one query (no N+1)."""
    if not ids:
        return {}
    rows = await db.execute(
        select(InterviewFeedback, User).join(User, User.id == InterviewFeedback.recorded_by_user_id).where(InterviewFeedback.interview_id.in_(ids))
        .execution_options(populate_existing=True)
    )
    return {
        row.interview_id: {
            **{f: getattr(row, f) for f in FEEDBACK_FIELDS}, "next_round_label": round_label(row.next_round),
            "final_decision_label": status_label(row.final_decision) if row.final_decision else None,
            "recorded_by": {"id": by.id, "full_name": by.full_name}, "updated_at": row.updated_at,
        }
        for row, by in rows
    }


# hrc-029 (DEC-SCOPE-405 V7): the panel labels and a member's feedback as read (services/interview_panel.py writes them)
KIND_LABELS = {"internal": "Internal interviewer", "employer": "Employer"}
ATTENDANCE_LABELS = {"attended": "Attended", "no_show": "No-show"}
RECOMMENDATION_LABELS = {"strong_yes": "Strongly recommend", "yes": "Recommend", "no": "Do not recommend", "strong_no": "Strongly do not recommend"}


def panel_feedback_out(row: InterviewPanelFeedback | None) -> dict | None:
    if row is None:
        return None
    return {
        "attendance": row.attendance, "attendance_label": ATTENDANCE_LABELS[row.attendance], "score": row.score, "recommendation": row.recommendation,
        "recommendation_label": RECOMMENDATION_LABELS.get(row.recommendation or ""), "notes": row.notes, "updated_at": row.updated_at,
    }  # fmt: skip


async def _panel(db: AsyncSession, ids: list[UUID]) -> dict[UUID, list[dict]]:
    """hrc-029 (DEC-SCOPE-405 V9): each interview's panel, lead first, with every member's own feedback -- one query."""
    if not ids:
        return {}
    rows = await db.execute(
        select(InterviewInterviewer, User, InterviewPanelFeedback)
        .join(User, User.id == InterviewInterviewer.user_id)
        .outerjoin(InterviewPanelFeedback, (InterviewPanelFeedback.interview_id == InterviewInterviewer.interview_id) & (InterviewPanelFeedback.interviewer_user_id == User.id))
        .where(InterviewInterviewer.interview_id.in_(ids))
        .order_by(InterviewInterviewer.is_lead.desc(), func.lower(User.full_name), User.id)
        .execution_options(populate_existing=True)
    )
    panel: dict[UUID, list[dict]] = {}
    for member, person, feedback in rows:
        panel.setdefault(member.interview_id, []).append({
            "id": person.id, "full_name": person.full_name, "kind": member.kind, "kind_label": KIND_LABELS[member.kind], "is_lead": member.is_lead,
            "feedback": panel_feedback_out(feedback),
        })
    return panel


# --- notices (IV9, Q-20) ------------------------------------------------------------------------------------------------------------
def _details(interview: Interview, job: Job, company: Company) -> list[str]:
    """hrc-028 (I2/I4): the time in the candidate's zone; once cancelled the link is never sent again, and the reason is."""
    cancelled = interview.status == "cancelled"
    lines = [f"Company: {company.name}", f"Requirement: {job.title}", f"Round: {round_text(interview)}", f"Date and time: {local_when(interview)}",
             f"Mode: {interview.mode}"]
    optional = (
        ("Platform", PLATFORM_LABELS.get(interview.platform or "")), ("Meeting link", None if cancelled else interview.meeting_url),
        ("Location", interview.location), ("Phone", interview.phone_details), ("Interviewer", interview.interviewer),
        ("Instructions", interview.instructions), ("Documents to bring", interview.documents_required), ("Reason", interview.cancel_reason),
    )
    return lines + [f"{label}: {value}" for label, value in optional if value]


def invite(interview: Interview, job: Job, company: Company, details: list[str]) -> tuple[str, str]:
    """hrc-028 (I6): the .ics (UID per interview, SEQUENCE from the row) and its METHOD, built now so a queued email never changes."""
    cancelled = interview.status == "cancelled"
    end = interview.ends_at or interview.scheduled_at + DEFAULT_LENGTH
    where = (interview.location or interview.mode) if cancelled else (interview.meeting_url or interview.location or interview.mode)
    vevent = calendar_ics.event(uid=f"interview-{interview.id}@edusphere", sequence=interview.calendar_sequence, start=interview.scheduled_at, end=end,
                                summary=f"Interview: {round_text(interview)} - {job.title} ({company.name})", location=where, description="\n".join(details),
                                status="CANCELLED" if cancelled else "CONFIRMED", organizer=settings.smtp_from_email or None)
    method = "CANCEL" if cancelled else "REQUEST"
    return calendar_ics.calendar([vevent], method=method), method


async def notify(db: AsyncSession, user: User, interview: Interview, application: JobApplication, job: Job, kind: str, enabled: bool) -> tuple[dict, list[UUID]]:
    """On schedule, reschedule, a visible detail change and cancel (`kind`): the candidate (in-app plus the email delivery for a student, else
    a queued email) and the chosen contact (a queued email naming the candidate by name and code only -- R8), each with the calendar invite
    (hrc-028 I6; every notice after the first moves the SEQUENCE on). Returns the summary and the email ids to publish after the commit."""
    contact = await db.get(CompanyContact, interview.contact_id) if interview.contact_id else None
    if not enabled:
        return {"candidate": "off", "contact": "off" if contact else None}, []
    candidate = await db.get(Candidate, application.candidate_id)
    company = await db.get(Company, job.company_id)
    if kind != "scheduled":
        interview.calendar_sequence += 1
    title = f"Interview {kind}"
    subject = f"{title}: {round_text(interview)} - {job.title}"[:200]
    details = _details(interview, job, company)
    ics, method = invite(interview, job, company, details)
    summary: dict = {"candidate": None, "contact": None}
    emails: list[RecruiterMessage] = []
    smtp = mailer.smtp_configured()
    if candidate.user_id is not None:
        student = await db.get(User, candidate.user_id)
        item = Notification(user_id=student.id, title=title, body="\n".join(details), read=False, action_url="/it/student/job-applications")
        db.add(item)
        await db.flush()
        await queue_deliveries(db, item, student, context={"kind": INVITE_KIND, "ics": ics, "method": method})
        summary["candidate"] = "in_app"
    elif not smtp or not candidate.email:
        summary["candidate"] = "email_off" if not smtp else "no_email"
    else:
        emails.append(RecruiterMessage(candidate_id=candidate.id, body="\n".join([f"Dear {candidate.name},", "", *details]), subject=subject, calendar_ics=ics, **_mail(user)))
        summary["candidate"] = "queued"
    if contact is not None:
        if contact.status == "do_not_contact":  # pob-005 D6: the interview goes ahead; this person is not emailed
            summary["contact"] = "do_not_contact"
        elif not smtp or not contact.email:
            summary["contact"] = "email_off" if not smtp else "no_email"
        else:
            lines = [f"Dear {contact.name},", "", f"Candidate: {candidate.name} ({candidate.candidate_code})", *details]
            emails.append(RecruiterMessage(company_id=company.id, contact_id=contact.id, body="\n".join(lines), subject=subject, calendar_ics=ics, **_mail(user)))
            summary["contact"] = "queued"
    db.add_all(emails)
    await db.flush()
    if summary["contact"] == "queued":
        await recruiter_companies.refresh_last_contact(db, company.id)  # pob-003 D4: the invite emailed to the client contact
        await contact_status.advance(db, user, [contact.id], "contacted", "interview")  # pob-005 D4
    return summary, [m.id for m in emails]


def _mail(user: User) -> dict:
    return {"sender_user_id": user.id, "channel": "email", "delivery_status": "queued", "sent_at": func.now()}


# --- reads --------------------------------------------------------------------------------------------------------------------------
async def _scoped(db: AsyncSession, user: User, application_id: UUID, *, lock: bool = False) -> tuple[JobApplication, Job]:
    try:
        return await applications.load_scoped(db, user, application_id, lock=lock)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, NOT_FOUND) from None
        raise


async def check_readable(db: AsyncSession, user: User, interview_id: UUID) -> None:
    application_id = await db.scalar(select(Interview.application_id).where(Interview.id == interview_id))
    if application_id is None:
        await requirements.caller_scope(db, user)  # the role check (403) comes before "not found"
        raise HTTPException(404, NOT_FOUND)
    await _scoped(db, user, application_id)


IV = Interview
Contact = aliased(CompanyContact)


def _rows():
    """One query: the interview, its application, candidate, requirement, company and contact -- no N+1."""
    return (
        select(IV, JobApplication, Candidate, Job, Company, Contact)
        .join(JobApplication, JobApplication.id == IV.application_id)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(Contact, Contact.id == IV.contact_id)
    )


async def _history(db: AsyncSession, ids: list[UUID]) -> dict[UUID, list]:
    history: dict[UUID, list] = {i: [] for i in ids}
    if not ids:
        return history
    rows = await db.execute(
        select(InterviewEvent, User).outerjoin(User, User.id == InterviewEvent.actor_user_id).where(InterviewEvent.interview_id.in_(ids)).order_by(InterviewEvent.position)
    )
    for event, actor in rows:
        history[event.interview_id].append({
            "event": event.event, "from_status": event.from_status, "to_status": event.to_status, "old_scheduled_at": event.old_scheduled_at,
            "new_scheduled_at": event.new_scheduled_at, "note": event.note, "actor": {"id": actor.id, "full_name": actor.full_name} if actor else None,
            "old_meeting_url": event.old_meeting_url, "new_meeting_url": event.new_meeting_url, "old_location": event.old_location,
            "new_location": event.new_location,
            "created_at": event.created_at,
        })
    return history


def _out(user: User, now: datetime, history: dict, feedback: dict, panel: dict, i: Interview, a: JobApplication, c: Candidate, job: Job, company: Company,
         contact) -> dict:
    writer = applications.can_write(user)
    return {
        "id": i.id, "code": i.interview_code, "round": i.round, "round_label": round_label(i.round), "scheduled_at": i.scheduled_at, "mode": i.mode,
        "meeting_url": i.meeting_url, "interviewer": i.interviewer, "location": i.location, "status": i.status, "status_label": status_label(i.status),
        "result": i.result, "updated_at": i.updated_at,  # hrc-003: the edit form's token
        # hrc-028 (I1/I3)
        "round_number": i.round_number, "ends_at": i.ends_at, "time_zone": i.time_zone, "local_when": local_when(i), "platform": i.platform,
        "platform_label": PLATFORM_LABELS.get(i.platform) if i.platform else None, "phone_details": i.phone_details, "instructions": i.instructions,
        "documents_required": i.documents_required, "cancel_reason": i.cancel_reason,
        "application": {"id": a.id, "status": a.status, "status_label": applications.label(a.status)},
        "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company": {"id": company.id, "name": company.name},
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "history": history[i.id],
        "allowed_statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in allowed(i, now)] if writer else [],
        "can_edit": writer and i.status not in CLOSED,
        "can_reschedule": writer and i.status in RESCHEDULABLE,
        "can_cancel": writer and i.status in CANCELLABLE,
        "feedback": feedback.get(i.id),
        "can_feedback": can_feedback(user, i.status, i.id in feedback),
        "interviewers": panel.get(i.id, []),  # hrc-029 (V9)
        "can_assign": writer and i.status not in CLOSED,
    }


async def _items(db: AsyncSession, user: User, now: datetime, rows) -> list[dict]:
    ids = [row[0].id for row in rows]
    history, feedback, panel = await _history(db, ids), await _feedback(db, ids), await _panel(db, ids)
    return [_out(user, now, history, feedback, panel, *row) for row in rows]


async def one(db: AsyncSession, user: User, interview_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows().where(IV.id == interview_id).execution_options(populate_existing=True))).one()
    return (await _items(db, user, now, [row]))[0]


async def for_application(db: AsyncSession, user: User, application: JobApplication, job: Job, now: datetime) -> dict:
    rows = (await db.execute(_rows().where(IV.application_id == application.id).order_by(IV.scheduled_at.desc(), IV.id))).all()
    can_schedule = applications.can_write(user) and application.status in applications.OPEN and job.status not in requirements.ENDED
    return {"items": await _items(db, user, now, rows), "can_schedule": can_schedule}


def views(now: datetime) -> dict:
    """IV12: the condition and the order of each view."""
    is_open = IV.status.in_(OPEN)
    return {
        "upcoming": (is_open & (IV.scheduled_at > now), (IV.scheduled_at, IV.id)),
        "awaiting_update": (or_(is_open & (IV.scheduled_at <= now), IV.status == "completed"), (IV.scheduled_at, IV.id)),
        "on_hold": (IV.status == "on_hold", (IV.scheduled_at.desc(), IV.id)),
        "closed": (IV.status.in_(("selected", "rejected", "no_show", "cancelled")), (IV.scheduled_at.desc(), IV.id)),
    }


async def list_page(db: AsyncSession, user: User, view: str, now: datetime, limit: int, offset: int) -> dict:
    """The caller's interviews (rec-007's requirement scope) in one view; the counts are the four views' totals."""
    scope = await requirements.caller_scope(db, user)
    conditions = views(now)
    where, order = conditions[view]
    base = select(func.count()).select_from(IV).join(JobApplication, JobApplication.id == IV.application_id).join(Job, Job.id == JobApplication.job_id)
    total = await db.scalar(base.where(*scope, where))
    rows = (await db.execute(_rows().where(*scope, where).order_by(*order).limit(limit).offset(offset))).all()
    counts = (await db.execute(base.with_only_columns(*(func.count().filter(c) for c, _ in conditions.values())).where(*scope))).one()
    return {"items": await _items(db, user, now, rows), "total": total or 0, "limit": limit, "offset": offset,
            "counts": {v: n or 0 for v, n in zip(conditions, counts, strict=True)}}


def audit(db: AsyncSession, user: User, action: str, interview: Interview, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_interview.{action}", entity_type="interview", entity_id=str(interview.id), metadata_json=metadata or {}))


def log(event: str, user: User, interview_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "interview_id": str(interview_id), **extra}})
