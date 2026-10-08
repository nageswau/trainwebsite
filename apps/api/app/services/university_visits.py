"""upc-010 (DEC-SCOPE-128, spec §1, §3): university visits -- who reads, plans and acts, the §8 flow, the approver, and output.

Functions only; nothing here commits -- the route owns the transaction. One transition table (`RULES`) drives both the 409s and the
`permissions` flags. The approver is resolved now, never stored (VS4): the lead's reporting head, unless that head is inactive or took
part (creator, lead or participant), in which case any active super_admin. Logs and audit rows carry ids, codes, statuses and field
names only; reasons live in the visit's own history (`university_visit_events`).
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    UNIVERSITY_VISIT_CODE_SEQ,
    AuditLog,
    Country,
    PartnershipProfile,
    University,
    UniversityContact,
    UniversityVisit,
    UniversityVisitContact,
    UniversityVisitEvent,
    UniversityVisitParticipant,
    User,
)
from app.services import partnership_universities as unis
from app.services.bdm_travel import india_today
from app.services.partnership import partnership_context
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Visit not found"
READ_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # VS7
CREATE_ROLES = frozenset({"partnership_manager", "partnership_head"})  # VS6
STAFF_ROLES = ("partnership_manager", "partnership_head")  # VS11
ACTOR_REFUSAL = "Only the visit's lead or the person who planned it can change it"

# VS9: what may change in each state. The university never changes; status only through the commands.
SCOPE_FIELDS = frozenset({"lead_user_id", "city", "purpose", "proposed_date", "travel_required", "hotel_required", "participant_user_ids"})
PREP_FIELDS = frozenset({"confirmed_date", "travel_notes", "hotel_notes", "agenda", "expected_outcome", "contact_ids"})
AFTER_FIELDS = frozenset({"follow_up_date"})
EARLY_CLOSE = ("planned", "approved", "travel_booked")
# The 409 for a field the status no longer allows (states where some other field is still editable).
FROZEN = {
    "planned": "The follow-up date is set when the visit is completed",
    "approved": "An approved visit's plan can't be changed",
    "travel_booked": "An approved visit's plan can't be changed",
    "visit_completed": "Only the follow-up date can change after the visit",
    "follow_up": "Only the follow-up date can change after the visit",
}


def approval_state(v: UniversityVisit) -> str | None:
    if v.status != "planned":
        return None
    return "waiting" if v.submitted_at else "returned" if v.rejection_reason else "draft"


def editable_fields(v: UniversityVisit) -> frozenset[str]:
    if v.status == "planned":
        return frozenset() if v.submitted_at else SCOPE_FIELDS | PREP_FIELDS
    if v.status in ("approved", "travel_booked"):
        return PREP_FIELDS
    if v.status in ("visit_completed", "follow_up"):
        return AFTER_FIELDS
    return frozenset()


RULES = {
    "edit": lambda v: bool(editable_fields(v)),
    "submit": lambda v: approval_state(v) in ("draft", "returned"),
    "decide": lambda v: approval_state(v) == "waiting",
    "book": lambda v: v.status == "approved",
    "complete": lambda v: v.status == "travel_booked",
    "follow_up": lambda v: v.status == "visit_completed",
    "close": lambda v: v.status in (*EARLY_CLOSE, "follow_up"),
}
FLAGS = {"can_edit": "edit", "can_submit": "submit", "can_book": "book", "can_complete": "complete", "can_follow_up": "follow_up", "can_close": "close"}
VERBS = {"edit": "edited", "submit": "submitted", "decide": "decided", "book": "booked", "complete": "completed", "follow_up": "moved to follow-up", "close": "closed"}
PHRASES = {
    "draft": "is still a draft", "returned": "was returned for changes", "waiting": "is waiting for approval", "approved": "is approved",
    "travel_booked": "has its travel booked", "visit_completed": "is completed", "follow_up": "is in follow-up", "closed": "is closed",
}  # fmt: skip


def refusal(v: UniversityVisit, action: str) -> HTTPException:
    """The 409 for an action outside its row of `RULES`, worded for the user."""
    return HTTPException(409, f"This visit {PHRASES[approval_state(v) or v.status]} and can't be {VERBS[action]}")


def now() -> datetime:
    return datetime.now(UTC)


# --- access -------------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES:
        raise HTTPException(403, "University visits access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def require_creator(db: AsyncSession, user: User) -> None:
    await require_reader(db, user)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Only partnership managers and heads plan visits")


def is_actor(user: User, v: UniversityVisit) -> bool:
    return user.id in (v.lead_user_id, v.created_by_user_id)


def require_actor(user: User, v: UniversityVisit, action: str) -> None:
    if not is_actor(user, v):
        log("university_visit_refused", user, v, action=action, status=403)
        raise HTTPException(403, ACTOR_REFUSAL)


async def load(db: AsyncSession, visit_id: UUID, *, lock: bool = False) -> UniversityVisit:
    stmt = select(UniversityVisit).where(UniversityVisit.id == visit_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    v = await db.scalar(stmt)
    if v is None:
        raise HTTPException(404, NOT_FOUND)
    return v


# --- the approver (VS4) ---------------------------------------------------------------------------------------------------------
async def participant_ids(db: AsyncSession, visit_id: UUID) -> set[UUID]:
    return set((await db.scalars(select(UniversityVisitParticipant.user_id).where(UniversityVisitParticipant.visit_id == visit_id))).all())


async def reporting_head(db: AsyncSession, v: UniversityVisit, excluded: set[UUID], *, lock: bool = False) -> User | None:
    """The lead's head when it may decide; None means the super_admin fallback. `lock` takes FOR SHARE on the profile and the head, so
    a concurrent reassignment or deactivation waits for the decision's commit."""
    stmt = select(PartnershipProfile).where(PartnershipProfile.user_id == v.lead_user_id)
    profile = await db.scalar(stmt.with_for_update(read=True) if lock else stmt)
    if profile is None:  # the lead is a head (VS4: the head travels)
        return None
    head_stmt = select(User).where(User.id == profile.reporting_head_user_id)
    head = await db.scalar(head_stmt.with_for_update(read=True) if lock else head_stmt)
    return head if head is not None and head.active and head.id not in excluded else None


