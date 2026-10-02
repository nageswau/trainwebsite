"""AGN-017 (DEC-SCOPE-058): agency notifications and daily reminders.

Recipients are the student's active assigned staff member, else the organisation's active Masters, never the actor (N2). In-app plus
email only (D19, N5). Bodies carry no names and no user-typed text -- the email leaves through the webhook (spec §8). Event notices ride
the caller's transaction (they never commit here), so a refused or rolled-back write leaves none.
"""

import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import get_args
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentCommission, AgentOrg, AgentOrgMember, AgentStudent, AgentTask, Notification, OverseasApplication, StudentDocument, University, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import AgentDocumentType
from app.services.agent_applications import OFFER_STAGES_ON, WITHDRAWN, stage_label
from app.services.agent_orgs import notification_recipients

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")  # N4: the reminder "day" (a service does not import app.api.schools; reporting/pdf.py keeps its own)
CHANNELS = ["email"]
STUDENTS_URL, DOCUMENTS_URL, APPLICATIONS_URL, TASKS_URL = (f"/overseas/agent/{s}" for s in ("students", "documents", "applications", "tasks"))
KNOWN_DOCUMENT_TYPES = frozenset(get_args(AgentDocumentType)) - {"Other"}  # "Other" names nothing; its label is user-typed


def document_label(value: str | None) -> str:
    """Only a known type is named: an uploaded document's type is free text and may carry personal data."""
    return value if value is not None and value in KNOWN_DOCUMENT_TYPES else "A document"


def clean_text(value: str | None, limit: int = 120) -> str:
    """Stored text bound for an email: control characters (CR/LF included) become spaces, runs collapse, then a hard cap."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value or "").split())[:limit]


async def _active_org(db: AsyncSession, record: AgentStudent) -> AgentOrg | None:
    """The record's organisation, only while it is active: a pending, rejected or suspended agency is never notified."""
    org = await db.scalar(select(AgentOrg).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).where(AgentOrgMember.user_id == record.agent_id))
    return org if org is not None and org.status == "active" else None


async def _active_masters(db: AsyncSession, org_id) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
        .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == "master", AgentOrgMember.status == "active", User.active.is_(True))
        .order_by(AgentOrgMember.seq)
    )
    return list(rows)


async def _active_member_user(db: AsyncSession, member_id, org_id) -> User | None:
    """The member's login, only while both the membership and the login are active and it belongs to `org_id`."""
    if member_id is None:
        return None
    row = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.id == member_id))).first()
    if row is None:
        return None
    member, user = row
    return user if member.org_id == org_id and member.status == "active" and user.active else None


async def recipients(db: AsyncSession, record: AgentStudent, actor: User | None) -> list[User]:
    org = await _active_org(db, record)
    if org is None:
        return []
    assignee = await _active_member_user(db, record.assigned_member_id, org.id)
    users = [assignee] if assignee else await _active_masters(db, org.id)
    return [u for u in users if actor is None or u.id != actor.id]


async def notify(db: AsyncSession, users: list[User], title: str, body: str, action_url: str) -> int:
    for user in users:
        item = Notification(user_id=user.id, title=title, body=body, read=False, action_url=action_url)
        db.add(item)
        await queue_deliveries(db, item, user, channels=CHANNELS)
    return len(users)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


async def student_assigned(db: AsyncSession, record: AgentStudent, member_id, actor: User) -> None:
    """N1/N9: only the new assignee hears about it, with the number of open tasks that moved with the student (AGN-016 T1)."""
    org = await _active_org(db, record)
    user = await _active_member_user(db, member_id, org.id) if org else None
    if user is None or user.id == actor.id:
        return
    open_tasks = await db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.agent_student_id == record.id, AgentTask.status == "open"))
    moved = f" {_plural(open_tasks, 'open task')} moved with them." if open_tasks else ""
    await notify(db, [user], "Student assigned to you", f"A student is now assigned to you.{moved}", STUDENTS_URL)


async def document_requested(db: AsyncSession, record: AgentStudent, document_type: str, actor: User) -> None:
    body = f"{document_label(document_type)} was requested for one of your students."
    await notify(db, await recipients(db, record, actor), "Document requested", body, DOCUMENTS_URL)


