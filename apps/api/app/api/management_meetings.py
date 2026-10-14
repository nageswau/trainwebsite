"""mgmt-029 (spec MM1-MM14): management meetings + minutes chain. `router` is the operational tier's (partner, super_admin; M13);
`me_router` is each participant's own meetings (MM12). Every write locks the meeting row, adds a management audit row and commits once
here; decisions and tasks recorded from the minutes go through mgmt-027 / mgmt-028's own rules, notifications and audit. A log line
follows the commit (ids and field names only)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import ManagementDiscussion, ManagementMeeting, ManagementTask, User
from app.schemas import (
    DiscussionOptions,
    MgmtMeetingCreate,
    MgmtMeetingDecisionIn,
    MgmtMeetingDetail,
    MgmtMeetingKind,
    MgmtMeetingMinutesIn,
    MgmtMeetingPage,
    MgmtMeetingStatus,
    MgmtMeetingTaskIn,
    MgmtMeetingUpdate,
    MyMgmtMeetingPage,
)
from app.services import management_audit
from app.services import management_discussions as discussions
from app.services import management_meetings as svc
from app.services import management_tasks as tasks
from app.services.ledger import field_error

router = APIRouter(prefix="/management/meetings", tags=["management-meetings"])
me_router = APIRouter(prefix="/me/management-meetings", tags=["management-meetings"])


@router.get("", response_model=MgmtMeetingPage)
async def list_meetings(
    date_from: date | None = None,
    date_to: date | None = None,
    kind: MgmtMeetingKind | None = None,
    status: MgmtMeetingStatus | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MM11: the calendar's range by IST day (at most 62 days); without dates, today's meetings."""
    discussions.require_operational(user)
    first, last = svc.range_of(date_from, date_to)
    return await svc.calendar(db, date_from=first, date_to=last, kind=kind, status=status)


@router.get("/options", response_model=DiscussionOptions)
async def meeting_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The form's participants, decision owners and task owners: active staff users (MM5)."""
    discussions.require_operational(user)
    return await discussions.options(db)


