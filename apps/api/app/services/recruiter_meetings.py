"""rec-028 (DEC-SCOPE-132, spec §1-§3): recruiter meetings with a company -- rules, the four lists, history and the output.

A meeting belongs to its company (rec-024's FU4 rule): every read and write goes through rec-003's company scope (`caller_scope` /
`load_scoped`), so another recruiter's meeting is the same 404 as a missing one. Writes need the company's `can_edit` (MT9) and lock the
company, then the meeting. Scheduling fires rec-005's `meeting_scheduled` event (MT8, AC1); an outcome's next action is a rec-024
follow-up (MT7, AC2). Functions only; nothing here commits. Logs and audit carry ids, keys and field names -- never purpose, outcome or
reasons."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    RECRUITER_MEETING_CODE_SEQ,
    AuditLog,
    Company,
    CompanyContact,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterMeetingEvent,
    RecruiterMeetingParticipant,
    User,
)
from app.schemas import RecFollowUpCreate, RecMeetingCreate, RecMeetingOutcome, RecMeetingUpdate
from app.services import company_pipeline
from app.services import recruiter_companies as companies
from app.services import recruiter_follow_ups as follow_ups
from app.services.lead_follow_ups import DUE_FAR, DUE_PAST, HORIZON
from app.services.recruiter import MANAGER_ROLE, ROLE

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Meeting not found"
STATE_REFUSALS = {"completed": "This meeting's outcome is already recorded", "cancelled": "This meeting was cancelled"}
START_PAST = "Choose a meeting time in the future"
START_FAR = "Choose a meeting time within the next 12 months"
NOT_STARTED = "You can record the outcome once the meeting has started"
CONTACT_INVALID = "Choose an active contact of this company"
RECRUITER_INVALID = "Choose active recruiters only"
NEXT_ACTION_MISSING = "Describe the next action"
NEXT_DUE_MISSING = "Choose when the next action is due"
NEXT_REASON_MISSING = "Choose a follow-up reason"
PEOPLE_ROLES = (ROLE, MANAGER_ROLE)

M = RecruiterMeeting
P = RecruiterMeetingParticipant
IS_SCHEDULED = M.status == "scheduled"
Recruiter, Creator, Completer = aliased(User), aliased(User), aliased(User)


def field_error(field: str, msg: str, value=None) -> RequestValidationError:
    """The validation-error shape, so the form can place a service rule on its field."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_time(field: str, when: datetime, now: datetime, past: str, far: str) -> None:
    """MT3 / MT7: in the future and within 366 days (tel-011's horizon)."""
    if when <= now or when > now + HORIZON:
        raise field_error(field, past if when <= now else far, when.isoformat())


def _rows():
    """One query: the meeting, its company and recruiter, the primary contact, the creator, the completer and the follow-up -- no N+1."""
    return (
        select(M, Company, Recruiter, CompanyContact, Creator, Completer, RecruiterFollowUp)
        .join(Company, Company.id == M.company_id)
        .outerjoin(Recruiter, Recruiter.id == Company.assigned_recruiter_user_id)
        .outerjoin(CompanyContact, CompanyContact.id == M.contact_id)
        .join(Creator, Creator.id == M.created_by_user_id)
        .outerjoin(Completer, Completer.id == M.completed_by_user_id)
        .outerjoin(RecruiterFollowUp, RecruiterFollowUp.id == M.follow_up_id)
    )


async def _extras(db: AsyncSession, ids: list[UUID]) -> tuple[dict, dict]:
    """Participants and history for a page of meetings -- two queries, whatever the page size."""
    people: dict[UUID, dict] = {i: {"contacts": [], "recruiters": []} for i in ids}
    history: dict[UUID, list] = {i: [] for i in ids}
    if not ids:
        return people, history
    rows = await db.execute(
        select(P.meeting_id, CompanyContact.id, CompanyContact.name, User.id, User.full_name)
        .outerjoin(CompanyContact, CompanyContact.id == P.contact_id)
        .outerjoin(User, User.id == P.user_id)
        .where(P.meeting_id.in_(ids))
        .order_by(func.lower(func.coalesce(CompanyContact.name, User.full_name)), P.id)
    )
    for meeting_id, contact_id, contact_name, user_id, full_name in rows:
        if contact_id is not None:
            people[meeting_id]["contacts"].append({"id": contact_id, "name": contact_name})
        else:
            people[meeting_id]["recruiters"].append({"id": user_id, "full_name": full_name})
    events = await db.execute(
        select(RecruiterMeetingEvent, User).join(User, User.id == RecruiterMeetingEvent.actor_user_id)
        .where(RecruiterMeetingEvent.meeting_id.in_(ids)).order_by(RecruiterMeetingEvent.position)
    )
    for event, actor in events:
        history[event.meeting_id].append({
            "event": event.event, "old_starts_at": event.old_starts_at, "new_starts_at": event.new_starts_at, "reason": event.reason,
            "actor": companies.person(actor), "created_at": event.created_at,
        })
    return people, history


