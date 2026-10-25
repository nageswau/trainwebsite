"""ccrm-030 (DEC-SCOPE-270, RM1-RM10): the counselor reminder and trigger engine -- one catalogue of rules, configured by the Overseas Admin,
that turns lead and application dates into counselor tasks (ccrm-029, `source='rule'`) or notifications, and reminds the student where the
rule says so. The daily job runs every time-based rule; `first_contact` runs inside the handover / admin owner write.

Every firing claims a `counselor_reminder_log` row by its unique `rule:subject:anchor` key (INSERT ... ON CONFLICT DO NOTHING), so a re-run
never repeats one (RM3), in a savepoint, so one failure is counted and logged with ids only (RM7). Agents are never told here: AGN-017 keeps
the agency reminders (RM4). Bodies carry codes, university names and dates only. Spec:
docs/superpowers/specs/2026-10-25-ccrm-030-counselor-reminders-design.md."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application_outcome import TERMINAL
from app.models import (
    COUNSELOR_REMINDER_MAX_OFFSET,
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationOfferCondition,
    ApplicationOutcome,
    AuditLog,
    CounselorReminderLog,
    CounselorReminderRule,
    CounselorTask,
    DocumentRequest,
    Enquiry,
    LeadCall,
    Notification,
    OverseasApplication,
    OverseasStudentCounselor,
    University,
    User,
    VisaCase,
)
from app.notifications.dispatch import queue_deliveries
from app.services.agent_applications import OFFER_STAGES_ON
from app.services.agent_notifications import clean_text
from app.services.bdm_travel import INDIA, india_today
from app.services.counselor_tasks import TASKS_URL
from app.services.ledger import field_error
from app.services.student_document_requests import name as request_name

logger = logging.getLogger("app.counselor_reminders")

LOOKBACK_DAYS = 30  # RM2: an "after" rule looks back this far, so switching it on never floods old items
NO_RESPONSE_STAGES = ("contacted", "qualified", "interested", "follow_up", "counselling_completed")
APPS_URL, LEADS_URL = "/overseas/counselor/applications", "/overseas/counselor/leads"
STUDENT_APPS_URL, STUDENT_DOCS_URL = "/overseas/student/applications", "/overseas/student/documents"
UNKNOWN_RULE = "Reminder rule not found"
NO_STUDENT = "This rule never reminds the student"


@dataclass(frozen=True)
class Rule:
    label: str
    description: str
    action: str  # "task" | "notify"
    timing: str  # "assign" | "silent" | "before" | "after"
    offset: int  # RM1 default
    max_offset: int
    student: bool | None  # None: the rule never reminds the student; else the default

    @property
    def min_offset(self) -> int:
        """A silence of 0 days would fire on every lead at once."""
        return 1 if self.timing == "silent" else 0


RULES: dict[str, Rule] = {
    "first_contact": Rule("New lead assigned", "A first-contact task when a lead is handed to a counselor.", "task", "assign", 1, 30, None),
    "no_response": Rule("No response after contact", "A follow-up task when a contacted lead has had no call or stage change.", "task", "silent", 3, 60, None),
    "document_overdue": Rule("Document request overdue", "A task to chase a student's overdue document request.", "task", "after", 0, 30, True),
    "application_deadline": Rule("Application deadline approaching", "Tells the counselor before an unsubmitted application's deadline.", "notify", "before", 7, 60, None),
    "decision_overdue": Rule("University decision overdue", "A task to chase the university once the expected decision date has passed.", "task", "after", 0, 30, None),
    "offer_deadline": Rule("Offer deadline approaching", "Before an undecided offer's deadline.", "notify", "before", 3, 60, True),
    "deposit_due": Rule("Deposit due", "Before a pending deposit's due date.", "notify", "before", 3, 60, True),
    "condition_due": Rule("Offer condition due", "Before an open offer condition's due date (the student when it is theirs).", "notify", "before", 3, 60, True),
    "visa_appointment": Rule("Visa appointment approaching", "Before the visa appointment of an undecided visa case.", "notify", "before", 2, 30, False),
    "hold_review": Rule("On-hold review date", "A task to review an on-hold application on its review date.", "task", "before", 0, 30, None),
}
assert COUNSELOR_REMINDER_MAX_OFFSET >= max(r.max_offset for r in RULES.values())


def log(event: str, **extra) -> None:
    logger.info(event, extra={"extra_fields": {k: str(v) for k, v in extra.items()}})


def _day(value: date) -> str:
    return value.strftime("%d %b %Y")


# --- configuration (RM9) ------------------------------------------------------------------------------------------------------------
async def configured(db: AsyncSession) -> dict[str, CounselorReminderRule]:
    """Every rule's settings; a missing row reads as the catalogue default (enabled)."""
    rows = {r.rule_key: r for r in (await db.scalars(select(CounselorReminderRule))).all()}
    return {key: rows.get(key) or CounselorReminderRule(rule_key=key, enabled=True, offset_days=rule.offset, notify_student=bool(rule.student)) for key, rule in RULES.items()}