async def took_part(db: AsyncSession, v: UniversityVisit) -> set[UUID]:
    """Who planned, leads or joins the visit -- none of them decides it (AC5)."""
    return {v.created_by_user_id, v.lead_user_id} | await participant_ids(db, v.id)


async def can_decide(db: AsyncSession, user: User, v: UniversityVisit, *, lock: bool = False) -> bool:
    excluded = await took_part(db, v)
    if user.id in excluded:
        return False
    head = await reporting_head(db, v, excluded, lock=lock)
    return user.id == head.id if head is not None else user.role == "super_admin"


async def approvers(db: AsyncSession, v: UniversityVisit) -> list[User]:
    """Who is told a visit waits (VS15): the head, or every active super_admin outside the visit."""
    excluded = await took_part(db, v)
    head = await reporting_head(db, v, excluded)
    if head is not None:
        return [head]
    stmt = select(User).where(User.role == "super_admin", User.active.is_(True), User.id.not_in(excluded)).order_by(User.id)
    return list((await db.scalars(stmt)).all())


Head = aliased(User)


def _head_decides():
    """SQL twin of `reporting_head(...) is not None` for the queue."""
    took_part = exists().where(UniversityVisitParticipant.visit_id == UniversityVisit.id, UniversityVisitParticipant.user_id == Head.id)
    return (
        select(PartnershipProfile.user_id)
        .join(Head, Head.id == PartnershipProfile.reporting_head_user_id)
        .where(PartnershipProfile.user_id == UniversityVisit.lead_user_id, Head.active.is_(True), Head.id != UniversityVisit.created_by_user_id, ~took_part)
        .exists()
    )


def approvals_filter(user: User) -> list:
    """The queue: waiting visits this caller may decide (the same rule as `can_decide`)."""
    waiting = [UniversityVisit.status == "planned", UniversityVisit.submitted_at.is_not(None)]
    if user.role == "partnership_head":
        mine = exists().where(PartnershipProfile.user_id == UniversityVisit.lead_user_id, PartnershipProfile.reporting_head_user_id == user.id)
        return [*waiting, mine, _head_decides()]
    joined = exists().where(UniversityVisitParticipant.visit_id == UniversityVisit.id, UniversityVisitParticipant.user_id == user.id)
    return [*waiting, ~_head_decides(), UniversityVisit.created_by_user_id != user.id, UniversityVisit.lead_user_id != user.id, ~joined]


# --- validation -----------------------------------------------------------------------------------------------------------------
def check_future(value: date | None, label: str) -> None:
    if value is not None and value < india_today():
        raise HTTPException(422, f"{label} can't be in the past")