def _out(user: User, now: datetime, people: dict, history: dict, m: M, company: Company, recruiter, contact, creator, completer, fu) -> dict:
    can_change = m.status == "scheduled" and companies.permissions(user, company)["can_edit"]
    return {
        "id": m.id, "code": m.meeting_code, "meeting_type": m.meeting_type, "starts_at": m.starts_at, "mode": m.mode, "location": m.location,
        "meeting_url": m.meeting_url, "purpose": m.purpose, "status": m.status, "outcome": m.outcome, "next_action": m.next_action,
        "company": {"id": company.id, "code": company.company_code, "name": company.name, "assigned_recruiter": companies.person(recruiter)},
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "participants": people[m.id], "history": history[m.id],
        "follow_up": None if fu is None else {"id": fu.id, "due_at": fu.due_at},
        "created_by": companies.person(creator), "created_at": m.created_at, "completed_at": m.completed_at,
        "completed_by": companies.person(completer), "cancelled_at": m.cancelled_at, "cancel_reason": m.cancel_reason,
        "can_change": can_change, "can_record_outcome": can_change and m.starts_at <= now,
    }


async def _items(db: AsyncSession, user: User, now: datetime, rows) -> list[dict]:
    people, history = await _extras(db, [row[0].id for row in rows])
    return [_out(user, now, people, history, *row) for row in rows]


async def _page(db: AsyncSession, user: User, now: datetime, where: list, order: tuple, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(M).join(Company, Company.id == M.company_id).where(*where))
    rows = (await db.execute(_rows().where(*where).order_by(*order).limit(limit).offset(offset))).all()
    return {"items": await _items(db, user, now, rows), "total": total or 0, "limit": limit, "offset": offset}


def views(now: datetime) -> dict:
    """MT10: the condition and the order of each view."""
    return {
        "upcoming": (IS_SCHEDULED & (M.starts_at > now), (M.starts_at, M.id)),
        "awaiting_outcome": (IS_SCHEDULED & (M.starts_at <= now), (M.starts_at, M.id)),
        "completed": (M.status == "completed", (M.starts_at.desc(), M.id)),
        "cancelled": (M.status == "cancelled", (M.starts_at.desc(), M.id)),
    }


async def list_page(db: AsyncSession, user: User, view: str, now: datetime, limit: int, offset: int) -> dict:
    """The caller's meetings in one view; the counts are the four views' totals, so the tabs agree with the lists."""
    scope = await companies.caller_scope(db, user)
    conditions = views(now)
    where, order = conditions[view]
    out = await _page(db, user, now, [*scope, where], order, limit, offset)
    counts = (await db.execute(
        select(*(func.count().filter(c) for c, _ in conditions.values())).select_from(M).join(Company, Company.id == M.company_id).where(*scope)
    )).one()
    return {**out, "counts": {v: n or 0 for v, n in zip(conditions, counts, strict=True)}}


async def company_page(db: AsyncSession, user: User, company_id: UUID, now: datetime, limit: int, offset: int) -> dict:
    """A company's meetings: scheduled ones by start, then completed / cancelled newest first."""
    order = (case((IS_SCHEDULED, 0), else_=1), case((IS_SCHEDULED, M.starts_at)).asc(), M.starts_at.desc(), M.id)
    return await _page(db, user, now, [M.company_id == company_id], order, limit, offset)


async def one(db: AsyncSession, user: User, meeting_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows().where(M.id == meeting_id).execution_options(populate_existing=True))).one()
    return (await _items(db, user, now, [row]))[0]


async def check_readable(db: AsyncSession, user: User, meeting_id: UUID) -> None:
    """A read: in the caller's company scope, else 404 (other roles 403 from the scope)."""
    company_id = await db.scalar(select(M.company_id).where(M.id == meeting_id))
    if company_id is None:
        raise HTTPException(404, NOT_FOUND)
    await _company(db, user, company_id, lock=False)


async def _company(db: AsyncSession, user: User, company_id: UUID, *, lock: bool) -> Company:
    try:
        return await companies.load_scoped(db, user, company_id, lock=lock)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, NOT_FOUND) from None
        raise


# --- participants (MT5) -------------------------------------------------------------------------------------------------------
async def _stored_people(db: AsyncSession, meeting_id: UUID) -> tuple[set[UUID], set[UUID]]:
    rows = (await db.execute(select(P.contact_id, P.user_id).where(P.meeting_id == meeting_id))).all()
    return {c for c, _ in rows if c is not None}, {u for _, u in rows if u is not None}


