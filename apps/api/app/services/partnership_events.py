"""upc-011 (DEC-SCOPE-152, spec CL2-CL7, CL14): partnership events -- who reads, adds and acts, the dates, owner and employees, and output.

Functions only; nothing here commits -- the route owns the transaction. Every partnership reader reads every event; only the owner or the
creator changes one, while it is scheduled. Audit rows carry ids, code, kind, counts and field names only -- never title, notes or reasons.
"""

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PARTNERSHIP_EVENT_CODE_SEQ, AuditLog, PartnershipEvent, PartnershipEventParticipant, University, User
from app.partnership_event_kinds import MAX_SPAN_DAYS
from app.schemas import PartnershipEventIn, PartnershipEventUpdate
from app.services import partnership_calendar as calendar
from app.services import university_visits as visits
from app.services.bdm_travel import india_today
from app.services.recruiter_meetings import field_error
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Event not found"
CREATE_ROLES = frozenset({"partnership_manager", "partnership_head"})
ACTOR_REFUSAL = "Only the event's owner or the person who added it can change it"
CANCELLED = "This event was cancelled"
UNIVERSITY_INVALID = "Choose an active university"
OWNER_INVALID = "Choose yourself or an active partnership manager from your team"
EMPLOYEE_INVALID = "Choose active partnership managers or heads"
EMPLOYEE_IS_OWNER = "The owner is already at the event; add other employees only"
PAST = "Choose today or a later date"
ENDS_BEFORE = "The end date can't be before the start date"
TOO_LONG = f"An event can last at most {MAX_SPAN_DAYS} days"
EP = PartnershipEventParticipant


# --- access -------------------------------------------------------------------------------------------------------------------------
async def require_creator(db: AsyncSession, user: User) -> None:
    await calendar.require_reader(db, user)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Only partnership managers and heads add events")


def is_actor(user: User, e: PartnershipEvent) -> bool:
    return user.id in (e.owner_user_id, e.created_by_user_id)


async def load_for_write(db: AsyncSession, user: User, event_id: UUID, action: str) -> PartnershipEvent:
    """Lock the event (404), then the actor (403, logged ids only), then the state (409)."""
    await calendar.require_reader(db, user)
    e = await db.scalar(select(PartnershipEvent).where(PartnershipEvent.id == event_id).with_for_update().execution_options(populate_existing=True))
    if e is None:
        raise HTTPException(404, NOT_FOUND)
    if not is_actor(user, e):
        log("partnership_event_refused", user, e.id, action=action)
        raise HTTPException(403, ACTOR_REFUSAL)
    if e.status != "scheduled":
        raise HTTPException(409, CANCELLED)
    return e


# --- rules (CL2-CL5) ------------------------------------------------------------------------------------------------------------------
async def check_university(db: AsyncSession, university_id: UUID | None) -> None:
    if university_id is not None and not await db.scalar(select(University.id).where(University.id == university_id, University.active.is_(True))):
        raise field_error("university_id", UNIVERSITY_INVALID, str(university_id))


def check_dates(starts_on: date, ends_on: date, changed: set[str]) -> None:
    """CL2/CL3: a new or changed date is today or later; the end is not before the start; at most MAX_SPAN_DAYS days."""
    today = india_today()
    for name, value in (("starts_on", starts_on), ("ends_on", ends_on)):
        if name in changed and value < today:
            raise field_error(name, PAST, value.isoformat())
    if ends_on < starts_on:
        raise field_error("ends_on", ENDS_BEFORE, ends_on.isoformat())
    if (ends_on - starts_on).days + 1 > MAX_SPAN_DAYS:
        raise field_error("ends_on", TOO_LONG, ends_on.isoformat())


async def check_owner(db: AsyncSession, user: User, owner_id: UUID) -> None:
    """CL4: upc-010's lead rule -- a manager owns their own; a head themselves or an active direct report."""
    if not await db.scalar(select(User.id).where(User.id == owner_id, *visits.lead_filter(user))):
        raise field_error("owner_user_id", OWNER_INVALID, str(owner_id))


async def check_employees(db: AsyncSession, users: set[UUID], owner_id: UUID, kept: set[UUID]) -> None:
    """CL5: each employee newly added is active partnership staff; a kept one stays even when since deactivated."""
    if owner_id in users:
        raise field_error("participant_user_ids", EMPLOYEE_IS_OWNER)
    added = users - kept
    if added:
        found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(added), User.active.is_(True), User.role.in_(visits.STAFF_ROLES)))
        if found != len(added):
            raise field_error("participant_user_ids", EMPLOYEE_INVALID)