async def university_for(db: AsyncSession, user: User, university_id: UUID) -> University:
    """VS6: the university must exist (422), be in the caller's edit scope (403) and be active (409) -- the upc-006 contact scope."""
    uni = await db.get(University, university_id)
    if uni is None:
        raise HTTPException(422, "Choose a university")
    unis.require(user, uni, await unis.team_of(db, user), "can_edit_contacts", "visit_create")
    return uni


async def check_lead(db: AsyncSession, user: User, lead_id: UUID) -> None:
    """VS6: a manager leads their own visits; a head leads or picks an active direct report."""
    if lead_id == user.id:
        return
    if user.role == "partnership_head":
        stmt = (
            select(User.id)
            .join(PartnershipProfile, PartnershipProfile.user_id == User.id)
            .where(User.id == lead_id, User.active.is_(True), User.role == "partnership_manager", PartnershipProfile.reporting_head_user_id == user.id)
        )
        if await db.scalar(stmt):
            return
        raise HTTPException(422, "Choose yourself or an active partnership manager from your team to lead the visit")
    raise HTTPException(422, "You lead the visits you plan")


async def check_participants(db: AsyncSession, ids: list[UUID], lead_id: UUID) -> None:
    if lead_id in ids:
        raise HTTPException(422, "The lead is already on the visit; add other employees only")
    if ids:
        found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(ids), User.active.is_(True), User.role.in_(STAFF_ROLES)))
        if found != len(ids):
            raise HTTPException(422, "Choose active partnership managers or heads as other employees")


async def check_contacts(db: AsyncSession, ids: list[UUID], university_id: UUID) -> None:
    if ids:
        found = await db.scalar(select(func.count()).select_from(UniversityContact).where(UniversityContact.id.in_(ids), UniversityContact.university_id == university_id))
        if found != len(ids):
            raise HTTPException(422, "Choose meeting contacts of this university")


async def replace_links(db: AsyncSession, v: UniversityVisit, participants: list[UUID] | None, contacts: list[UUID] | None) -> None:
    """Replaces each list that was sent (None = unchanged)."""
    if participants is not None:
        await db.execute(delete(UniversityVisitParticipant).where(UniversityVisitParticipant.visit_id == v.id))
        db.add_all(UniversityVisitParticipant(visit_id=v.id, user_id=uid) for uid in participants)
    if contacts is not None:
        await db.execute(delete(UniversityVisitContact).where(UniversityVisitContact.visit_id == v.id))
        db.add_all(UniversityVisitContact(visit_id=v.id, contact_id=cid) for cid in contacts)
    await db.flush()


async def contact_ids_of(db: AsyncSession, visit_id: UUID) -> set[UUID]:
    return set((await db.scalars(select(UniversityVisitContact.contact_id).where(UniversityVisitContact.visit_id == visit_id))).all())


async def next_code(db: AsyncSession) -> str:
    return f"VIS-{await db.scalar(select(UNIVERSITY_VISIT_CODE_SEQ.next_value())):06d}"


# --- the record ----------------------------------------------------------------------------------------------------------------
def record(db: AsyncSession, user: User, v: UniversityVisit, action: str, before: str | None, *, reason: str | None = None, fields: list[str] | None = None) -> None:
    """One history row (VS14) and one audit row (ids, code, statuses, field names) in the caller's transaction."""
    db.add(UniversityVisitEvent(visit_id=v.id, action=action, from_status=before, to_status=v.status, actor_user_id=user.id, reason=reason))
    meta = {"code": v.code, "university_id": str(v.university_id), "from": before, "to": v.status, **({"fields": fields} if fields else {})}
    db.add(AuditLog(user_id=user.id, action=f"university_visit.{action}", entity_type="university_visit", entity_id=str(v.id), metadata_json=meta))


def log(event: str, user: User, v: UniversityVisit, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "visit_id": str(v.id), "status": v.status, **extra}})


# --- output ----------------------------------------------------------------------------------------------------------------------
Lead = aliased(User)


def rows_stmt(filters: list):
    """One query for a list page: visit + university + country + lead (no N+1)."""
    return (
        select(UniversityVisit, University, Country, Lead)
        .join(University, University.id == UniversityVisit.university_id)
        .join(Country, Country.id == University.country_id)
        .join(Lead, Lead.id == UniversityVisit.lead_user_id)
        .where(*filters)
    )


