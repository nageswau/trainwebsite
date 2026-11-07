"""pob-022 (DEC-SCOPE-421 A1-A8): interview coordination automation -- the settings (A2), the approved templates (A1), the reminder markers
and their re-arm (A3/A4), and the two beat sweeps: reminders before an interview, and the feedback chase follow-up with its escalation to
the Team Lead (A5/A6).

Each sweep takes a bounded batch with `FOR UPDATE SKIP LOCKED` and writes its markers in the transaction of its notices or follow-up: both
or neither, so a rerun adds nothing. A reschedule holds the interview lock, so it never races a sweep over the same row. Logs and audit
carry ids and counts only, never a name, a body or a note."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    CompanyContact,
    Interview,
    InterviewAutomationSetting,
    InterviewFeedback,
    Job,
    JobApplication,
    RecruiterFollowUp,
    RecruiterMessageTemplate,
    RecruiterProfile,
    User,
)
from app.notifications.dispatch import enqueue_recruiter_email
from app.notifications.events import notify
from app.services import interviews, recruiter_messages
from app.services.recruiter import MANAGER_ROLE

logger = logging.getLogger("app.recruiter")

DEFAULTS = {"first_reminder_hours": 24, "second_reminder_hours": 2, "reminder_template_id": None, "chase_after_hours": 24, "escalate_after_hours": 24,
            "chase_template_id": None}  # fmt: skip
SLOTS = (("first_reminder_hours", "first_reminder_at"), ("second_reminder_hours", "second_reminder_at"))
EDITORS = frozenset({MANAGER_ROLE, "super_admin"})  # pob-001: the Team Lead is the placement manager
# hrc-032 N6's set (interviews.OPEN + completed, spelled out: interviews imports this module): on hold, no show, decided and cancelled owe none
AWAITING_FEEDBACK = ("scheduled", "confirmed", "rescheduled", "completed")
SWEEP_LIMIT = 200
ESCALATED = "it.interview.feedback_escalated"
FOLLOW_UPS_URL = "/recruiter/follow-ups"
NOT_ALLOWED = "Only a Team Lead can change interview automation"
TEMPLATE_INVALID = "Choose an approved shared email template"
CONFIRMATION_INVALID = "Choose an approved interview confirmation template"
ORDER_INVALID = "The second reminder must come closer to the interview than the first"
# A5: the chase text when no template is chosen -- rendered by pob-023's allow-list like a template
CHASE_TEXT = ("Dear {name},\n\nCould you share your feedback on {candidate}'s {job_title} interview of {interview_date}?\n\n"
              "Thank you,\n{recruiter}")  # fmt: skip
HAS_FEEDBACK = exists(select(InterviewFeedback.interview_id).where(InterviewFeedback.interview_id == Interview.id))


# --- A2 settings ------------------------------------------------------------------------------------------------------------------------
async def settings(db: AsyncSession, *, lock: bool = False) -> InterviewAutomationSetting:
    """The one row; its defaults (not added) when the row is missing."""
    row = await db.get(InterviewAutomationSetting, 1, with_for_update=lock, populate_existing=True)
    return row if row is not None else InterviewAutomationSetting(id=1, **DEFAULTS)


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, NOT_ALLOWED)


def _approved(template: RecruiterMessageTemplate | None, kind: str | None = None) -> bool:
    """pob-023 G4/G5: approved and shared (a personal template is never approved), an email, and of `kind` when one is asked for."""
    return (template is not None and template.owner_user_id is None and template.status == "approved" and template.channel == "email"
            and (kind is None or template.kind == kind))  # fmt: skip


async def approved_template(db: AsyncSession, template_id: UUID, *, field: str, kind: str | None = None) -> RecruiterMessageTemplate:
    """The template a request names, or 422 on its field."""
    template = await db.get(RecruiterMessageTemplate, template_id)
    if not _approved(template, kind):
        raise interviews.field_error(field, CONFIRMATION_INVALID if kind else TEMPLATE_INVALID, str(template_id))
    return template


async def _still_approved(db: AsyncSession, template_id: UUID | None) -> RecruiterMessageTemplate | None:
    """A sweep's template: a chosen one archived since falls back to the fixed text."""
    template = await db.get(RecruiterMessageTemplate, template_id) if template_id else None
    return template if _approved(template) else None


