"""AGN-017 (DEC-SCOPE-055): agency notifications and daily reminders.

Recipients are the student's active assigned staff member, else the organisation's active Masters, never the actor (N2). In-app plus
email only (D19, N5). Bodies carry no names and no user-typed text -- the email leaves through the webhook (spec §8). Event notices ride
the caller's transaction (they never commit here), so a refused or rolled-back write leaves none.
"""

import logging
from datetime import date, datetime
from typing import get_args
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentCommission, AgentOrg, AgentOrgMember, AgentStudent, AgentTask, Notification, OverseasApplication, StudentDocument, University, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import AgentDocumentType
from app.services.agent_applications import stage_label
from app.services.agent_orgs import notification_recipients

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")  # N4: the reminder "day" (a service does not import app.api.schools; reporting/pdf.py keeps its own)
CHANNELS = ["email"]
STUDENTS_URL, DOCUMENTS_URL, APPLICATIONS_URL, TASKS_URL = (f"/overseas/agent/{s}" for s in ("students", "documents", "applications", "tasks"))
KNOWN_DOCUMENT_TYPES = frozenset(get_args(AgentDocumentType)) - {"Other"}  # "Other" names nothing; its label is user-typed


def document_label(value: str | None) -> str:
    """Only a known type is named: an uploaded document's type is free text and may carry personal data."""
    return value if value in KNOWN_DOCUMENT_TYPES else "A document"


def clean_text(value: str | None, limit: int = 120) -> str:
    """Stored text bound for an email: control characters (CR/LF included) become spaces, runs collapse, then a hard cap."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value or "").split())[:limit]


async def _org(db: AsyncSession, record: AgentStudent) -> AgentOrg | None:
    return await db.scalar(select(AgentOrg).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).where(AgentOrgMember.user_id == record.agent_id))


async def _active_masters(db: AsyncSession, org_id) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
        .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == "master", AgentOrgMember.status == "active", User.active.is_(True))
        .order_by(AgentOrgMember.seq)
    )
    return list(rows)


async def active_member_user(db: AsyncSession, member_id, org_id) -> User | None:
    """The member's login, only while both the membership and the login are active and it belongs to `org_id`."""
    row = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.id == member_id))).first()
    if row is None:
        return None
    member, user = row
    return user if member.org_id == org_id and member.status == "active" and user.active else None


async def recipients(db: AsyncSession, record: AgentStudent, actor: User | None) -> list[User]:
    org = await _org(db, record)
    if org is None or org.status != "active":
        return []
    assignee = await active_member_user(db, record.assigned_member_id, org.id) if record.assigned_member_id else None
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


async def student_assigned(db: AsyncSession, record: AgentStudent, member_id, actor: User) -> int:
    """N1/N9: only the new assignee hears about it, with the number of open tasks that moved with the student (AGN-016 T1)."""
    org = await _org(db, record)
    user = await active_member_user(db, member_id, org.id) if org is not None and org.status == "active" and member_id else None
    if user is None or user.id == actor.id:
        return 0
    open_tasks = await db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.agent_student_id == record.id, AgentTask.status == "open"))
    moved = f" {_plural(open_tasks, 'open task')} moved with them." if open_tasks else ""
    return await notify(db, [user], "Student assigned to you", f"A student is now assigned to you.{moved}", STUDENTS_URL)


async def document_requested(db: AsyncSession, record: AgentStudent, document_type: str, actor: User) -> int:
    body = f"{document_label(document_type)} was requested for one of your students."
    return await notify(db, await recipients(db, record, actor), "Document requested", body, DOCUMENTS_URL)


OUTCOME_TEXT = {"rejected": "rejected", "changes_required": "changes required"}  # N9: both need the agency to act


async def _document_record(db: AsyncSession, document: StudentDocument) -> AgentStudent | None:
    """The agency record that owns a document: its own, else its application's (a pre-AGN-009 row has neither)."""
    record_id = document.agent_student_id
    if record_id is None and document.application_id:
        record_id = await db.scalar(select(OverseasApplication.agent_student_id).where(OverseasApplication.id == document.application_id))
    return await db.get(AgentStudent, record_id) if record_id else None


async def document_needs_attention(db: AsyncSession, document: StudentDocument, actor: User) -> int:
    outcome = OUTCOME_TEXT.get(document.verification_status)
    record = await _document_record(db, document) if outcome else None
    if record is None:
        return 0
    body = f"{document_label(document.document_type)}: {outcome}."
    return await notify(db, await recipients(db, record, actor), "Document needs attention", body, DOCUMENTS_URL)


async def has_commission(db: AsyncSession, application_id) -> bool:
    return await db.scalar(select(AgentCommission.id).where(AgentCommission.application_id == application_id)) is not None


async def status_changed(db: AsyncSession, application: OverseasApplication, old_status: str, actor: User, *, had_commission: bool) -> int:
    """N3: any status change to an agency application, by the agency or by EduSphere. AC3: when this change has just created the
    commission (`had_commission` is read before the AGT-003 trigger), the users the trigger told ("Commission estimated") are left out,
    so nobody gets two notices for one change."""
    if application.status == old_status or application.agent_student_id is None:
        return 0
    record = await db.get(AgentStudent, application.agent_student_id)
    users = await recipients(db, record, actor) if record else []
    if users and not had_commission and application.agent_id and await has_commission(db, application.id):
        agent = await db.get(User, application.agent_id)
        told = {u.id for u in await notification_recipients(db, agent)} if agent else set()
        users = [u for u in users if u.id not in told]
    university = clean_text(await db.scalar(select(University.name).where(University.id == application.university_id)))
    body = f"{university}: {stage_label(old_status)} → {stage_label(application.status)}."
    return await notify(db, users, "Application status changed", body, APPLICATIONS_URL)


def ist_date(value: date | datetime) -> str:
    return (value.astimezone(INDIA) if isinstance(value, datetime) else value).strftime("%d %b %Y")


async def task_created(db: AsyncSession, record: AgentStudent, task: AgentTask, actor: User) -> int:
    """N1: the student's recipient, unless they created it. The title is user-typed, so only the due date is shown (§8)."""
    body = f"A new task on one of your students is due {ist_date(task.due_at)}."
    return await notify(db, await recipients(db, record, actor), "New task", body, TASKS_URL)