async def stored_people(db: AsyncSession, event_id: UUID) -> set[UUID]:
    return set((await db.scalars(select(EP.user_id).where(EP.event_id == event_id))).all())


# --- writes -------------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, payload: PartnershipEventIn) -> PartnershipEvent:
    check_dates(payload.starts_on, payload.ends_on, {"starts_on", "ends_on"})
    await check_university(db, payload.university_id)
    owner_id = payload.owner_user_id or user.id
    await check_owner(db, user, owner_id)
    users = set(payload.participant_user_ids)
    await check_employees(db, users, owner_id, set())
    code = f"PEV-{await db.scalar(select(PARTNERSHIP_EVENT_CODE_SEQ.next_value())):06d}"
    values = payload.model_dump(include={"kind", "title", "university_id", "starts_on", "ends_on", "location", "notes"})
    e = PartnershipEvent(code=code, owner_user_id=owner_id, created_by_user_id=user.id, status="scheduled", **values)
    db.add(e)
    await db.flush()
    db.add_all(EP(event_id=e.id, user_id=uid) for uid in users)
    audit(db, user, "create", e, {"kind": e.kind, "university_id": str(e.university_id) if e.university_id else None, "employees": len(users)})
    return e


async def update(db: AsyncSession, user: User, e: PartnershipEvent, payload: PartnershipEventUpdate) -> list[str]:
    """Only changed values count (no audit for none). Returns the changed field names."""
    changes = payload.model_dump(exclude_unset=True, exclude={"participant_user_ids"})
    changed = sorted(key for key, value in changes.items() if getattr(e, key) != value)
    check_dates(changes.get("starts_on", e.starts_on), changes.get("ends_on", e.ends_on), set(changed))
    if "university_id" in changed:
        await check_university(db, changes["university_id"])
    if "owner_user_id" in changed:
        await check_owner(db, user, changes["owner_user_id"])
    stored = await stored_people(db, e.id)
    users = set(payload.participant_user_ids) if payload.participant_user_ids is not None else stored
    await check_employees(db, users, changes.get("owner_user_id", e.owner_user_id), stored)
    for key in changed:
        setattr(e, key, changes[key])
    if users != stored:
        changed.append("participant_user_ids")
        if stored - users:
            await db.execute(delete(EP).where(EP.event_id == e.id, EP.user_id.in_(stored - users)))
        db.add_all(EP(event_id=e.id, user_id=uid) for uid in users - stored)
    if changed:
        audit(db, user, "update", e, {"fields": changed})
    return changed


def cancel(db: AsyncSession, user: User, e: PartnershipEvent, reason: str, now: datetime) -> None:
    e.status, e.cancelled_at, e.cancel_reason = "cancelled", now, reason
    audit(db, user, "cancel", e)


# --- output -------------------------------------------------------------------------------------------------------------------------
async def detail_out(db: AsyncSession, user: User, event_id: UUID) -> dict:
    """What every route returns, read as written (populate_existing: never a stale identity-map copy after a commit)."""
    e = await db.scalar(select(PartnershipEvent).where(PartnershipEvent.id == event_id).execution_options(populate_existing=True))
    if e is None:
        raise HTTPException(404, NOT_FOUND)
    uni = await db.get(University, e.university_id) if e.university_id else None
    owner = await db.get_one(User, e.owner_user_id)
    creator = await db.get_one(User, e.created_by_user_id)
    people = (await db.scalars(select(User).join(EP, EP.user_id == User.id).where(EP.event_id == e.id).order_by(User.full_name, User.id))).all()
    overlaps = await calendar.overlaps_for(db, "event", e.id, e.starts_on, e.ends_on, {e.owner_user_id, *(p.id for p in people)})
    can_change = e.status == "scheduled" and is_actor(user, e)
    return {
        **{k: getattr(e, k) for k in ("id", "code", "kind", "title", "starts_on", "ends_on", "location", "notes", "status", "cancelled_at",
                                      "cancel_reason", "created_at", "updated_at")},
        "university": {"id": uni.id, "name": uni.name} if uni else None,
        "owner": person_ref(owner), "created_by": person_ref(creator), "participants": [person_ref(p) for p in people],
        "overlaps": overlaps, "permissions": {"can_edit": can_change, "can_cancel": can_change},
    }  # fmt: skip


def audit(db: AsyncSession, user: User, action: str, e: PartnershipEvent, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, code, kind, counts and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"partnership_event.{action}", entity_type="partnership_event", entity_id=str(e.id),
                    metadata_json={"code": e.code, **(metadata or {})}))  # fmt: skip


def log(event_name: str, user: User, event_id, **extra) -> None:
    logger.info(event_name, extra={"extra_fields": {"actor_id": str(user.id), "event_id": str(event_id), **extra}})