async def check_people(db: AsyncSession, company_id: UUID, contact_id: UUID | None, contacts: set[UUID], users: set[UUID],
                       kept_contacts: frozenset = frozenset(), kept_users: frozenset = frozenset()) -> None:
    """Each contact newly set or added must be an active contact of this company; each recruiter newly added an active placement user.
    Kept ones stay even when since deactivated."""
    if contact_id is not None and contact_id not in kept_contacts:
        if await db.scalar(select(CompanyContact.id).where(CompanyContact.id == contact_id, CompanyContact.company_id == company_id, CompanyContact.active)) is None:
            raise field_error("contact_id", CONTACT_INVALID, str(contact_id))
    added = contacts - kept_contacts - {contact_id}
    if added:
        found = await db.scalar(select(func.count()).select_from(CompanyContact).where(
            CompanyContact.id.in_(added), CompanyContact.company_id == company_id, CompanyContact.active))
        if found != len(added):
            raise field_error("participant_contact_ids", CONTACT_INVALID)
    added_users = users - kept_users
    if added_users:
        found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(added_users), User.role.in_(PEOPLE_ROLES), User.active))
        if found != len(added_users):
            raise field_error("participant_user_ids", RECRUITER_INVALID)


async def _set_people(db: AsyncSession, meeting_id: UUID, contacts: set[UUID], users: set[UUID], stored: tuple[set, set]) -> None:
    """Replace the set: remove what left, add what arrived (no delete-then-insert of a kept row)."""
    stored_contacts, stored_users = stored
    if stored_contacts - contacts or stored_users - users:
        gone = or_(P.contact_id.in_(stored_contacts - contacts), P.user_id.in_(stored_users - users))
        await db.execute(delete(P).where(P.meeting_id == meeting_id, gone))
    db.add_all([P(meeting_id=meeting_id, contact_id=c) for c in contacts - stored_contacts])
    db.add_all([P(meeting_id=meeting_id, user_id=u) for u in users - stored_users])


def _event(db: AsyncSession, meeting_id: UUID, user: User, event: str, *, old=None, new=None, reason=None) -> None:
    db.add(RecruiterMeetingEvent(meeting_id=meeting_id, event=event, old_starts_at=old, new_starts_at=new, reason=reason, actor_user_id=user.id))


# --- writes -----------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, company: Company, payload: RecMeetingCreate, now: datetime) -> M:
    """The caller locked the company and checked `can_edit`. MT3 time; MT5 people; MT8 the pipeline move (AC1)."""
    check_time("starts_at", payload.starts_at, now, START_PAST, START_FAR)
    values = payload.model_dump(exclude={"participant_contact_ids", "participant_user_ids"})
    contacts, users = set(payload.participant_contact_ids), set(payload.participant_user_ids)
    await check_people(db, company.id, payload.contact_id, contacts, users)
    if payload.contact_id is not None:
        contacts.add(payload.contact_id)
    code = f"MTG-{await db.scalar(select(RECRUITER_MEETING_CODE_SEQ.next_value())):06d}"
    meeting = M(meeting_code=code, company_id=company.id, created_by_user_id=user.id, **values)
    db.add(meeting)
    await db.flush()
    await _set_people(db, meeting.id, contacts, users, (set(), set()))
    _event(db, meeting.id, user, "scheduled", new=meeting.starts_at)
    moved = await company_pipeline.apply_event(db, company, "meeting_scheduled", user)
    audit(db, user, "create", meeting.id, {"company_id": str(company.id), "meeting_type": meeting.meeting_type, "mode": meeting.mode,
                                           "contacts": len(contacts), "recruiters": len(users), "stage_moved": moved})
    return meeting