def _university(uni: University, country: Country) -> dict:
    return {"id": uni.id, "name": uni.name, "university_code": uni.university_code, "city": uni.city, "country": {"id": country.id, "name": country.name}}


def row_out(v: UniversityVisit, uni: University, country: Country, lead: User) -> dict:
    return {
        "id": v.id, "code": v.code, "university": _university(uni, country), "city": v.city, "lead": person_ref(lead),
        "proposed_date": v.proposed_date, "confirmed_date": v.confirmed_date, "status": v.status, "approval_state": approval_state(v),
        "submitted_at": v.submitted_at,
    }  # fmt: skip


async def page(db: AsyncSession, filters: list, limit: int, offset: int, order: tuple) -> dict:
    stmt = rows_stmt(filters)
    total = await db.scalar(select(func.count()).select_from(stmt.with_only_columns(UniversityVisit.id).subquery()))
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [row_out(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def detail_out(db: AsyncSession, user: User, v: UniversityVisit) -> dict:
    """What every route returns. Refreshes first: server defaults (timestamps) are expired after a flush."""
    await db.refresh(v)
    uni = await db.get_one(University, v.university_id)
    country = await db.get_one(Country, uni.country_id)
    lead = await db.get_one(User, v.lead_user_id)
    creator = await db.get_one(User, v.created_by_user_id)
    decider = await db.get(User, v.decided_by_user_id) if v.decided_by_user_id else None
    people = (
        await db.scalars(
            select(User).join(UniversityVisitParticipant, UniversityVisitParticipant.user_id == User.id).where(UniversityVisitParticipant.visit_id == v.id).order_by(User.full_name, User.id)
        )
    ).all()
    contacts = (
        await db.scalars(
            select(UniversityContact)
            .join(UniversityVisitContact, UniversityVisitContact.contact_id == UniversityContact.id)
            .where(UniversityVisitContact.visit_id == v.id)
            .order_by(func.lower(UniversityContact.name), UniversityContact.id)
        )
    ).all()
    events = (
        await db.execute(
            select(UniversityVisitEvent, User)
            .join(User, User.id == UniversityVisitEvent.actor_user_id)
            .where(UniversityVisitEvent.visit_id == v.id)
            .order_by(UniversityVisitEvent.created_at, UniversityVisitEvent.id)
        )
    ).all()
    actor = is_actor(user, v)
    permissions = {flag: actor and RULES[action](v) for flag, action in FLAGS.items()}
    permissions["can_decide"] = RULES["decide"](v) and await can_decide(db, user, v)
    return {
        **row_out(v, uni, country, lead),
        **{
            k: getattr(v, k)
            for k in (
                "purpose",
                "travel_required",
                "travel_notes",
                "hotel_required",
                "hotel_notes",
                "agenda",
                "expected_outcome",
                "follow_up_date",
                "rejection_reason",
                "decided_at",
                "close_reason",
                "created_at",
                "updated_at",
            )
        },
        "created_by": person_ref(creator),
        "decided_by": person_ref(decider) if decider else None,
        "participants": [person_ref(p) for p in people],
        "contacts": [{"id": c.id, "name": c.name, "designation": c.designation} for c in contacts],
        "events": [{"action": e.action, "from_status": e.from_status, "to_status": e.to_status, "actor": person_ref(a), "reason": e.reason, "created_at": e.created_at} for e, a in events],
        "permissions": permissions,
        "editable_fields": sorted(editable_fields(v)) if actor else [],
    }


# --- option lists (what the caller may submit) ------------------------------------------------------------------------------------
async def university_scope(db: AsyncSession, user: User) -> list:
    """SQL twin of upc-003's edit scope for the two creator roles (VS6), active universities only."""
    if user.role == "partnership_manager":
        owned = or_(University.primary_manager_user_id == user.id, University.backup_manager_user_id == user.id)
    else:
        team = await unis.team_of(db, user)
        owned = or_(University.primary_manager_user_id.is_(None), University.primary_manager_user_id.in_(team), University.backup_manager_user_id.in_(team))
    return [University.active.is_(True), owned]


def lead_filter(user: User) -> list:
    if user.role == "partnership_manager":
        return [User.id == user.id]
    team = select(PartnershipProfile.user_id).where(PartnershipProfile.reporting_head_user_id == user.id)
    return [or_(User.id == user.id, and_(User.id.in_(team), User.active.is_(True), User.role == "partnership_manager"))]