OUTCOME_TEXT = {"rejected": "rejected", "changes_required": "changes required"}  # N9: both need the agency to act


async def _document_record(db: AsyncSession, document: StudentDocument) -> AgentStudent | None:
    """The agency record that owns a document: its own, else its application's (a pre-AGN-009 row has neither)."""
    record_id = document.agent_student_id
    if record_id is None and document.application_id:
        record_id = await db.scalar(select(OverseasApplication.agent_student_id).where(OverseasApplication.id == document.application_id))
    return await db.get(AgentStudent, record_id) if record_id else None


async def document_needs_attention(db: AsyncSession, document: StudentDocument, actor: User) -> None:
    outcome = OUTCOME_TEXT.get(document.verification_status)
    record = await _document_record(db, document) if outcome else None
    if record is None:
        return
    body = f"{document_label(document.document_type)}: {outcome}."
    await notify(db, await recipients(db, record, actor), "Document needs attention", body, DOCUMENTS_URL)


async def has_commission(db: AsyncSession, application_id) -> bool:
    return await db.scalar(select(AgentCommission.id).where(AgentCommission.application_id == application_id)) is not None


async def status_changed(db: AsyncSession, application: OverseasApplication, old_status: str, actor: User, *, had_commission: bool) -> None:
    """N3: any status change to an agency application, by the agency or by EduSphere. AC3: when this change has just created the
    commission (`had_commission` is read before the AGT-003 trigger), the users the trigger told ("Commission estimated") are left out,
    so nobody gets two notices for one change."""
    if application.status == old_status or application.agent_student_id is None:
        return
    record = await db.get(AgentStudent, application.agent_student_id)
    users = await recipients(db, record, actor) if record else []
    if users and not had_commission and application.agent_id and await has_commission(db, application.id):
        agent = await db.get(User, application.agent_id)
        told = {u.id for u in await notification_recipients(db, agent)} if agent else set()
        users = [u for u in users if u.id not in told]
    university = clean_text(await db.scalar(select(University.name).where(University.id == application.university_id)))
    body = f"{university}: {stage_label(old_status)} → {stage_label(application.status)}."
    await notify(db, users, "Application status changed", body, APPLICATIONS_URL)


def ist_date(value: date | datetime) -> str:
    return (value.astimezone(INDIA) if isinstance(value, datetime) else value).strftime("%d %b %Y")


async def task_created(db: AsyncSession, record: AgentStudent, task: AgentTask, actor: User) -> None:
    """N1: the student's recipient, unless they created it. The title is user-typed, so only the due date is shown (§8)."""
    due = ist_date(task.due_at)
    # QA17-04: a task may be created already past due (AGN-016 T6); "is due 01 Oct" on 2 Oct read as a future date.
    body = f"A new task on one of your students was due {due} and is overdue." if task.due_at < datetime.now(UTC) else f"A new task on one of your students is due {due}."
    await notify(db, await recipients(db, record, actor), "New task", body, TASKS_URL)


# --- daily reminders (N4, N6, N10) ------------------------------------------------------------------------------------------------

WINDOWS = {3: "Deadline in 3 days", 1: "Deadline tomorrow", 0: "Deadline today"}
CHUNK = 200


async def _insert_reminder(db: AsyncSession, user: User, title: str, body: str, url: str, key: str) -> bool:
    """One reminder, claimed by the partial unique index: a second insert of the same key is a no-op, never a read-then-write race."""
    stmt = (
        pg_insert(Notification)
        .values(id=uuid4(), user_id=user.id, title=title, body=body, read=False, action_url=url, dedupe_key=key)
        .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Notification.dedupe_key.isnot(None))
        .returning(Notification.id)
    )
    new_id = await db.scalar(stmt)
    if new_id is None:
        return False
    await queue_deliveries(db, await db.get_one(Notification, new_id), user, channels=CHANNELS)
    return True