def rule_out(key: str, row: CounselorReminderRule) -> dict:
    rule = RULES[key]
    return {
        "key": key,
        "label": rule.label,
        "description": rule.description,
        "action": rule.action,
        "timing": rule.timing,
        "min_offset": rule.min_offset,
        "max_offset": rule.max_offset,
        "enabled": row.enabled,
        "offset_days": row.offset_days,
        "notify_student": None if rule.student is None else row.notify_student,
        "updated_at": row.updated_at,
    }


async def rules_out(db: AsyncSession) -> list[dict]:
    return [rule_out(key, row) for key, row in (await configured(db)).items()]


async def update_rule(db: AsyncSession, user: User, key: str, enabled: bool, offset_days: int, notify_student: bool | None) -> dict:
    """The caller commits. Range per rule; `notify_student` only on a rule with a student column. Audited with field names only."""
    rule = RULES.get(key)
    if rule is None:
        raise HTTPException(404, UNKNOWN_RULE)
    if not rule.min_offset <= offset_days <= rule.max_offset:
        raise field_error("offset_days", f"Choose from {rule.min_offset} to {rule.max_offset} days")
    if rule.student is None and notify_student:
        raise field_error("notify_student", NO_STUDENT)
    row = await db.get(CounselorReminderRule, key, with_for_update=True)
    if row is None:
        row = CounselorReminderRule(rule_key=key, enabled=True, offset_days=rule.offset, notify_student=bool(rule.student))
        db.add(row)
    student = row.notify_student if notify_student is None or rule.student is None else notify_student
    changed = [f for f, v in (("enabled", enabled), ("offset_days", offset_days), ("notify_student", student)) if getattr(row, f) != v]
    row.enabled, row.offset_days, row.notify_student, row.updated_by_user_id = enabled, offset_days, student, user.id
    db.add(AuditLog(user_id=user.id, action="counselor_reminder_rule.update", entity_type="counselor_reminder_rule", entity_id=key, metadata_json={"fields": changed}))
    await db.flush()
    await db.refresh(row)
    return rule_out(key, row)


