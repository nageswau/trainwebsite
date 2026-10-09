"""upc-009 (DEC-SCOPE-145, spec §1, §3): university meetings -- who reads, schedules and acts, the §7 record, the stage advance, the
follow-ups, the four lists and output.

Functions only; nothing here commits -- the route owns the transaction. Every partnership reader reads every meeting (MG14); only the
responsible employee or the scheduler changes one (MG15). Scheduling and completing run on the university row the route locked, so the
stage advance (MG13) and the upc-020 follow-ups (MG11/MG12) are written under it. Logs and audit rows carry ids, codes, keys, counts and
field names only -- never agenda, notes, discussion points, decisions, next action or reasons.
"""

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    UNIVERSITY_MEETING_CODE_SEQ,
    AuditLog,
    Country,
    PartnershipTask,
    University,
    UniversityContact,
    UniversityMeeting,
    UniversityMeetingEvent,
    UniversityMeetingParticipant,
    User,
)
from app.schemas import UniversityMeetingComplete, UniversityMeetingIn, UniversityMeetingUpdate
from app.services import partnership_pipeline as pipeline
from app.services import partnership_tasks as tasks
from app.services import partnership_universities as unis
from app.services import university_visits as visits
from app.services.bdm_travel import india_today
from app.services.partnership import partnership_context
from app.services.recruiter_meetings import check_time, field_error
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Meeting not found"
READ_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # MG14
CREATE_ROLES = frozenset({"partnership_manager", "partnership_head"})  # MG15
ACTOR_REFUSAL = "Only the meeting's responsible employee or the person who scheduled it can change it"
STATE_REFUSALS = {"completed": "This meeting's outcome is already recorded", "cancelled": "This meeting was cancelled"}
START_PAST = "Choose a meeting time in the future"
START_FAR = "Choose a meeting time within the next 12 months"
NOT_STARTED = "You can record the outcome once the meeting has started"
UNIVERSITY_MISSING = "Choose a university"
CONTACT_INVALID = "Choose contacts of this university"
EMPLOYEE_INVALID = "Choose active partnership managers or heads"
EMPLOYEE_IS_RESPONSIBLE = "The responsible employee is already in the meeting; add other employees only"
RESPONSIBLE_INVALID = "Choose yourself or an active partnership manager from your team"
OUTCOME_EMPTY = "Record what happened: notes, discussion points or decisions"
NEXT_ACTION_MISSING = "Describe the next action"
NEXT_DUE_MISSING = "Choose when the next action is due"
LINK_MISSING = "link_missing"  # MG4 warning key

M = UniversityMeeting
P = UniversityMeetingParticipant
IS_SCHEDULED = M.status == "scheduled"
Responsible = aliased(User)


