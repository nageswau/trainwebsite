"""AGN-017 (DEC-SCOPE-055): agency notifications and daily reminders.

Recipients are the student's active assigned staff member, else the organisation's active Masters, never the actor (N2). In-app plus
email only (D19, N5). Bodies carry no names and no user-typed text -- the email leaves through the webhook (spec §8). Event notices ride
the caller's transaction (they never commit here), so a refused or rolled-back write leaves none.
"""

import logging
from typing import get_args
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, AgentStudent, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import AgentDocumentType

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")  # N4: the reminder "day" (a service does not import app.api.schools; reporting/pdf.py keeps its own)
CHANNELS = ["email"]
STUDENTS_URL, DOCUMENTS_URL, APPLICATIONS_URL, TASKS_URL = (f"/overseas/agent/{s}" for s in ("students", "documents", "applications", "tasks"))
KNOWN_DOCUMENT_TYPES = frozenset(get_args(AgentDocumentType))


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
