"""upc-011 (DEC-SCOPE-150, spec CL8-CL12): the §9 calendar -- a read-only union of university meetings (upc-009), university visits
(upc-010) and partnership events, whose calendar it is, and the per-employee overlap warning.

Functions only; nothing here writes. Three range queries (each joined to its university), one people query per source and one user
query, each bounded by MAX_ROWS. An overlap is the same employee on two items whose intervals intersect (CL10): a visit occupies its
whole IST day, an event its whole days, a meeting a 60-minute slot from its start."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PartnershipEvent,
    PartnershipEventParticipant,
    PartnershipProfile,
    University,
    UniversityMeeting,
    UniversityMeetingParticipant,
    UniversityVisit,
    UniversityVisitEvent,
    UniversityVisitParticipant,
    User,
)
from app.services.bdm_appointments import IST
from app.services.partnership import partnership_context
from app.services.telecaller import person_ref
from app.services.university_visits import STAFF_ROLES

READ_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # CL7
MAX_DAYS = 31  # CL8 (bdm-013 K2)
MAX_ROWS = 500  # per source; far above real use
MEETING_SLOT = timedelta(minutes=60)  # CL10: meetings have no duration (MG3)
EMPLOYEE_NOT_FOUND = "Employee not found"

M, V, E = UniversityMeeting, UniversityVisit, PartnershipEvent
VISIT_DAY = func.coalesce(V.confirmed_date, V.proposed_date)


@dataclass
class Item:
    source: str
    kind: str
    id: UUID
    code: str
    title: str
    starts_on: date
    ends_on: date
    starts_at: datetime | None
    status: str
    university: dict | None
    people: list[UUID]
    overlaps: list[dict] = field(default_factory=list)

    @property
    def interval(self) -> tuple[datetime, datetime]:
        if self.starts_at is not None:
            return self.starts_at, self.starts_at + MEETING_SLOT
        return day_start(self.starts_on), day_start(self.ends_on + timedelta(days=1))

    def ref(self) -> dict:
        return {"source": self.source, "id": self.id, "code": self.code, "title": self.title}


def day_start(d: date) -> datetime:
    return datetime.combine(d, time(), IST)


# --- access and scope (CL7, CL9) ----------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES:
        raise HTTPException(403, "Partnership calendar access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def _team(db: AsyncSession, head: User) -> list[User]:
    reports = select(PartnershipProfile.user_id).where(PartnershipProfile.reporting_head_user_id == head.id)
    return list((await db.scalars(select(User).where(or_(User.id == head.id, User.id.in_(reports))).order_by(User.full_name, User.id))).all())


async def employees(db: AsyncSession, user: User) -> list[User]:
    """CL9: the people this caller may choose -- a manager themselves, a head their team, super_admin every partnership employee."""
    await require_reader(db, user)
    if user.role == "partnership_manager":
        return [user]
    if user.role == "partnership_head":
        return await _team(db, user)
    return list((await db.scalars(select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.full_name, User.id).limit(MAX_ROWS))).all())


async def scope(db: AsyncSession, user: User, user_id: UUID | None) -> tuple[set[UUID] | None, User | None]:
    """CL9: (whose items, the named employee). None = everyone (super_admin without `user_id`). Out of scope is the 404 of a missing one."""
    await require_reader(db, user)
    if user.role == "super_admin":
        if user_id is None:
            return None, None
        chosen = await db.scalar(select(User).where(User.id == user_id, User.role.in_(STAFF_ROLES)))
    else:
        people = [user] if user.role == "partnership_manager" else await _team(db, user)
        if user_id is None:
            return {p.id for p in people}, (user if user.role == "partnership_manager" else None)
        chosen = next((p for p in people if p.id == user_id), None)
    if chosen is None:
        raise HTTPException(404, EMPLOYEE_NOT_FOUND)
    return {chosen.id}, chosen


def check_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"The calendar shows at most {MAX_DAYS} days")


# --- the union (CL1, CL8) -----------------------------------------------------------------------------------------------------------
def _uni(uni: University | None) -> dict | None:
    return None if uni is None else {"id": uni.id, "name": uni.name}


async def _people(db: AsyncSession, table, key, ids: list[UUID]) -> dict[UUID, list[UUID]]:
    out: dict[UUID, list[UUID]] = {}
    if ids:
        for item_id, user_id in (await db.execute(select(key, table.user_id).where(key.in_(ids), table.user_id.is_not(None)))).all():
            out.setdefault(item_id, []).append(user_id)
    return out


async def items_in(db: AsyncSession, date_from: date, date_to: date, people: set[UUID] | None) -> tuple[list[Item], bool]:
    """Every non-cancelled item touching [date_from, date_to] (IST) with one of `people` on it (None = all), ordered by start."""
    MP, VP, EP = UniversityMeetingParticipant, UniversityVisitParticipant, PartnershipEventParticipant
    meetings = (await db.execute(
        select(M, University).join(University, University.id == M.university_id)
        .where(M.status != "cancelled", M.starts_at >= day_start(date_from), M.starts_at < day_start(date_to + timedelta(days=1)),
               *_person_filter(people, M.responsible_user_id, MP, MP.meeting_id, M.id))
        .order_by(M.starts_at, M.id).limit(MAX_ROWS + 1)
    )).all()  # fmt: skip
    called_off = and_(V.status == "closed", ~exists().where(UniversityVisitEvent.visit_id == V.id, UniversityVisitEvent.to_status == "visit_completed"))
    visits = (await db.execute(
        select(V, University).join(University, University.id == V.university_id)
        .where(VISIT_DAY >= date_from, VISIT_DAY <= date_to, not_(called_off), *_person_filter(people, V.lead_user_id, VP, VP.visit_id, V.id))
        .order_by(VISIT_DAY, V.code).limit(MAX_ROWS + 1)
    )).all()  # fmt: skip
    events = (await db.execute(
        select(E, University).outerjoin(University, University.id == E.university_id)
        .where(E.status == "scheduled", E.starts_on <= date_to, E.ends_on >= date_from, *_person_filter(people, E.owner_user_id, EP, EP.event_id, E.id))
        .order_by(E.starts_on, E.code).limit(MAX_ROWS + 1)
    )).all()  # fmt: skip
    truncated = any(len(rows) > MAX_ROWS for rows in (meetings, visits, events))
    meetings, visits, events = meetings[:MAX_ROWS], visits[:MAX_ROWS], events[:MAX_ROWS]

    m_people = await _people(db, MP, MP.meeting_id, [m.id for m, _ in meetings])
    v_people = await _people(db, VP, VP.visit_id, [v.id for v, _ in visits])
    e_people = await _people(db, EP, EP.event_id, [e.id for e, _ in events])
    items: list[Item] = []
    for m, uni in meetings:
        d = m.starts_at.astimezone(IST).date()
        items.append(Item("meeting", "university_meeting", m.id, m.code, uni.name, d, d, m.starts_at, m.status, _uni(uni),
                          [m.responsible_user_id, *m_people.get(m.id, [])]))  # fmt: skip
    for v, uni in visits:
        d = v.confirmed_date or v.proposed_date
        items.append(Item("visit", "university_visit", v.id, v.code, f"{uni.name}, {v.city}", d, d, None, v.status, _uni(uni),
                          [v.lead_user_id, *v_people.get(v.id, [])]))  # fmt: skip
    for e, uni in events:
        items.append(Item("event", e.kind, e.id, e.code, e.title, e.starts_on, e.ends_on, None, e.status, _uni(uni),
                          [e.owner_user_id, *e_people.get(e.id, [])]))  # fmt: skip
    items.sort(key=lambda x: (x.interval[0], x.code))
    return items, truncated


def _person_filter(people: set[UUID] | None, owner, table, link, item_id) -> list:
    """One of `people` owns the item or takes part in it (None = no filter)."""
    if people is None:
        return []
    return [or_(owner.in_(people), exists().where(link == item_id, table.user_id.in_(people)))]


# --- overlaps (CL10-CL12) -----------------------------------------------------------------------------------------------------------
def mark_overlaps(items: list[Item], among: set[UUID] | None, users: dict[UUID, User]) -> None:
    """Adds to each item every (employee, other item) pair whose intervals intersect, for employees in `among` (None = all)."""
    by_person: dict[UUID, list[Item]] = {}
    for item in items:
        for pid in dict.fromkeys(item.people):
            if among is None or pid in among:
                by_person.setdefault(pid, []).append(item)
    for pid, mine in by_person.items():
        for i, a in enumerate(mine):
            a_start, a_end = a.interval
            for b in mine[i + 1:]:
                b_start, b_end = b.interval
                if a_start < b_end and b_start < a_end:
                    employee = person_ref(users[pid])
                    a.overlaps.append({"employee": employee, "item": b.ref()})
                    b.overlaps.append({"employee": employee, "item": a.ref()})


async def users_of(db: AsyncSession, items: list[Item]) -> dict[UUID, User]:
    ids = {pid for item in items for pid in item.people}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}


def item_out(item: Item, users: dict[UUID, User]) -> dict:
    return {
        "source": item.source, "kind": item.kind, "id": item.id, "code": item.code, "title": item.title, "starts_on": item.starts_on,
        "ends_on": item.ends_on, "starts_at": item.starts_at, "status": item.status, "university": item.university,
        "people": [person_ref(users[pid]) for pid in dict.fromkeys(item.people)], "overlaps": item.overlaps,
    }  # fmt: skip


async def calendar(db: AsyncSession, date_from: date, date_to: date, people: set[UUID] | None) -> tuple[list[dict], bool]:
    items, truncated = await items_in(db, date_from, date_to, people)
    users = await users_of(db, items)
    mark_overlaps(items, people, users)
    return [item_out(item, users) for item in items], truncated


async def overlaps_for(db: AsyncSession, source: str, item_id: UUID, first: date, last: date, people: set[UUID]) -> list[dict]:
    """CL11/CL12: one item's overlaps for all its people, computed over the item's own days (complete for multi-day events)."""
    items, _ = await items_in(db, first, last, people)
    users = await users_of(db, items)
    mark_overlaps(items, people, users)
    return next((item.overlaps for item in items if item.source == source and item.id == item_id), [])