async def load_for_write(db: AsyncSession, user: User, meeting_id: UUID, route: str) -> tuple[Company, M]:
    """In scope (404) -> company lock -> `can_edit` (403, then 409 when archived) -> meeting lock -> scheduled (409)."""
    company_id = await db.scalar(select(M.company_id).where(M.id == meeting_id))
    if company_id is None:
        raise HTTPException(404, NOT_FOUND)
    company = await _company(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", route)
    meeting = await db.scalar(select(M).where(M.id == meeting_id).with_for_update().execution_options(populate_existing=True))
    if meeting is None:  # never in practice (meetings are not deleted); narrows the type without an assert
        raise HTTPException(404, NOT_FOUND)
    if meeting.status != "scheduled":
        raise HTTPException(409, STATE_REFUSALS[meeting.status])
    return company, meeting


async def update(db: AsyncSession, user: User, company: Company, meeting: M, payload: RecMeetingUpdate, now: datetime) -> list[str]:
    """MT6: only changed values count (no audit for none); a changed start is a reschedule, must be in the future, and is recorded with
    the old and new time. Returns the changed field names."""
    changes = payload.model_dump(exclude_unset=True, exclude={"participant_contact_ids", "participant_user_ids", "reschedule_reason"})
    changed = sorted(key for key, value in changes.items() if getattr(meeting, key) != value)
    if "starts_at" in changed:
        check_time("starts_at", changes["starts_at"], now, START_PAST, START_FAR)
    stored = await _stored_people(db, meeting.id)
    contact_id = changes.get("contact_id", meeting.contact_id)
    # Unsent lists stay as stored (a replaced primary contact stays a participant until the list is sent without it).
    contacts = set(payload.participant_contact_ids) if payload.participant_contact_ids is not None else set(stored[0])
    users = set(payload.participant_user_ids) if payload.participant_user_ids is not None else set(stored[1])
    await check_people(db, company.id, contact_id, contacts, users, frozenset(stored[0]), frozenset(stored[1]))
    if contact_id is not None:
        contacts.add(contact_id)
    if contacts != stored[0]:
        changed.append("participant_contact_ids")
    if users != stored[1]:
        changed.append("participant_user_ids")
    old_start = meeting.starts_at
    for key in changes:
        if key in changed:
            setattr(meeting, key, changes[key])
    await _set_people(db, meeting.id, contacts, users, stored)
    if "starts_at" in changed:
        _event(db, meeting.id, user, "rescheduled", old=old_start, new=meeting.starts_at, reason=payload.reschedule_reason)
    if changed:
        audit(db, user, "update", meeting.id, {"fields": changed})
    return changed


async def record_outcome(db: AsyncSession, user: User, company: Company, meeting: M, payload: RecMeetingOutcome, now: datetime) -> None:
    """MT7 / AC2: after the start only; a next action needs a due time and a reason and becomes a rec-024 follow-up in this transaction
    (its rules -- future time, the open cap -- refuse the whole outcome)."""
    if meeting.starts_at > now:
        raise HTTPException(422, NOT_STARTED)
    follow_up = None
    if payload.next_action is None:
        if payload.next_action_due_at is not None or payload.next_action_reason is not None:
            raise field_error("next_action", NEXT_ACTION_MISSING)
    else:
        missing = [(f, msg) for f, msg, value in (("next_action_due_at", NEXT_DUE_MISSING, payload.next_action_due_at),
                                                 ("next_action_reason", NEXT_REASON_MISSING, payload.next_action_reason)) if value is None]
        if missing:
            raise RequestValidationError([{"type": "value_error", "loc": ("body", f), "msg": msg, "input": None} for f, msg in missing])
        check_time("next_action_due_at", payload.next_action_due_at, now, DUE_PAST, DUE_FAR)
        active_contact = meeting.contact_id and await db.scalar(select(CompanyContact.active).where(CompanyContact.id == meeting.contact_id))
        follow_up = await follow_ups.create(db, user, company, RecFollowUpCreate(
            due_at=payload.next_action_due_at, reason=payload.next_action_reason, contact_id=meeting.contact_id if active_contact else None,
            notes=payload.next_action,
        ), now)
    meeting.status, meeting.outcome, meeting.next_action = "completed", payload.outcome, payload.next_action
    meeting.completed_at, meeting.completed_by_user_id, meeting.follow_up_id = now, user.id, follow_up.id if follow_up else None
    _event(db, meeting.id, user, "completed")
    audit(db, user, "complete", meeting.id, {"with_next_action": follow_up is not None, "follow_up_id": str(follow_up.id) if follow_up else None})


def cancel(db: AsyncSession, user: User, meeting: M, reason: str, now: datetime) -> None:
    meeting.status, meeting.cancelled_at, meeting.cancel_reason = "cancelled", now, reason
    _event(db, meeting.id, user, "cancelled", reason=reason)
    audit(db, user, "cancel", meeting.id)


async def recruiter_options(db: AsyncSession, filters: list, limit: int) -> dict:
    """The participant picker (MT5): active placement users, names only."""
    where = [User.role.in_(PEOPLE_ROLES), User.active.is_(True), *filters]
    total = await db.scalar(select(func.count()).select_from(User).where(*where))
    rows = (await db.scalars(select(User).where(*where).order_by(func.lower(User.full_name), User.id).limit(limit))).all()
    return {"items": [{"id": u.id, "full_name": u.full_name} for u in rows], "total": total or 0}


def audit(db: AsyncSession, user: User, action: str, meeting_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_meeting.{action}", entity_type="recruiter_meeting", entity_id=str(meeting_id), metadata_json=metadata or {}))


def log(event: str, user: User, meeting_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "meeting_id": str(meeting_id), **extra}})