def settings_out(row: InterviewAutomationSetting) -> dict:
    return {key: getattr(row, key) for key in DEFAULTS}


async def save_settings(db: AsyncSession, user: User, values: dict) -> InterviewAutomationSetting:
    """The Team Lead (403 otherwise); the order of the slots and the templates (422 on the field); the row locked, created when missing,
    and audited with the changed values."""
    require_editor(user)
    first, second = values["first_reminder_hours"], values["second_reminder_hours"]
    if first is not None and second is not None and second >= first:
        raise interviews.field_error("second_reminder_hours", ORDER_INVALID, second)
    for field in ("reminder_template_id", "chase_template_id"):
        if values[field] is not None:
            await approved_template(db, values[field], field=field)
    row = await db.get(InterviewAutomationSetting, 1, with_for_update=True, populate_existing=True)
    if row is None:
        row = InterviewAutomationSetting(id=1, **DEFAULTS)
        db.add(row)
    changes = {key: [_plain(getattr(row, key)), _plain(value)] for key, value in values.items() if getattr(row, key) != value}
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by_user_id = user.id
    if changes:
        db.add(AuditLog(user_id=user.id, action="interview_automation.settings", entity_type="interview_automation_settings", entity_id="1",
                        metadata_json={"changes": changes}))  # fmt: skip
    return row


def _plain(value):
    return str(value) if isinstance(value, UUID) else value


# --- A4 re-arm --------------------------------------------------------------------------------------------------------------------------
async def arm(db: AsyncSession, interview: Interview, now: datetime) -> None:
    """On schedule and reschedule: a slot the new time is already inside counts as sent (the confirmation just went out); any other is
    armed. A reschedule also starts the feedback chase over."""
    row = await settings(db)
    for hours_key, marker in SLOTS:
        hours = getattr(row, hours_key)
        inside = hours is not None and interview.scheduled_at - now <= timedelta(hours=hours)
        setattr(interview, marker, now if inside else None)
    interview.chase_follow_up_id = interview.chase_escalated_at = None


async def _owner(db: AsyncSession, interview: Interview, application: JobApplication, job: Job) -> User | None:
    """Who the automated emails and the chase come from: the application's owner, else the requirement's primary, else the creator."""
    user_id = application.owner_user_id or job.assigned_recruiter_user_id or interview.created_by_user_id
    user = await db.get(User, user_id) if user_id else None
    return user if user is not None and user.active else None


# --- A3 reminders -----------------------------------------------------------------------------------------------------------------------
async def run_reminders(now: datetime | None = None) -> dict[str, int]:
    """An open interview inside a reminder slot it was not reminded for gets one reminder (both slots due at once: one, both stamped).
    Soonest first; the emails are published after the commit."""
    now = now or datetime.now(UTC)
    emails: list[UUID] = []
    async with SessionLocal() as db:
        row = await settings(db)
        slots = [(timedelta(hours=hours), marker) for key, marker in SLOTS if (hours := getattr(row, key)) is not None]
        due = []
        if slots:
            inside = or_(*(and_(getattr(Interview, marker).is_(None), Interview.scheduled_at <= now + window) for window, marker in slots))
            due = (await db.execute(
                select(Interview, JobApplication, Job)
                .join(JobApplication, JobApplication.id == Interview.application_id)
                .join(Job, Job.id == JobApplication.job_id)
                .where(Interview.status.in_(interviews.OPEN), Interview.scheduled_at > now, inside)
                .order_by(Interview.scheduled_at, Interview.id)
                .limit(SWEEP_LIMIT)
                .with_for_update(of=Interview, skip_locked=True)
            )).all()  # fmt: skip
            template = await _still_approved(db, row.reminder_template_id)
        for interview, application, job in due:
            for window, marker in slots:
                if getattr(interview, marker) is None and interview.scheduled_at <= now + window:
                    setattr(interview, marker, now)
            _summary, ids = await interviews.notify(db, await _owner(db, interview, application, job), interview, application, job, "reminder", True,
                                                    template=template)  # fmt: skip
            emails += ids
        await db.commit()
    for message_id in emails:
        enqueue_recruiter_email(message_id)
    counts = {"interviews": len(due)}
    logger.info("interview_reminder_sweep", extra={"extra_fields": counts})
    return counts


