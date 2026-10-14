"""mgmt-027 (spec MD1-MD14): management discussions & decisions, EVID-017 §27.

Partners and the super admin (M13 operational tier) record discussions; a decision with a responsible person reaches that person as
the decision line only (MD8/MD14), with an in-app + email notification (MD9). Every write adds a `management_audit` row (kind
`mgmt.decision`, field names only) in the caller's transaction; the routes in `api/management_discussions.py` commit once.
Spec: docs/superpowers/specs/2026-10-12-mgmt-027-discussions-decisions-design.md.
"""

import hashlib
import logging
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ManagementDiscussion,
    ManagementDiscussionAttachment,
    ManagementDiscussionParticipant,
    Notification,
    User,
)
from app.notifications.dispatch import queue_deliveries
from app.services import management_audit
from app.services.ledger import field_error
from app.services.management_access import STAFF_ROLES, can_view_operational, require_management
from app.services.storage import storage

logger = logging.getLogger("app.management")
STORAGE_PREFIX = "management-discussions"
MAX_ATTACHMENTS = 10
PENDING = ("open", "in_progress")
STATUS_LABELS = {"open": "Open", "in_progress": "In Progress", "completed": "Completed", "cancelled": "Cancelled"}
MY_DECISIONS_URL = "/account/management-decisions"
# The fields a write may change; the ones whose change the responsible person is told about (MD9).
FIELDS = ("topic", "discussion_date", "department", "points", "decision", "responsible_user_id", "deadline", "status", "follow_up_date")
LINE_FIELDS = ("decision", "deadline", "status")

OPERATIONAL_ONLY = "Operational management access required"
NOT_FOUND = "Discussion not found"
DECISION_NOT_FOUND = "Decision not found"
ATTACHMENT_NOT_FOUND = "Attachment not found"
CANCELLED = "This decision was cancelled; it can't be updated"
TOO_MANY = f"A discussion can have at most {MAX_ATTACHMENTS} attachments"


def require_operational(user: User) -> User:
    """MD7: partner and super_admin. The accountant (finance tier only) gets its own message."""
    require_management(user)
    if not can_view_operational(user):
        raise HTTPException(403, OPERATIONAL_ONLY)
    return user


def log(event: str, user: User, discussion_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "discussion_id": str(discussion_id), **extra}})


async def load(db: AsyncSession, discussion_id, *, lock: bool = False) -> ManagementDiscussion:
    stmt = select(ManagementDiscussion).where(ManagementDiscussion.id == discussion_id)
    discussion = await db.scalar(stmt.with_for_update() if lock else stmt)
    if discussion is None:
        raise HTTPException(404, NOT_FOUND)
    return discussion


async def load_mine(db: AsyncSession, user: User, discussion_id, *, lock: bool = False) -> ManagementDiscussion:
    """MD8: the caller's own decision, or 404 -- another user's id never reveals that it exists. Checked after the lock (MD13)."""
    stmt = select(ManagementDiscussion).where(ManagementDiscussion.id == discussion_id, ManagementDiscussion.responsible_user_id == user.id)
    discussion = await db.scalar(stmt.with_for_update() if lock else stmt)
    if discussion is None:
        raise HTTPException(404, DECISION_NOT_FOUND)
    return discussion


# --- rules (MD2, MD5, MD6) ----------------------------------------------------------------------------------------------------
async def staff_ids(db: AsyncSession, ids) -> set:
    """The ids among `ids` that are active staff users."""
    if not ids:
        return set()
    return set((await db.scalars(select(User.id).where(User.id.in_(set(ids)), User.active.is_(True), User.role.in_(STAFF_ROLES)))).all())


async def check(db: AsyncSession, state: dict, participant_ids: list | None, previous_responsible=None) -> None:
    """The merged state of a create or change. Raises the first broken rule as a field-located 422. A person named earlier who has
    since left is not re-checked, so a discussion can still be cancelled or reassigned."""
    responsible = state["responsible_user_id"]
    if responsible not in (None, previous_responsible) and responsible not in await staff_ids(db, [responsible]):
        raise field_error("responsible_user_id", "Choose an active staff member")
    if participant_ids and len(await staff_ids(db, participant_ids)) != len(set(participant_ids)):
        raise field_error("participant_ids", "Participants must be active staff members")
    if responsible is not None and not state["decision"]:
        raise field_error("decision", "Record the decision before naming a responsible person")
    if state["deadline"] is not None and not state["decision"]:
        raise field_error("decision", "Record the decision before setting a deadline")
    for field, label in (("deadline", "The deadline"), ("follow_up_date", "The follow-up date")):
        if state[field] is not None and state[field] < state["discussion_date"]:
            raise field_error(field, f"{label} can't be before the discussion date")