async def log_page(db: AsyncSession, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(CounselorReminderLog))
    rows = (await db.scalars(select(CounselorReminderLog).order_by(CounselorReminderLog.created_at.desc(), CounselorReminderLog.id).limit(limit).offset(offset))).all()
    items = [
        {
            "id": r.id,
            "rule_key": r.rule_key,
            "rule_label": RULES[r.rule_key].label if r.rule_key in RULES else r.rule_key,
            "summary": r.summary,
            "task_created": r.task_id is not None,
            "recipients": r.recipients,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


# --- firing (RM3, RM6, RM7) ---------------------------------------------------------------------------------------------------------
def _counts() -> dict:
    return {"created": 0, "duplicate": 0, "skipped": 0, "failed": 0, "rules": dict.fromkeys(RULES, 0)}


async def _fire(db: AsyncSession, counts: dict, key: str, subject_id, anchor, summary: str, notices: list[tuple[User, str]], *, title: str, body: str, task: dict | None = None) -> None:
    """One firing: claim the log row, create the task (first notice's user is the counselor), send the notices."""
    try:
        async with db.begin_nested():
            claim = (
                pg_insert(CounselorReminderLog)
                .values(id=uuid4(), rule_key=key, dedupe_key=f"{key}:{subject_id}:{anchor}"[:200], subject_id=subject_id, summary=summary[:200])
                .on_conflict_do_nothing(index_elements=["dedupe_key"])
                .returning(CounselorReminderLog.id)
            )
            log_id = await db.scalar(claim)
            if log_id is None:
                counts["duplicate"] += 1
                return
            task_id = None
            if task is not None:
                counselor = notices[0][0]
                row = CounselorTask(
                    title=task["title"][:200],
                    due_on=task["due_on"],
                    priority="medium",
                    source="rule",
                    rule_key=key,
                    counselor_user_id=counselor.id,
                    created_by_user_id=counselor.id,
                    updated_by_user_id=counselor.id,
                    **task["link"],
                )
                db.add(row)
                await db.flush()
                task_id = row.id
                db.add(
                    AuditLog(
                        user_id=counselor.id,
                        action="counselor_task.create",
                        entity_type="counselor_task",
                        entity_id=str(row.id),
                        metadata_json={"fields": ["title", "due_on", "priority", "status", "counselor_user_id", "link"], "rule": key},
                    )
                )
            for user, url in notices:
                note = Notification(user_id=user.id, title=title, body=body, read=False, action_url=url)
                db.add(note)
                await queue_deliveries(db, note, user)
            await db.execute(update(CounselorReminderLog).where(CounselorReminderLog.id == log_id).values(task_id=task_id, recipients=len(notices)))
        counts["created"] += 1
        counts["rules"][key] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("counselor_reminder_failed", extra={"extra_fields": {"rule": key, "subject_id": str(subject_id)}})


_Counselor = aliased(User)


def _is_counselor(user_alias, id_column):
    return and_(user_alias.id == id_column, user_alias.active.is_(True), user_alias.role == "counselor", user_alias.division == "overseas")


def _app_select(*extra):
    """Live applications (RM5) with their university and counselor (RM4: the application's, else a direct student's csc-001 counselor),
    `None` when that person is not an active overseas counselor."""
    counselor_id = func.coalesce(OverseasApplication.counselor_id, case((OverseasApplication.agent_student_id.is_(None), OverseasStudentCounselor.counselor_user_id)))
    return (
        select(OverseasApplication, University.name, _Counselor, *extra)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasStudentCounselor, OverseasStudentCounselor.student_user_id == OverseasApplication.student_id)
        .outerjoin(_Counselor, _is_counselor(_Counselor, counselor_id))
        .where(OverseasApplication.status.notin_(("withdrawn", "enrolled")))
    )


def _before_offer():
    """QA-01: not yet at the offer stage -- a status outside the pipeline (a seeded `university_review`) counts as before it."""
    return OverseasApplication.status.notin_(OFFER_STAGES_ON)


def _not_paused():
    return or_(OverseasApplication.outcome.is_(None), OverseasApplication.outcome.notin_((*TERMINAL, "on_hold")))


def _before(column, today: date, offset: int):
    return column.between(today, today + timedelta(days=offset))


def _after(column, today: date, offset: int):
    """Overdue by more than `offset` days (0: the day after the date), within the lookback."""
    last = today - timedelta(days=offset)
    return and_(column < last, column >= last - timedelta(days=LOOKBACK_DAYS))


async def _student(db: AsyncSession, app: OverseasApplication, wanted: bool) -> User | None:
    """RM4: only on a direct application, and only an active login."""
    if not wanted or app.agent_student_id is not None or app.student_id is None:
        return None
    student = await db.get(User, app.student_id)
    return student if student is not None and student.active else None


def _app_summary(app: OverseasApplication, university: str, when: date) -> str:
    return f"{app.application_code} · {clean_text(university, 120)} · {_day(when)}"


async def _app_rule(db: AsyncSession, counts: dict, key: str, stmt, setting, today: date, *, title: str, what: str, student_url: str = STUDENT_APPS_URL) -> None:
    """A notify rule over rows (application, university, counselor, subject id, date[, student wanted])."""
    for app, university, counselor, subject_id, when, *rest in (await db.execute(stmt)).all():
        if counselor is None:
            counts["skipped"] += 1
            continue
        notices = [(counselor, APPS_URL)]
        student = await _student(db, app, setting.notify_student and (rest[0] if rest else True))
        if student is not None:
            notices.append((student, student_url))
        body = f"{clean_text(university)}: {what} {_day(when)} ({app.application_code})."
        await _fire(db, counts, key, subject_id, when.isoformat(), _app_summary(app, university, when), notices, title=title, body=body)


# --- the rules ------------------------------------------------------------------------------------------------------------------------
async def _application_deadline(db, counts, s, today):
    a = OverseasApplication
    stmt = _app_select(a.id, a.application_deadline).where(_not_paused(), _before_offer(), a.submitted_on.is_(None), _before(a.application_deadline, today, s.offset_days))
    await _app_rule(db, counts, "application_deadline", stmt, s, today, title="Application deadline approaching", what="application deadline")


async def _offer_deadline(db, counts, s, today):
    o = ApplicationOffer
    stmt = (
        _app_select(o.id, o.offer_deadline)
        .join(o, and_(o.application_id == OverseasApplication.id, o.status == "active", o.decision == "considering"))
        .where(_not_paused(), _before(o.offer_deadline, today, s.offset_days))
    )
    await _app_rule(db, counts, "offer_deadline", stmt, s, today, title="Offer deadline approaching", what="offer deadline")


async def _deposit_due(db, counts, s, today):
    d = ApplicationDepositRecord
    stmt = (
        _app_select(d.id, d.due_date)
        .join(d, and_(d.application_id == OverseasApplication.id, d.required.is_(True), d.payment_status == "pending"))
        .where(_not_paused(), _before(d.due_date, today, s.offset_days))
    )
    await _app_rule(db, counts, "deposit_due", stmt, s, today, title="Deposit due", what="deposit due")


async def _condition_due(db, counts, s, today):
    o, c = ApplicationOffer, ApplicationOfferCondition
    stmt = (
        _app_select(c.id, c.due_date, c.owner == "student")
        .join(o, and_(o.application_id == OverseasApplication.id, o.status == "active"))
        .join(c, and_(c.offer_id == o.id, c.status == "open"))
        .where(_not_paused(), _before(c.due_date, today, s.offset_days))
    )
    await _app_rule(db, counts, "condition_due", stmt, s, today, title="Offer condition due", what="an offer condition is due")


async def _visa_appointment(db, counts, s, today):
    v = VisaCase
    stmt = _app_select(v.id, v.appointment_date).join(v, and_(v.application_id == OverseasApplication.id, v.decision.is_(None))).where(_not_paused(), _before(v.appointment_date, today, s.offset_days))
    await _app_rule(db, counts, "visa_appointment", stmt, s, today, title="Visa appointment approaching", what="visa appointment")


async def _decision_overdue(db, counts, s, today):
    a = OverseasApplication
    stmt = _app_select().where(_not_paused(), _before_offer(), a.submitted_on.isnot(None), _after(a.decision_due_on, today, s.offset_days))
    for app, university, counselor in (await db.execute(stmt)).all():
        if counselor is None:
            counts["skipped"] += 1
            continue
        when = app.decision_due_on
        task = {"title": f"Chase university decision: {app.application_code}", "due_on": today, "link": {"application_id": app.id}}
        body = f"{clean_text(university)}: decision expected {_day(when)} ({app.application_code}). A task was added."
        await _fire(db, counts, "decision_overdue", app.id, when.isoformat(), _app_summary(app, university, when), [(counselor, TASKS_URL)], title="University decision overdue", body=body, task=task)


async def _hold_review(db, counts, s, today):
    """RM1: the latest on-hold event's review date; the task goes to its hold owner when an active overseas counselor, else the counselor."""
    latest = (
        select(ApplicationOutcome.review_date, ApplicationOutcome.hold_owner_id)
        .where(ApplicationOutcome.application_id == OverseasApplication.id, ApplicationOutcome.outcome == "on_hold")
        .order_by(ApplicationOutcome.created_at.desc())
        .limit(1)
        .lateral()
    )
    owner = aliased(User)
    stmt = (
        _app_select(latest.c.review_date, owner)
        .join(latest, true())
        .outerjoin(owner, _is_counselor(owner, latest.c.hold_owner_id))
        .where(OverseasApplication.outcome == "on_hold", latest.c.review_date <= today + timedelta(days=s.offset_days), latest.c.review_date >= today - timedelta(days=LOOKBACK_DAYS))
    )
    for app, university, counselor, when, hold_owner in (await db.execute(stmt)).all():
        assignee = hold_owner or counselor
        if assignee is None:
            counts["skipped"] += 1
            continue
        task = {"title": f"Review on-hold application: {app.application_code}", "due_on": max(when, today), "link": {"application_id": app.id}}
        body = f"{clean_text(university)}: on-hold review date {_day(when)} ({app.application_code}). A task was added."
        await _fire(db, counts, "hold_review", app.id, when.isoformat(), _app_summary(app, university, when), [(assignee, TASKS_URL)], title="On-hold review date", body=body, task=task)


async def _document_overdue(db, counts, s, today):
    """A direct student's open request (ccrm-020): the requester when an active overseas counselor, else the student's csc-001 counselor."""
    r = DocumentRequest
    requester, linked, student = aliased(User), aliased(User), aliased(User)
    stmt = (
        select(r, student, requester, linked)
        .join(student, student.id == r.student_user_id)
        .outerjoin(requester, _is_counselor(requester, r.requested_by_user_id))
        .outerjoin(OverseasStudentCounselor, OverseasStudentCounselor.student_user_id == r.student_user_id)
        .outerjoin(linked, _is_counselor(linked, OverseasStudentCounselor.counselor_user_id))
        .where(r.status == "open", r.student_user_id.isnot(None), _after(r.due_date, today, s.offset_days))
    )
    for request, who, by, link in (await db.execute(stmt)).all():
        counselor = by or link
        if counselor is None:
            counts["skipped"] += 1
            continue
        document, code = clean_text(request_name(request), 80), who.student_code or "Student"
        notices = [(counselor, TASKS_URL)] + ([(who, STUDENT_DOCS_URL)] if s.notify_student and who.active else [])
        task = {"title": f"Chase overdue document: {document} ({code})", "due_on": today, "link": {"student_user_id": who.id}}
        body = f"{document}: requested by {_day(request.due_date)} and not uploaded yet."
        await _fire(
            db,
            counts,
            "document_overdue",
            request.id,
            request.due_date.isoformat(),
            f"{code} · {document} · {_day(request.due_date)}",
            notices,
            title="Requested document overdue",
            body=body,
            task=task,
        )


async def _no_response(db, counts, s, today):
    """A counselor's contacted lead with no stage change and no call for `offset_days` IST days, and no next action due today or later."""
    last_call = select(func.max(LeadCall.occurred_at)).where(LeadCall.lead_id == Enquiry.id).scalar_subquery()
    last = func.greatest(Enquiry.stage_changed_at, func.coalesce(last_call, Enquiry.stage_changed_at))
    quiet_since = datetime.combine(today - timedelta(days=s.offset_days - 1), time.min, INDIA)
    stmt = (
        select(Enquiry, _Counselor, last)
        .join(_Counselor, _is_counselor(_Counselor, Enquiry.owner_id))
        .where(
            Enquiry.division == "overseas",
            Enquiry.status.in_(NO_RESPONSE_STAGES),
            or_(Enquiry.next_action_due.is_(None), Enquiry.next_action_due < today),
            last < quiet_since,
            last >= quiet_since - timedelta(days=LOOKBACK_DAYS),
        )
    )
    for lead, counselor, when in (await db.execute(stmt)).all():
        day = when.astimezone(INDIA).date()
        task = {"title": f"Follow up {lead.lead_code}: no response", "due_on": today, "link": {"lead_id": lead.id}}
        body = f"{lead.lead_code}: no call or stage change since {_day(day)}. A follow-up task was added."
        await _fire(db, counts, "no_response", lead.id, day.isoformat(), f"{lead.lead_code} · quiet since {_day(day)}", [(counselor, TASKS_URL)], title="Lead needs a follow-up", body=body, task=task)


JOB_RULES = {
    "no_response": _no_response,
    "document_overdue": _document_overdue,
    "application_deadline": _application_deadline,
    "decision_overdue": _decision_overdue,
    "offer_deadline": _offer_deadline,
    "deposit_due": _deposit_due,
    "condition_due": _condition_due,
    "visa_appointment": _visa_appointment,
    "hold_review": _hold_review,
}


async def send_counselor_reminders(db: AsyncSession, *, now: datetime) -> dict:
    """Every enabled time-based rule, each committed on its own; returns the counts (RM10's "Run now" shows them)."""
    today = now.astimezone(INDIA).date()
    counts = _counts()
    for key, setting in (await configured(db)).items():
        if key in JOB_RULES and setting.enabled:
            await JOB_RULES[key](db, counts, setting, today)
            await db.commit()
    log("counselor_reminders_done", day=today.isoformat(), **{k: v for k, v in counts.items() if k != "rules"})
    return counts


async def run_counselor_reminders() -> dict:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_counselor_reminders(db, now=datetime.now(UTC))


# --- event-driven (RM8) ---------------------------------------------------------------------------------------------------------------
async def first_contact(db: AsyncSession, lead: Enquiry) -> None:
    """Inside the handover / admin owner write (the caller commits): a first-contact task for the lead's new overseas counselor, once per
    counselor and day. Never raises -- a reminder never blocks the assignment."""
    if lead.owner_id is None or lead.division != "overseas":
        return
    setting = (await configured(db))["first_contact"]
    counselor = await db.scalar(select(_Counselor).where(_is_counselor(_Counselor, lead.owner_id))) if setting.enabled else None
    if counselor is None:
        return
    today = india_today()
    due = today + timedelta(days=setting.offset_days)
    task = {"title": f"First contact: {lead.lead_code}", "due_on": due, "link": {"lead_id": lead.id}}
    body = f"{lead.lead_code}: a new lead was assigned to you. First contact is due {_day(due)}."
    await _fire(
        db,
        _counts(),
        "first_contact",
        lead.id,
        f"{counselor.id}:{today.isoformat()}",
        f"{lead.lead_code} · first contact by {_day(due)}",
        [(counselor, TASKS_URL)],
        title="New lead assigned",
        body=body,
        task=task,
    )