@router.post("", status_code=201, response_model=MgmtMeetingDetail)
async def create_meeting(payload: MgmtMeetingCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    state = payload.model_dump(exclude={"participant_ids", "status"})
    await svc.check(db, {**state, "status": "scheduled"}, set(payload.participant_ids))
    meeting = ManagementMeeting(**state, status="scheduled", created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(meeting)
    await db.flush()
    await svc.set_participants(db, meeting, payload.participant_ids)
    fields = [f for f in svc.FIELDS if f != "status" and state[f] is not None] + (["participants"] if payload.participant_ids else [])
    svc.audit(db, user, meeting, "create", fields)
    await svc.notify_after_write(db, user, meeting, fields, [], list(dict.fromkeys(payload.participant_ids)))
    await db.commit()
    svc.log("meeting_created", user, meeting.id)
    return await svc.detail(db, meeting)


@router.get("/{meeting_id}", response_model=MgmtMeetingDetail)
async def get_meeting(meeting_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    return await svc.detail(db, await svc.load(db, meeting_id))


@router.patch("/{meeting_id}", response_model=MgmtMeetingDetail)
async def change_meeting(meeting_id: UUID, payload: MgmtMeetingUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A partial change; nothing changed = nothing recorded. Participants hear about an invitation, a new time or a cancellation."""
    discussions.require_operational(user)
    meeting = await svc.load(db, meeting_id, lock=True)
    sent = payload.model_dump(exclude_unset=True)
    members = sent.pop("participant_ids", None)
    before = {f: getattr(meeting, f) for f in svc.FIELDS}
    state = {**before, **sent}
    current = await svc.participant_ids_of(db, meeting.id)
    after = list(dict.fromkeys(members)) if members is not None else current
    await svc.check(db, state, set(after) - set(current), before)
    changed = [f for f in svc.FIELDS if state[f] != before[f]]
    if set(after) != set(current):
        changed.append("participants")
    if not changed:
        return await svc.detail(db, meeting)
    for field in changed:
        if field != "participants":
            setattr(meeting, field, state[field])
    if "participants" in changed:
        await svc.set_participants(db, meeting, after)
    meeting.updated_by_user_id = user.id
    svc.audit(db, user, meeting, "update", changed)
    await svc.notify_after_write(db, user, meeting, changed, current, after)
    await db.commit()
    svc.log("meeting_changed", user, meeting.id, changed=changed)
    return await svc.detail(db, meeting)


@router.post("/{meeting_id}/minutes", response_model=MgmtMeetingDetail)
async def record_minutes(meeting_id: UUID, payload: MgmtMeetingMinutesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MM6: the first record completes the meeting (`complete`); a later one replaces the text (`update`)."""
    discussions.require_operational(user)
    meeting = await svc.load(db, meeting_id, lock=True)
    if meeting.minutes == payload.minutes:
        return await svc.detail(db, meeting)
    first = svc.record_minutes(meeting, payload.minutes)
    meeting.updated_by_user_id = user.id
    svc.audit(db, user, meeting, "complete" if first else "update", ["minutes"])
    await db.commit()
    svc.log("meeting_minutes_recorded", user, meeting.id, first=first)
    return await svc.detail(db, meeting)


@router.post("/{meeting_id}/decisions", status_code=201, response_model=MgmtMeetingDetail)
async def add_decision(meeting_id: UUID, payload: MgmtMeetingDecisionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MM8: a mgmt-027 discussion dated the meeting's IST day, with the meeting's participants who are still active staff."""
    discussions.require_operational(user)
    meeting = await svc.load(db, meeting_id, lock=True)
    svc.require_minutes(meeting)
    members = list(await discussions.staff_ids(db, await svc.participant_ids_of(db, meeting.id)))
    state = {
        "topic": payload.topic or meeting.title,
        "discussion_date": svc.ist_day(meeting.starts_at),
        "department": None,
        "points": None,
        "decision": payload.decision,
        "responsible_user_id": payload.responsible_user_id,
        "deadline": payload.deadline,
        "status": "open",
        "follow_up_date": None,
    }
    await discussions.check(db, state, members)
    discussion = ManagementDiscussion(**state, meeting_id=meeting.id, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(discussion)
    await db.flush()
    await discussions.set_participants(db, discussion, members)
    fields = [f for f in discussions.FIELDS if state[f] is not None] + (["participants"] if members else [])
    management_audit.record(db, user, "mgmt.decision", "create", str(discussion.id), fields=fields)
    await discussions.notify_after_write(db, user, discussion, fields, None)
    await db.commit()
    svc.log("meeting_decision_added", user, meeting.id, discussion_id=str(discussion.id))
    return await svc.detail(db, meeting)


@router.post("/{meeting_id}/tasks", status_code=201, response_model=MgmtMeetingDetail)
async def add_task(meeting_id: UUID, payload: MgmtMeetingTaskIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MM9: a mgmt-028 task linked to the meeting, or to one of its decisions."""
    discussions.require_operational(user)
    meeting = await svc.load(db, meeting_id, lock=True)
    svc.require_minutes(meeting)
    source, source_id = "meeting", meeting.id
    if payload.decision_id is not None:
        found = await db.scalar(select(ManagementDiscussion.id).where(ManagementDiscussion.id == payload.decision_id, ManagementDiscussion.meeting_id == meeting.id))
        if found is None:
            raise field_error("decision_id", "Choose one of this meeting's decisions")
        source, source_id = "decision", found
    state = payload.model_dump(exclude={"decision_id"})
    await tasks.check(db, state)
    task = ManagementTask(**state, status="open", source=source, source_id=source_id, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(task)
    await db.flush()
    management_audit.record(db, user, "mgmt.task", "create", str(task.id), fields=list(tasks.FIELDS))
    await tasks.notify_after_write(db, user, task, list(tasks.FIELDS), None)
    await db.commit()
    svc.log("meeting_task_added", user, meeting.id, task_id=str(task.id))
    return await svc.detail(db, meeting)


# --- the participant's slice (MM12) ----------------------------------------------------------------------------------------------
@me_router.get("", response_model=MyMgmtMeetingPage)
async def my_meetings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.mine(db, user)