async def _remind(db: AsyncSession, counts: dict, user: User, title: str, body: str, url: str, key: str, **log_ids) -> None:
    """One reminder in a savepoint: a failure is counted and logged with ids only, never raised (AC6)."""
    try:
        async with db.begin_nested():
            counts["created" if await _insert_reminder(db, user, title, body, url, key) else "duplicate"] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("agn017_reminder_failed", extra={"extra_fields": {k: str(v) for k, v in {**log_ids, "user_id": user.id}.items()}})


async def _cached_recipients(db: AsyncSession, record: AgentStudent, cache: dict) -> list[User]:
    if record.id not in cache:
        cache[record.id] = await recipients(db, record, None)
    return cache[record.id]


def _deadlines(app: OverseasApplication) -> tuple:
    """`nearest_deadline`'s stage rule (N10): from the offer stage on, only the offer deadline counts."""
    if app.status in OFFER_STAGES_ON:
        return (("offer", app.offer_deadline),)
    return (("application", app.application_deadline), ("offer", app.offer_deadline))


def _window_days(today: date) -> dict[date, int]:
    """Each reminder date, mapped to how many days ahead of `today` it is."""
    return {today + timedelta(days=d): d for d in WINDOWS}


def deadline_query(today: date, last) -> Select[OverseasApplication, AgentStudent, str]:
    """One chunk of agency applications with a deadline in a reminder window, after `last` (keyset paging)."""
    days = list(_window_days(today))
    query = (
        select(OverseasApplication, AgentStudent, University.name)
        .join(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .join(University, University.id == OverseasApplication.university_id)
        .where(
            AgentStudent.status == "active",
            OverseasApplication.status.notin_([WITHDRAWN, "enrolled"]),
            or_(OverseasApplication.application_deadline.in_(days), OverseasApplication.offer_deadline.in_(days)),
        )
        .order_by(OverseasApplication.id)
        .limit(CHUNK)
    )
    return query if last is None else query.where(OverseasApplication.id > last)


async def _deadline_reminders(db: AsyncSession, today: date, counts: dict, cache: dict) -> None:
    days = _window_days(today)
    last = None
    while True:
        rows = (await db.execute(deadline_query(today, last))).all()
        if not rows:
            return
        for app, record, university in rows:
            for kind, when in _deadlines(app):
                if when not in days:
                    continue
                left = days[when]
                body = f"{clean_text(university)}: {kind} deadline {ist_date(when)}."
                for user in await _cached_recipients(db, record, cache):
                    key = f"agn017:deadline:{app.id}:{kind}:{when.isoformat()}:{left}:{user.id}"
                    await _remind(db, counts, user, WINDOWS[left], body, APPLICATIONS_URL, key, application_id=app.id)
        last = rows[-1][0].id
        await db.commit()


async def _overdue_digests(db: AsyncSession, now: datetime, today: date, counts: dict, cache: dict) -> None:
    """N4: one "Overdue tasks" notice per recipient per India day, counting open overdue tasks of active students."""
    per_record = (
        await db.execute(
            select(AgentTask.agent_student_id, func.count())
            .join(AgentStudent, AgentStudent.id == AgentTask.agent_student_id)
            .where(AgentTask.status == "open", AgentTask.due_at < now, AgentStudent.status == "active")
            .group_by(AgentTask.agent_student_id)
        )
    ).all()
    users: dict = {}
    overdue: Counter = Counter()
    for record_id, count in per_record:
        for user in await _cached_recipients(db, await db.get_one(AgentStudent, record_id), cache):
            users[user.id] = user
            overdue[user.id] += count
    for user_id, count in overdue.items():
        body = f"You have {_plural(count, 'overdue task')}."
        await _remind(db, counts, users[user_id], "Overdue tasks", body, TASKS_URL, f"agn017:overdue:{today.isoformat()}:{user_id}")
    await db.commit()


async def send_daily_reminders(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    today = now.astimezone(INDIA).date()
    counts = {"created": 0, "duplicate": 0, "failed": 0}
    cache: dict = {}
    await _deadline_reminders(db, today, counts, cache)
    await _overdue_digests(db, now, today, counts, cache)
    logger.info("agn017_reminders_done", extra={"extra_fields": {"day": today.isoformat(), **counts}})
    return counts


async def run_daily_reminders() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_daily_reminders(db, now=datetime.now(UTC))