# --- A5/A6 feedback chase and escalation ------------------------------------------------------------------------------------------------
async def _chase(db: AsyncSession, row: InterviewAutomationSetting, now: datetime) -> int:
    due = (await db.execute(
        select(Interview, JobApplication, Job)
        .join(JobApplication, JobApplication.id == Interview.application_id)
        .join(Job, Job.id == JobApplication.job_id)
        .where(Interview.chase_follow_up_id.is_(None), Interview.chase_escalated_at.is_(None), Interview.status.in_(AWAITING_FEEDBACK),
               func.coalesce(Interview.ends_at, Interview.scheduled_at) < now - timedelta(hours=row.chase_after_hours), ~HAS_FEEDBACK)
        .order_by(Interview.scheduled_at, Interview.id)
        .limit(SWEEP_LIMIT)
        .with_for_update(of=Interview, skip_locked=True)
    )).all()  # fmt: skip
    template = await _still_approved(db, row.chase_template_id)
    chased = 0
    for interview, application, job in due:
        owner = await _owner(db, interview, application, job)
        if owner is None:  # nobody to chase it: left for a later run
            continue
        contact = await db.get(CompanyContact, interview.contact_id) if interview.contact_id else None
        contact = contact if contact is not None and contact.active else None
        values = await interviews.template_values(db, owner, interview, application, job)
        values |= {"name": contact.name if contact else "", "designation": (contact.designation or "") if contact else ""}
        if template is None:
            notes = recruiter_messages.render(CHASE_TEXT, values)
        else:
            text = recruiter_messages.rendered(template, values)
            notes = f"Subject: {text['subject']}\n\n{text['body']}"
        follow_up = RecruiterFollowUp(company_id=job.company_id, contact_id=contact.id if contact else None, job_id=job.id, application_id=application.id,
                                      reason="interview_feedback", due_at=now, notes=notes, created_by_user_id=owner.id)  # fmt: skip
        db.add(follow_up)
        await db.flush()
        interview.chase_follow_up_id = follow_up.id
        chased += 1
    return chased


async def _team_lead(db: AsyncSession, owner_id: UUID, managers: list[User]) -> list[User]:
    """The owner's reporting manager when an active Team Lead, else every active one."""
    lead_id = await db.scalar(select(RecruiterProfile.reporting_manager_user_id).where(RecruiterProfile.user_id == owner_id))
    lead = await db.get(User, lead_id) if lead_id else None
    return [lead] if lead is not None and lead.active and lead.role == MANAGER_ROLE else managers


async def _escalate(db: AsyncSession, row: InterviewAutomationSetting, now: datetime) -> int:
    due = (await db.execute(
        select(Interview, RecruiterFollowUp.created_by_user_id)
        .join(RecruiterFollowUp, RecruiterFollowUp.id == Interview.chase_follow_up_id)
        .where(Interview.chase_escalated_at.is_(None), Interview.status.in_(AWAITING_FEEDBACK), RecruiterFollowUp.status == "open",
               RecruiterFollowUp.due_at < now - timedelta(hours=row.escalate_after_hours), ~HAS_FEEDBACK)
        .order_by(RecruiterFollowUp.due_at, Interview.id)
        .limit(SWEEP_LIMIT)
        .with_for_update(of=Interview, skip_locked=True)
    )).all()  # fmt: skip
    managers = list((await db.scalars(select(User).where(User.role == MANAGER_ROLE, User.active))).all()) if due else []
    escalated = 0
    for interview, owner_id in due:
        leads = await _team_lead(db, owner_id, managers)
        if not leads:  # no Team Lead at all: left for a later run
            continue
        await notify(db, leads, ESCALATED, interview.id, action_url=FOLLOW_UPS_URL)
        interview.chase_escalated_at = now
        escalated += 1
    return escalated


async def run_feedback_chase(now: datetime | None = None) -> dict[str, int]:
    """A5: overdue client feedback becomes one follow-up for the owner (no extra notice: hrc-032 already tells them); A6: a chase still
    open M hours later, feedback still missing, tells the Team Lead once. Oldest first."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        row = await settings(db)
        chased = await _chase(db, row, now) if row.chase_after_hours is not None else 0
        escalated = await _escalate(db, row, now) if row.escalate_after_hours is not None else 0
        await db.commit()
    counts = {"chased": chased, "escalated": escalated}
    logger.info("interview_feedback_chase_sweep", extra={"extra_fields": counts})
    return counts