# --- access ---------------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES:
        raise HTTPException(403, "University meetings access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def require_creator(db: AsyncSession, user: User) -> None:
    await require_reader(db, user)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Only partnership managers and heads schedule meetings")


def is_actor(user: User, m: M) -> bool:
    return user.id in (m.responsible_user_id, m.created_by_user_id)


async def university_for(db: AsyncSession, user: User, university_id: UUID) -> University:
    """MG15: the university, locked (it may move stage), in the caller's edit scope (403) and active (409) -- upc-010 VS6's rule."""
    try:
        uni = await unis.load(db, university_id, lock=True)
    except HTTPException:
        raise field_error("university_id", UNIVERSITY_MISSING, str(university_id)) from None
    unis.require(user, uni, await unis.team_of(db, user), "can_edit_contacts", "meeting_create")
    return uni


async def university_of(db: AsyncSession, user: User, meeting_id: UUID) -> University:
    """Complete's first lock: the meeting's university (it may move stage), so the order is always university -> meeting."""
    await require_reader(db, user)
    university_id = await db.scalar(select(M.university_id).where(M.id == meeting_id))
    if university_id is None:
        raise HTTPException(404, NOT_FOUND)
    return await unis.load(db, university_id, lock=True)


async def load_for_write(db: AsyncSession, user: User, meeting_id: UUID, action: str) -> M:
    """Lock the meeting (404), then the actor (403, logged ids only), then the state (409)."""
    await require_reader(db, user)
    m = await db.scalar(select(M).where(M.id == meeting_id).with_for_update().execution_options(populate_existing=True))
    if m is None:
        raise HTTPException(404, NOT_FOUND)
    if not is_actor(user, m):
        log("university_meeting_refused", user, m.id, action=action)
        raise HTTPException(403, ACTOR_REFUSAL)
    if m.status != "scheduled":
        raise HTTPException(409, STATE_REFUSALS[m.status])
    return m


# --- people (MG5-MG8) -----------------------------------------------------------------------------------------------------------
async def check_responsible(db: AsyncSession, user: User, responsible_id: UUID) -> None:
    """MG8: a manager is responsible for their own meetings; a head picks themselves or an active direct report (upc-010 lead rule)."""
    if not await db.scalar(select(User.id).where(User.id == responsible_id, *visits.lead_filter(user))):
        raise field_error("responsible_user_id", RESPONSIBLE_INVALID, str(responsible_id))


async def contact_of(db: AsyncSession, university_id: UUID, contact_id: UUID) -> UniversityContact:
    contact = await db.scalar(select(UniversityContact).where(UniversityContact.id == contact_id, UniversityContact.university_id == university_id))
    if contact is None:
        raise field_error("contact_id", CONTACT_INVALID, str(contact_id))  # N1
    return contact


async def check_contacts(db: AsyncSession, university_id: UUID, added: set[UUID]) -> None:
    if added:
        found = await db.scalar(select(func.count()).select_from(UniversityContact).where(UniversityContact.id.in_(added), UniversityContact.university_id == university_id))
        if found != len(added):
            raise field_error("participant_contact_ids", CONTACT_INVALID)  # N1


async def check_employees(db: AsyncSession, users: set[UUID], responsible_id: UUID, kept: set[UUID]) -> None:
    """MG7: each employee newly added is an active partnership manager or head; a kept one stays even when since deactivated."""
    if responsible_id in users:
        raise field_error("participant_user_ids", EMPLOYEE_IS_RESPONSIBLE)
    added = users - kept
    if added:
        found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(added), User.active.is_(True), User.role.in_(visits.STAFF_ROLES)))
        if found != len(added):
            raise field_error("participant_user_ids", EMPLOYEE_INVALID)


def set_contact(m: M, contact: UniversityContact | None) -> None:
    """MG5: the contact person's name and designation are copied, so the meeting keeps them."""
    m.contact_id = contact.id if contact else None
    m.contact_name = contact.name if contact else None
    m.contact_designation = contact.designation if contact else None


async def stored_people(db: AsyncSession, meeting_id: UUID) -> tuple[set[UUID], set[UUID]]:
    rows = (await db.execute(select(P.contact_id, P.user_id).where(P.meeting_id == meeting_id))).all()
    return {c for c, _ in rows if c is not None}, {u for _, u in rows if u is not None}


async def set_people(db: AsyncSession, meeting_id: UUID, contacts: set[UUID], users: set[UUID], stored: tuple[set[UUID], set[UUID]]) -> None:
    """Replace the sets: remove what left, add what arrived (no delete-then-insert of a kept row)."""
    stored_contacts, stored_users = stored
    if stored_contacts - contacts or stored_users - users:
        gone = or_(P.contact_id.in_(stored_contacts - contacts), P.user_id.in_(stored_users - users))
        await db.execute(delete(P).where(P.meeting_id == meeting_id, gone))
    db.add_all([P(meeting_id=meeting_id, contact_id=c) for c in contacts - stored_contacts])
    db.add_all([P(meeting_id=meeting_id, user_id=u) for u in users - stored_users])


# --- writes -----------------------------------------------------------------------------------------------------------------------
async def _advance(db: AsyncSession, user: User, uni: University, m: M, to_stage: str, verb: str) -> bool:
    """MG13 / AC3: forward-only, through the upc-007 engine, with the new stage's upc-020 rule and the university's audit row."""
    if uni.lost_at is not None or not uni.active:
        return False
    from_stage = pipeline.advance_to(db, user, uni, to_stage, f"Automatic: meeting {m.code} {verb}")
    if from_stage is None:
        return False
    await tasks.on_stage_entered(db, user, uni)
    unis.audit(db, user, "stage_changed", uni.id, {"from": from_stage, "to": to_stage, "backward": False, "note": True, "source": "meeting"})
    return True