async def set_participants(db: AsyncSession, discussion: ManagementDiscussion, ids: list) -> None:
    await db.execute(delete(ManagementDiscussionParticipant).where(ManagementDiscussionParticipant.discussion_id == discussion.id))
    db.add_all(ManagementDiscussionParticipant(discussion_id=discussion.id, user_id=i) for i in dict.fromkeys(ids))


async def participant_ids(db: AsyncSession, discussion_id) -> list:
    return list((await db.scalars(select(ManagementDiscussionParticipant.user_id).where(ManagementDiscussionParticipant.discussion_id == discussion_id))).all())


# --- audit + notification (MD9, MD11) ------------------------------------------------------------------------------------------
def audit(db: AsyncSession, user: User, discussion: ManagementDiscussion, changed: list[str], previous_status: str | None) -> None:
    """MD11: `decide` when the decision text changed, `complete` when the status became completed, `update` otherwise."""
    if "decision" in changed:
        verb = "decide"
    elif "status" in changed and discussion.status == "completed" and previous_status != "completed":
        verb = "complete"
    else:
        verb = "update"
    management_audit.record(db, user, "mgmt.decision", verb, str(discussion.id), fields=changed)


def line(discussion: ManagementDiscussion) -> str:
    deadline = discussion.deadline.strftime("%d %b %Y") if discussion.deadline else "no deadline"
    return f"{discussion.decision} — {deadline} — {STATUS_LABELS[discussion.status]}"


async def notify(db: AsyncSession, discussion: ManagementDiscussion, *, assigned: bool) -> None:
    """MD9: the decision line only -- never the topic or notes."""
    recipient = await db.get_one(User, discussion.responsible_user_id)
    title = "A management decision was assigned to you" if assigned else "A management decision you are responsible for changed"
    note = Notification(user_id=recipient.id, title=title, body=line(discussion), read=False, action_url=MY_DECISIONS_URL)
    db.add(note)
    await queue_deliveries(db, note, recipient)


async def notify_after_write(db: AsyncSession, actor: User, discussion: ManagementDiscussion, changed: list[str], previous_responsible) -> None:
    if discussion.responsible_user_id is None or discussion.responsible_user_id == actor.id:
        return
    if discussion.responsible_user_id != previous_responsible:
        await notify(db, discussion, assigned=True)
    elif any(field in changed for field in LINE_FIELDS):
        await notify(db, discussion, assigned=False)


# --- serializers --------------------------------------------------------------------------------------------------------------
def person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name, "role": user.role} if user else None


async def people(db: AsyncSession, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()}


