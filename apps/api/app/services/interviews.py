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

from app.models import AuditLog, Candidate, Company, CompanyContact, Interview, InterviewEvent, Job, JobApplication, Notification, RecruiterMessage, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import RecInterviewCreate, RecInterviewUpdate
from app.services import applications, company_pipeline, mailer
from app.services import recruiter_requirements as requirements

logger = logging.getLogger("app.recruiter")

ROUND_LABELS = {"hr_round": "HR Round", "technical_round": "Technical Round", "manager_round": "Manager Round", "final_round": "Final Round", "client_round": "Client Round"}
STATUS_LABELS = {
    "scheduled": "Scheduled", "confirmed": "Confirmed", "completed": "Completed", "rescheduled": "Rescheduled", "no_show": "No Show",
    "selected": "Selected", "rejected": "Rejected", "on_hold": "On Hold",
}
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
RESCHEDULABLE = (*OPEN, "on_hold", "no_show")
DECIDING_ROUNDS = ("final_round", "client_round")  # IV8: only these rounds' Selected selects the application
IST = ZoneInfo("Asia/Kolkata")

NOT_FOUND = "Interview not found"
CLASH = "This candidate already has an interview scheduled at this time"
NOT_STARTED = "You can mark this once the interview time has passed"
APPLICATION_CLOSED = "Interviews can be scheduled only for an open application"
REQUIREMENT_ENDED = "Interviews cannot be scheduled on a closed or cancelled requirement"
DECIDED = "This interview is already decided"
SAME_TIME = "Choose a different time to reschedule"
CONTACT_INVALID = "Choose an active contact of this requirement's company"
TIME_PAST = "Choose an interview time in the future"
TIME_FAR = "Choose an interview time within the next 12 months"


HORIZON = timedelta(days=366)  # tel-011's horizon, as rec-028's meetings (not imported: workflows.py -> here must not reach the telecaller modules)


def field_error(field: str, msg: str, value=None) -> RequestValidationError:
    """The validation-error shape, so the form can place a service rule on its field."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_time(when: datetime, now: datetime) -> None:
    """IV4 / IV5: in the future and within 366 days."""
    if when <= now or when > now + HORIZON:
        raise field_error("scheduled_at", TIME_PAST if when <= now else TIME_FAR, when.isoformat())


def round_label(key: str | None) -> str | None:
    return ROUND_LABELS.get(key, key) if key else None


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


def _event(db: AsyncSession, interview: Interview, actor: User | None, event: str, *, from_status=None, old=None, note=None) -> None:
    db.add(InterviewEvent(
        interview_id=interview.id, event=event, from_status=from_status, to_status=interview.status,
        old_scheduled_at=old, new_scheduled_at=interview.scheduled_at if event != "status" else None, note=note,
        actor_user_id=actor.id if actor else None,
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
    """Only changed values count (no audit for none). Returns the changed field names."""
    if interview.status in FINAL:
        raise HTTPException(409, DECIDED)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(key for key, value in changes.items() if getattr(interview, key) != value)
    if "contact_id" in changed:
        await _check_contact(db, job.company_id, changes["contact_id"], kept=interview.contact_id)
    for key in changed:
        setattr(interview, key, changes[key])
    if changed:
        audit(db, user, "update", interview, {"fields": changed})
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
    interview.scheduled_at, interview.status = when, "rescheduled"
    _event(db, interview, user, "rescheduled", from_status=previous, old=old, note=reason)
    if user is not None:
        audit(db, user, "reschedule", interview, {"from_status": previous})


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
        audit(db, user, "status", interview, {"from": previous, "to": target})
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


# --- notices (IV9, Q-20) ------------------------------------------------------------------------------------------------------------
def _when(value: datetime) -> str:
    return value.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def _details(interview: Interview, job: Job, company: Company) -> list[str]:
    lines = [f"Company: {company.name}", f"Requirement: {job.title}", f"Round: {round_label(interview.round)}", f"Date and time: {_when(interview.scheduled_at)}",
             f"Mode: {interview.mode}"]
    lines += [f"{label}: {value}" for label, value in (("Meeting link", interview.meeting_url), ("Location", interview.location), ("Interviewer", interview.interviewer)) if value]
    return lines


async def notify(db: AsyncSession, user: User, interview: Interview, application: JobApplication, job: Job, kind: str, enabled: bool) -> tuple[dict, list[UUID]]:
    """On schedule and reschedule (`kind`): the candidate (in-app for a student, else a queued email) and the chosen contact (a queued
    email naming the candidate by name and code only -- R8). Returns the summary and the email ids to publish after the commit."""
    contact = await db.get(CompanyContact, interview.contact_id) if interview.contact_id else None
    if not enabled:
        return {"candidate": "off", "contact": "off" if contact else None}, []
    candidate = await db.get(Candidate, application.candidate_id)
    company = await db.get(Company, job.company_id)
    title = f"Interview {kind}"
    subject = f"{title}: {round_label(interview.round)} - {job.title}"[:200]
    details = _details(interview, job, company)
    summary: dict = {"candidate": None, "contact": None}
    emails: list[RecruiterMessage] = []
    smtp = mailer.smtp_configured()
    if candidate.user_id is not None:
        student = await db.get(User, candidate.user_id)
        item = Notification(user_id=student.id, title=title, body="\n".join(details), read=False, action_url="/it/student/job-applications")
        db.add(item)
        await db.flush()
        await queue_deliveries(db, item, student)
        summary["candidate"] = "in_app"
    elif not smtp or not candidate.email:
        summary["candidate"] = "email_off" if not smtp else "no_email"
    else:
        emails.append(RecruiterMessage(candidate_id=candidate.id, body="\n".join([f"Dear {candidate.name},", "", *details]), subject=subject, **_mail(user)))
        summary["candidate"] = "queued"
    if contact is not None:
        if not smtp or not contact.email:
            summary["contact"] = "email_off" if not smtp else "no_email"
        else:
            lines = [f"Dear {contact.name},", "", f"Candidate: {candidate.name} ({candidate.candidate_code})", *details]
            emails.append(RecruiterMessage(company_id=company.id, contact_id=contact.id, body="\n".join(lines), subject=subject, **_mail(user)))
            summary["contact"] = "queued"
    db.add_all(emails)
    await db.flush()
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
            "created_at": event.created_at,
        })
    return history


def _out(user: User, now: datetime, history: dict, i: Interview, a: JobApplication, c: Candidate, job: Job, company: Company, contact) -> dict:
    writer = applications.can_write(user)
    return {
        "id": i.id, "code": i.interview_code, "round": i.round, "round_label": round_label(i.round), "scheduled_at": i.scheduled_at, "mode": i.mode,
        "meeting_url": i.meeting_url, "interviewer": i.interviewer, "location": i.location, "status": i.status, "status_label": status_label(i.status),
        "result": i.result,
        "application": {"id": a.id, "status": a.status, "status_label": applications.label(a.status)},
        "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company": {"id": company.id, "name": company.name},
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "history": history[i.id],
        "allowed_statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in allowed(i, now)] if writer else [],
        "can_edit": writer and i.status not in FINAL,
        "can_reschedule": writer and i.status in RESCHEDULABLE,
    }


async def _items(db: AsyncSession, user: User, now: datetime, rows) -> list[dict]:
    history = await _history(db, [row[0].id for row in rows])
    return [_out(user, now, history, *row) for row in rows]


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
        "closed": (IV.status.in_(("selected", "rejected", "no_show")), (IV.scheduled_at.desc(), IV.id)),
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