async def create(db: AsyncSession, user: User, uni: University, payload: UniversityMeetingIn, now: datetime) -> M:
    """The route locked the university and checked its scope. MG3 time; MG5-MG8 people; MG13 the stage (AC3)."""
    check_time("starts_at", payload.starts_at, now, START_PAST, START_FAR)
    responsible_id = payload.responsible_user_id or user.id
    await check_responsible(db, user, responsible_id)
    contact = await contact_of(db, uni.id, payload.contact_id) if payload.contact_id else None
    contacts, users = set(payload.participant_contact_ids), set(payload.participant_user_ids)
    await check_contacts(db, uni.id, contacts - ({contact.id} if contact else set()))
    await check_employees(db, users, responsible_id, set())
    if contact:
        contacts.add(contact.id)
    values = payload.model_dump(include={"meeting_type", "starts_at", "mode", "location", "meeting_url", "agenda", "notes"})
    code = f"UMT-{await db.scalar(select(UNIVERSITY_MEETING_CODE_SEQ.next_value())):06d}"
    m = M(code=code, university_id=uni.id, responsible_user_id=responsible_id, created_by_user_id=user.id, status="scheduled", **values)
    set_contact(m, contact)
    db.add(m)
    await db.flush()
    await set_people(db, m.id, contacts, users, (set(), set()))
    event(db, m, user, "scheduled", new=m.starts_at)
    moved = await _advance(db, user, uni, m, "meeting_scheduled", "scheduled")
    audit(db, user, "create", m.id, {"code": m.code, "university_id": str(uni.id), "meeting_type": m.meeting_type, "mode": m.mode,
                                     "contacts": len(contacts), "employees": len(users), "stage_moved": moved})  # fmt: skip
    return m


async def update(db: AsyncSession, user: User, m: M, payload: UniversityMeetingUpdate, now: datetime) -> list[str]:
    """MG9: only changed values count (no event or audit for none); a changed start is a reschedule recorded with the old and new time.
    Returns the changed field names."""
    changes = payload.model_dump(exclude_unset=True, exclude={"participant_contact_ids", "participant_user_ids", "reschedule_reason"})
    changed = sorted(key for key, value in changes.items() if getattr(m, key) != value)
    if "starts_at" in changed:
        check_time("starts_at", changes["starts_at"], now, START_PAST, START_FAR)
    if "responsible_user_id" in changed:
        await check_responsible(db, user, changes["responsible_user_id"])
    contact_id = changes.get("contact_id", m.contact_id)
    contact = await contact_of(db, m.university_id, contact_id) if "contact_id" in changed and contact_id else None
    stored = await stored_people(db, m.id)
    # Unsent lists stay as stored (a replaced contact person stays a participant until the list is sent without it).
    contacts = set(payload.participant_contact_ids) if payload.participant_contact_ids is not None else set(stored[0])
    users = set(payload.participant_user_ids) if payload.participant_user_ids is not None else set(stored[1])
    await check_contacts(db, m.university_id, contacts - stored[0] - {contact_id})
    await check_employees(db, users, changes.get("responsible_user_id", m.responsible_user_id), stored[1])
    if contact_id is not None:
        contacts.add(contact_id)
    changed += [key for key, now_set, before in (("participant_contact_ids", contacts, stored[0]), ("participant_user_ids", users, stored[1])) if now_set != before]
    old_start = m.starts_at
    for key in changed:
        if key == "contact_id":
            set_contact(m, contact)
        elif key in changes:
            setattr(m, key, changes[key])
    await set_people(db, m.id, contacts, users, stored)
    if "starts_at" in changed:
        event(db, m, user, "rescheduled", old=old_start, new=m.starts_at, reason=payload.reschedule_reason)
    if set(changed) - {"starts_at"}:
        event(db, m, user, "edited")
    if changed:
        audit(db, user, "update", m.id, {"code": m.code, "fields": changed})
    return changed


def _check_future(field: str, value: date | None) -> None:
    if value is not None and value < india_today():
        raise field_error(field, "Choose today or a later date", value.isoformat())


