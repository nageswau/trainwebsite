"""mgmt-029 (spec MM1-MM14): management meetings and the minutes chain, EVID-017 §29 (Meeting → Minutes → Decision → Task → Deadline →
Completion).

Partners and the super admin (M13 operational tier) schedule meetings, record the minutes and, from them, the mgmt-027 decisions and
mgmt-028 tasks that came out of the meeting -- created through those items' own rules, notifications and audit. The meeting's detail
rolls the chain's completion up (MM10). Participants see only their meetings' time, place, link and agenda (MM12). Every write adds a
`management_audit` row (kind `mgmt.meeting`, field names only) in the caller's transaction; the routes in `api/management_meetings.py`
commit once. Logs carry ids and field names, never titles or minutes.
Spec: docs/superpowers/specs/2026-10-14-mgmt-029-management-meetings-design.md.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ManagementDiscussion, ManagementMeeting, ManagementMeetingParticipant, ManagementTask, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services import management_audit
from app.services.bdm_travel import INDIA, india_today
from app.services.ledger import field_error
from app.services.management_discussions import people, person, staff_ids

logger = logging.getLogger("app.management")
FIELDS = ("title", "kind", "starts_at", "mode", "location", "meeting_url", "agenda", "status")
KIND_LABELS = {
    "partner": "Partner meeting",
    "department": "Department meeting",
    "school": "School meeting",
    "university": "University meeting",
    "agent": "Agent meeting",
    "recruiter": "Recruiter meeting",
    "marketing_review": "Marketing review",
}
WINDOW = timedelta(days=366)  # MM7
MAX_RANGE_DAYS = 62  # MM11: a month view and its neighbours' edges
RECENT_DAYS = 7  # MM12: a participant also sees the last week's meetings
MY_MEETINGS_URL = "/account/management-tasks#meetings"

NOT_FOUND = "Meeting not found"
CANCELLED = "This meeting was cancelled; it can't be changed"
COMPLETED_TIME = "The minutes are recorded; the meeting's time can't change"
COMPLETED_CANCEL = "A meeting with minutes can't be cancelled"
NOT_STARTED = "Minutes can be recorded once the meeting has started"
NO_MINUTES = "Record the minutes before adding decisions or tasks"


def log(event: str, user: User, meeting_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "meeting_id": str(meeting_id), **extra}})


def ist_day(moment: datetime) -> date:
    return moment.astimezone(INDIA).date()


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, INDIA)


# --- rules (MM4-MM7) -----------------------------------------------------------------------------------------------------------
async def load(db: AsyncSession, meeting_id, *, lock: bool = False) -> ManagementMeeting:
    stmt = select(ManagementMeeting).where(ManagementMeeting.id == meeting_id)
    meeting = await db.scalar((stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True))
    if meeting is None:
        raise HTTPException(404, NOT_FOUND)
    return meeting


async def check(db: AsyncSession, state: dict, added: set, before: dict | None = None) -> None:
    """The merged state of a create or change; only fields set or changed are checked, and only the participants `added`, so one
    who has since left stays (MM5)."""
    if before is not None:
        if before["status"] == "cancelled":
            raise HTTPException(409, CANCELLED)
        if before["status"] == "completed" and state["starts_at"] != before["starts_at"]:
            raise HTTPException(409, COMPLETED_TIME)
        if before["status"] == "completed" and state["status"] == "cancelled":
            raise HTTPException(409, COMPLETED_CANCEL)
    if (before is None or state["starts_at"] != before["starts_at"]) and abs(state["starts_at"] - datetime.now(UTC)) > WINDOW:
        raise field_error("starts_at", "Choose a time within a year from now, before or after")
    if added and len(await staff_ids(db, added)) != len(added):
        raise field_error("participant_ids", "Participants must be active staff members")


async def participant_ids_of(db: AsyncSession, meeting_id) -> list:
    return list((await db.scalars(select(ManagementMeetingParticipant.user_id).where(ManagementMeetingParticipant.meeting_id == meeting_id))).all())


async def set_participants(db: AsyncSession, meeting: ManagementMeeting, ids: list) -> None:
    await db.execute(delete(ManagementMeetingParticipant).where(ManagementMeetingParticipant.meeting_id == meeting.id))
    db.add_all(ManagementMeetingParticipant(meeting_id=meeting.id, user_id=i) for i in dict.fromkeys(ids))


def require_minutes(meeting: ManagementMeeting) -> None:
    """MM8/MM9: the chain starts from recorded minutes; a cancelled meeting has none."""
    if meeting.status == "cancelled":
        raise HTTPException(409, CANCELLED)
    if meeting.minutes is None:
        raise HTTPException(409, NO_MINUTES)


def record_minutes(meeting: ManagementMeeting, minutes: str) -> bool:
    """MM6: returns True when this is the first record (the meeting completes)."""
    if meeting.status == "cancelled":
        raise HTTPException(409, CANCELLED)
    if meeting.starts_at > datetime.now(UTC):
        raise HTTPException(409, NOT_STARTED)
    first = meeting.minutes_recorded_at is None
    meeting.minutes = minutes
    meeting.status = "completed"
    if first:
        meeting.minutes_recorded_at = datetime.now(UTC)
    return first


# --- notification (MM13) -------------------------------------------------------------------------------------------------------
def line(meeting: ManagementMeeting) -> str:
    """ "Monthly partner meeting — 14 Oct 2026 10:00 IST — Partner meeting": never the link, agenda or minutes."""
    return f"{meeting.title} — {meeting.starts_at.astimezone(INDIA).strftime('%d %b %Y %H:%M')} IST — {KIND_LABELS[meeting.kind]}"


async def _notify(db: AsyncSession, ids, title: str, meeting: ManagementMeeting) -> None:
    for recipient in (await people(db, ids)).values():
        note = Notification(user_id=recipient.id, title=title, body=line(meeting), read=False, action_url=MY_MEETINGS_URL)
        db.add(note)
        await queue_deliveries(db, note, recipient)


async def notify_after_write(db: AsyncSession, actor: User, meeting: ManagementMeeting, changed: list[str], before_ids: list, after_ids: list) -> None:
    """New participants are invited; everyone else hears about a new time or a cancellation. Never the actor."""
    added = [i for i in after_ids if i not in before_ids and i != actor.id]
    rest = [i for i in after_ids if i in before_ids and i != actor.id]
    await _notify(db, added, "You were invited to a management meeting", meeting)
    if "status" in changed and meeting.status == "cancelled":
        await _notify(db, rest, "A management meeting was cancelled", meeting)
    elif "starts_at" in changed:
        await _notify(db, rest, "A management meeting was rescheduled", meeting)


def audit(db: AsyncSession, user: User, meeting: ManagementMeeting, verb: str, changed: list[str]) -> None:
    management_audit.record(db, user, "mgmt.meeting", verb, str(meeting.id), fields=changed)


# --- reads ---------------------------------------------------------------------------------------------------------------------
def row_out(meeting: ManagementMeeting, count: int) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "kind": meeting.kind,
        "starts_at": meeting.starts_at,
        "mode": meeting.mode,
        "location": meeting.location,
        "meeting_url": meeting.meeting_url,
        "status": meeting.status,
        "participant_count": count,
    }


def range_of(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """MM11: both or neither; neither = today (IST). At most 62 days, in order."""
    if date_from is None and date_to is None:
        today = india_today()
        return today, today
    if date_from is None or date_to is None:
        raise HTTPException(422, "Give both date_from and date_to, or neither")
    if date_to < date_from or (date_to - date_from).days >= MAX_RANGE_DAYS:
        raise HTTPException(422, f"date_to must be on or after date_from, at most {MAX_RANGE_DAYS} days")
    return date_from, date_to


async def calendar(db: AsyncSession, *, date_from: date, date_to: date, kind: str | None, status: str | None) -> dict:
    count = select(func.count()).where(ManagementMeetingParticipant.meeting_id == ManagementMeeting.id).scalar_subquery()
    where = [ManagementMeeting.starts_at >= _day_start(date_from), ManagementMeeting.starts_at < _day_start(date_to + timedelta(days=1))]
    if kind:
        where.append(ManagementMeeting.kind == kind)
    if status:
        where.append(ManagementMeeting.status == status)
    rows = (await db.execute(select(ManagementMeeting, count).where(*where).order_by(ManagementMeeting.starts_at, ManagementMeeting.id))).all()
    return {"items": [row_out(m, n) for m, n in rows], "date_from": date_from, "date_to": date_to, "today": india_today()}


def _task_out(task: ManagementTask, who: dict) -> dict:
    return {"id": task.id, "title": task.title, "owner": person(who[task.owner_user_id]), "priority": task.priority, "deadline": task.deadline, "status": task.status}


async def chain(db: AsyncSession, meeting: ManagementMeeting) -> dict:
    """MM10: the meeting's decisions, each with its tasks, then the meeting's own tasks, and the roll-up over every non-cancelled item."""
    decisions = list((await db.scalars(select(ManagementDiscussion).where(ManagementDiscussion.meeting_id == meeting.id).order_by(ManagementDiscussion.created_at, ManagementDiscussion.id))).all())
    linked = or_(
        (ManagementTask.source == "meeting") & (ManagementTask.source_id == meeting.id),
        (ManagementTask.source == "decision") & ManagementTask.source_id.in_([d.id for d in decisions]),
    )
    tasks = list((await db.scalars(select(ManagementTask).where(linked).order_by(ManagementTask.deadline, ManagementTask.created_at, ManagementTask.id))).all())
    who = await people(db, [d.responsible_user_id for d in decisions] + [t.owner_user_id for t in tasks])
    items = [d.status for d in decisions] + [t.status for t in tasks]
    live = [s for s in items if s != "cancelled"]
    return {
        "decisions": [
            {
                "id": d.id,
                "decision": d.decision,
                "responsible": person(who.get(d.responsible_user_id)),
                "deadline": d.deadline,
                "status": d.status,
                "tasks": [_task_out(t, who) for t in tasks if t.source == "decision" and t.source_id == d.id],
            }
            for d in decisions
        ],
        "tasks": [_task_out(t, who) for t in tasks if t.source == "meeting"],
        "progress": {"done": live.count("completed"), "total": len(live)},
    }


async def detail(db: AsyncSession, meeting: ManagementMeeting) -> dict:
    await db.refresh(meeting)
    members = await participant_ids_of(db, meeting.id)
    who = await people(db, [meeting.created_by_user_id, meeting.updated_by_user_id, *members])
    return {
        **row_out(meeting, len(members)),
        "agenda": meeting.agenda,
        "minutes": meeting.minutes,
        "minutes_recorded_at": meeting.minutes_recorded_at,
        "participants": sorted((person(who[i]) for i in members), key=lambda p: p["full_name"].lower()),
        **await chain(db, meeting),
        "created_by": person(who.get(meeting.created_by_user_id)),
        "updated_by": person(who.get(meeting.updated_by_user_id)),
        "created_at": meeting.created_at,
        "updated_at": meeting.updated_at,
    }


async def mine(db: AsyncSession, user: User) -> dict:
    """MM12: the caller's meetings from the last 7 IST days on; cancelled ones only when recent (so a participant sees the change)."""
    since = _day_start(india_today() - timedelta(days=RECENT_DAYS - 1))
    rows = (
        await db.scalars(
            select(ManagementMeeting)
            .join(ManagementMeetingParticipant, ManagementMeetingParticipant.meeting_id == ManagementMeeting.id)
            .where(ManagementMeetingParticipant.user_id == user.id, ManagementMeeting.starts_at >= since)
            .order_by(ManagementMeeting.starts_at, ManagementMeeting.id)
            .limit(100)
        )
    ).all()
    keys = ("id", "title", "kind", "starts_at", "mode", "location", "meeting_url", "agenda", "status")
    return {"items": [{key: getattr(m, key) for key in keys} for m in rows]}