def row_out(d: ManagementDiscussion, who: dict) -> dict:
    return {
        "id": d.id,
        "topic": d.topic,
        "discussion_date": d.discussion_date,
        "department": d.department,
        "decision": d.decision,
        "responsible": person(who.get(d.responsible_user_id)),
        "deadline": d.deadline,
        "status": d.status,
        "follow_up_date": d.follow_up_date,
        "meeting_id": d.meeting_id,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def attachment_out(a: ManagementDiscussionAttachment) -> dict:
    return {"id": a.id, "name": a.name, "content_type": a.content_type, "shareable": a.shareable, "created_at": a.created_at}


async def attachments(db: AsyncSession, discussion_ids, *, shareable_only: bool = False) -> list[ManagementDiscussionAttachment]:
    stmt = select(ManagementDiscussionAttachment).where(ManagementDiscussionAttachment.discussion_id.in_(discussion_ids))
    if shareable_only:
        stmt = stmt.where(ManagementDiscussionAttachment.shareable.is_(True))
    return list((await db.scalars(stmt.order_by(ManagementDiscussionAttachment.created_at, ManagementDiscussionAttachment.id))).all())


async def detail(db: AsyncSession, discussion: ManagementDiscussion) -> dict:
    await db.refresh(discussion)
    members = await participant_ids(db, discussion.id)
    who = await people(db, [discussion.responsible_user_id, discussion.created_by_user_id, discussion.updated_by_user_id, *members])
    return {
        **row_out(discussion, who),
        "points": discussion.points,
        "participants": sorted((person(who[i]) for i in members), key=lambda p: p["full_name"].lower()),
        "attachments": [attachment_out(a) for a in await attachments(db, [discussion.id])],
        "created_by": person(who.get(discussion.created_by_user_id)),
        "updated_by": person(who.get(discussion.updated_by_user_id)),
    }


async def page(db: AsyncSession, *, status: str | None, responsible, pending: bool, limit: int, offset: int) -> dict:
    """MD12: pending = a named person, open or in progress, by deadline (none last); otherwise newest discussion first."""
    where: list = []
    order: tuple
    if status:
        where.append(ManagementDiscussion.status == status)
    if responsible:
        where.append(ManagementDiscussion.responsible_user_id == responsible)
    if pending:
        where += [ManagementDiscussion.responsible_user_id.is_not(None), ManagementDiscussion.status.in_(PENDING)]
        order = (nulls_last(ManagementDiscussion.deadline.asc()), ManagementDiscussion.created_at, ManagementDiscussion.id)
    else:
        order = (ManagementDiscussion.discussion_date.desc(), ManagementDiscussion.created_at.desc(), ManagementDiscussion.id)
    total = await db.scalar(select(func.count()).select_from(ManagementDiscussion).where(*where))
    rows = (await db.scalars(select(ManagementDiscussion).where(*where).order_by(*order).limit(limit).offset(offset))).all()
    who = await people(db, [r.responsible_user_id for r in rows])
    return {"items": [row_out(r, who) for r in rows], "total": total, "limit": limit, "offset": offset}


async def options(db: AsyncSession) -> dict:
    users = (await db.scalars(select(User).where(User.active.is_(True), User.role.in_(STAFF_ROLES)).order_by(func.lower(User.full_name), User.id))).all()
    return {"users": [person(u) for u in users]}


# --- the responsible person's slice (MD8, MD14) --------------------------------------------------------------------------------
def my_out(d: ManagementDiscussion, files: list[ManagementDiscussionAttachment]) -> dict:
    """Only these keys ever leave for the responsible person (AC3)."""
    return {
        "id": d.id,
        "decision": d.decision,
        "deadline": d.deadline,
        "status": d.status,
        "updated_at": d.updated_at,
        "attachments": [{"id": a.id, "name": a.name, "content_type": a.content_type} for a in files if a.discussion_id == d.id],
    }


async def my_decisions(db: AsyncSession, user: User) -> list[dict]:
    """Open and in-progress first by deadline (none last), then completed; cancelled lines are not listed."""
    rows = (
        await db.scalars(
            select(ManagementDiscussion)
            .where(ManagementDiscussion.responsible_user_id == user.id, ManagementDiscussion.status != "cancelled")
            .order_by(ManagementDiscussion.status == "completed", nulls_last(ManagementDiscussion.deadline.asc()), ManagementDiscussion.id)
        )
    ).all()
    files = await attachments(db, [r.id for r in rows], shareable_only=True) if rows else []
    return [my_out(r, files) for r in rows]


async def my_decision(db: AsyncSession, discussion: ManagementDiscussion) -> dict:
    await db.refresh(discussion)
    return my_out(discussion, await attachments(db, [discussion.id], shareable_only=True))


# --- attachments (MD10) --------------------------------------------------------------------------------------------------------
def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def load_attachment(db: AsyncSession, discussion_id, attachment_id, *, shareable_only: bool = False) -> ManagementDiscussionAttachment:
    stmt = select(ManagementDiscussionAttachment).where(ManagementDiscussionAttachment.id == attachment_id, ManagementDiscussionAttachment.discussion_id == discussion_id)
    if shareable_only:
        stmt = stmt.where(ManagementDiscussionAttachment.shareable.is_(True))
    found = await db.scalar(stmt)
    if found is None:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    return found


async def attachment_count(db: AsyncSession, discussion_id) -> int:
    return await db.scalar(select(func.count()).select_from(ManagementDiscussionAttachment).where(ManagementDiscussionAttachment.discussion_id == discussion_id)) or 0


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("discussion_attachment_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object no committed row points at; a failure leaves an orphan, logged by key digest."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("discussion_attachment_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read(attachment: ManagementDiscussionAttachment) -> bytes:
    try:
        return storage.read_bytes(attachment.storage_key)
    except FileNotFoundError:
        logger.warning("discussion_attachment_missing", extra={"extra_fields": {"attachment_id": str(attachment.id), "key_digest": _digest(attachment.storage_key)}})
        raise HTTPException(404, ATTACHMENT_NOT_FOUND) from None


def download_name(discussion: ManagementDiscussion, attachment: ManagementDiscussionAttachment, extension: str) -> str:
    """Built here, never the uploaded name."""
    return f"discussion-attachment-{discussion.discussion_date.isoformat()}-{str(attachment.id)[:8]}.{extension}"