async def complete(db: AsyncSession, user: User, m: M, uni: University, payload: UniversityMeetingComplete, now: datetime) -> None:
    """MG10-MG13: after the start only; something recorded; a next action with its due date; the follow-ups and the stage advance in
    this transaction (AC2, AC3)."""
    if m.starts_at > now:
        raise HTTPException(422, NOT_STARTED)
    if not (payload.notes or payload.discussion_points or payload.decisions):
        raise HTTPException(422, OUTCOME_EMPTY)
    if payload.next_action and payload.next_action_due_on is None:
        raise field_error("next_action_due_on", NEXT_DUE_MISSING)
    if payload.next_action_due_on is not None and not payload.next_action:
        raise field_error("next_action", NEXT_ACTION_MISSING)
    _check_future("next_action_due_on", payload.next_action_due_on)
    _check_future("next_meeting_date", payload.next_meeting_date)
    if payload.notes:
        m.notes = payload.notes
    m.discussion_points, m.decisions = payload.discussion_points, payload.decisions
    m.next_action, m.next_action_due_on, m.next_meeting_date = payload.next_action, payload.next_action_due_on, payload.next_meeting_date
    m.status, m.completed_at, m.completed_by_user_id = "completed", now, user.id
    event(db, m, user, "completed")
    await db.flush()
    await tasks.on_meeting_completed(db, user, m, uni)
    moved = await _advance(db, user, uni, m, "meeting_completed", "completed")
    audit(db, user, "complete", m.id, {"code": m.code, "with_next_action": bool(m.next_action), "with_next_meeting": m.next_meeting_date is not None, "stage_moved": moved})


def cancel(db: AsyncSession, user: User, m: M, reason: str, now: datetime) -> None:
    m.status, m.cancelled_at, m.cancel_reason = "cancelled", now, reason
    event(db, m, user, "cancelled", reason=reason)
    audit(db, user, "cancel", m.id, {"code": m.code})


# --- output ---------------------------------------------------------------------------------------------------------------------
def _rows():
    """One query for a page: meeting + university + country + responsible employee (no N+1)."""
    return (
        select(M, University, Country, Responsible)
        .join(University, University.id == M.university_id)
        .join(Country, Country.id == University.country_id)
        .join(Responsible, Responsible.id == M.responsible_user_id)
    )


def _university(uni: University, country: Country) -> dict:
    return {"id": uni.id, "name": uni.name, "university_code": uni.university_code, "city": uni.city, "country": {"id": country.id, "name": country.name}}


def warnings(m: M) -> list[str]:
    """MG4 / E1: an online meeting may be saved without its link; say so while it is scheduled."""
    return [LINK_MISSING] if m.status == "scheduled" and m.mode == "online" and not m.meeting_url else []


def row_out(m: M, uni: University, country: Country, responsible: User) -> dict:
    contact = None if m.contact_id is None and m.contact_name is None else {"id": m.contact_id, "name": m.contact_name, "designation": m.contact_designation}
    return {
        "id": m.id, "code": m.code, "meeting_type": m.meeting_type, "starts_at": m.starts_at, "mode": m.mode, "status": m.status,
        "university": _university(uni, country), "responsible": person_ref(responsible), "contact": contact, "warnings": warnings(m),
    }  # fmt: skip


def views(now: datetime) -> dict:
    """MG16: each view's condition and order (rec-028 MT10)."""
    return {
        "upcoming": (IS_SCHEDULED & (M.starts_at > now), (M.starts_at, M.id)),
        "awaiting_outcome": (IS_SCHEDULED & (M.starts_at <= now), (M.starts_at, M.id)),
        "completed": (M.status == "completed", (M.starts_at.desc(), M.id)),
        "cancelled": (M.status == "cancelled", (M.starts_at.desc(), M.id)),
    }


def list_filters(user: User, university_id: UUID | None, mine: bool) -> list:
    filters = []
    if university_id is not None:
        filters.append(M.university_id == university_id)
    if mine:
        joined = exists().where(P.meeting_id == M.id, P.user_id == user.id)
        filters.append(or_(M.responsible_user_id == user.id, M.created_by_user_id == user.id, joined))
    return filters


async def page(db: AsyncSession, filters: list, view: str | None, now: datetime, limit: int, offset: int) -> dict:
    """The counts use every filter but the view, so the tabs add up; no view = every meeting, scheduled ones first by start."""
    conditions = views(now)
    if view is None:
        where, order = [], (case((IS_SCHEDULED, 0), else_=1), case((IS_SCHEDULED, M.starts_at)).asc(), M.starts_at.desc(), M.id)
    else:
        condition, order = conditions[view]
        where = [condition]
    total = await db.scalar(select(func.count()).select_from(M).where(*filters, *where))
    rows = (await db.execute(_rows().where(*filters, *where).order_by(*order).limit(limit).offset(offset))).all()
    counts = (await db.execute(select(*(func.count().filter(c) for c, _ in conditions.values())).select_from(M).where(*filters))).one()
    return {
        "items": [row_out(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset,
        "counts": {v: n or 0 for v, n in zip(conditions, counts, strict=True)},
    }  # fmt: skip


async def detail_out(db: AsyncSession, user: User, meeting_id: UUID, now: datetime) -> dict:
    """What every route returns, read as written (populate_existing: never a stale identity-map copy after a commit)."""
    row = (await db.execute(_rows().where(M.id == meeting_id).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    m, uni, country, responsible = row
    creator = await db.get_one(User, m.created_by_user_id)
    completer = await db.get(User, m.completed_by_user_id) if m.completed_by_user_id else None
    contacts = (await db.scalars(
        select(UniversityContact).join(P, P.contact_id == UniversityContact.id).where(P.meeting_id == m.id).order_by(func.lower(UniversityContact.name), UniversityContact.id)
    )).all()  # fmt: skip
    employees = (await db.scalars(select(User).join(P, P.user_id == User.id).where(P.meeting_id == m.id).order_by(User.full_name, User.id))).all()
    events = (await db.execute(
        select(UniversityMeetingEvent, User).join(User, User.id == UniversityMeetingEvent.actor_user_id)
        .where(UniversityMeetingEvent.meeting_id == m.id).order_by(UniversityMeetingEvent.position)
    )).all()  # fmt: skip
    follow_ups = (await db.execute(
        select(PartnershipTask, User).join(User, User.id == PartnershipTask.assignee_user_id)
        .where(PartnershipTask.rule.in_((f"meeting:{m.id}", f"meeting:{m.id}:next"))).order_by(PartnershipTask.due_on, PartnershipTask.id)
    )).all()  # fmt: skip
    can_change = m.status == "scheduled" and is_actor(user, m)
    return {
        **row_out(m, uni, country, responsible),
        **{k: getattr(m, k) for k in ("location", "meeting_url", "agenda", "notes", "discussion_points", "decisions", "next_action", "next_action_due_on",
                                      "next_meeting_date", "completed_at", "cancelled_at", "cancel_reason", "created_at", "updated_at")},
        "created_by": person_ref(creator),
        "completed_by": person_ref(completer) if completer else None,
        "participants": {"contacts": [{"id": c.id, "name": c.name, "designation": c.designation} for c in contacts], "employees": [person_ref(u) for u in employees]},
        "events": [{"event": e.event, "old_starts_at": e.old_starts_at, "new_starts_at": e.new_starts_at, "reason": e.reason, "actor": person_ref(a), "created_at": e.created_at} for e, a in events],
        "follow_ups": [{"id": t.id, "title": t.title, "due_on": t.due_on, "status": t.status, "assignee": person_ref(a)} for t, a in follow_ups],
        "permissions": {"can_edit": can_change, "can_complete": can_change and m.starts_at <= now, "can_cancel": can_change},
    }  # fmt: skip


def event(db: AsyncSession, m: M, user: User, name: str, *, old: datetime | None = None, new: datetime | None = None, reason: str | None = None) -> None:
    db.add(UniversityMeetingEvent(meeting_id=m.id, event=name, old_starts_at=old, new_starts_at=new, reason=reason, actor_user_id=user.id))


def audit(db: AsyncSession, user: User, action: str, meeting_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, codes, keys, counts and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"university_meeting.{action}", entity_type="university_meeting", entity_id=str(meeting_id), metadata_json=metadata or {}))


def log(event_name: str, user: User, meeting_id, **extra) -> None:
    logger.info(event_name, extra={"extra_fields": {"actor_id": str(user.id), "meeting_id": str(meeting_id), **extra}})
