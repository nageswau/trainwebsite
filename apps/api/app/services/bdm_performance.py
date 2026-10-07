"""bdm-024 (DEC-SCOPE-111, spec §3-§4): the management performance figures of Appendix B.6 (P-02...P-08) for an IST period.

Every figure is counted once, at (BDM, organization) grain, by one grouped statement; the type table, the BDM list and a BDM's
organizations are sums of the same rows, so the levels of the drill-down cannot disagree (AC2, P8). Read-only; only counts and sums
leave this module."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, distinct, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentOrgMember,
    AgentStudent,
    BdmAppointment,
    BdmMou,
    BdmMouEvent,
    BdmOrganization,
    BdmProfile,
    BdmTrip,
    Enquiry,
    Payment,
    SchoolStudent,
    User,
)
from app.services.bdm_appointments import IST
from app.services.bdm_metrics import _completed, fee_filter, month_range

TYPES = ("agent", "school", "college")
FIGURES = ("meetings", "trips", "new_organizations", "mous", "leads", "students", "revenue")
MAX_DAYS = 366  # P2: bounds the heaviest aggregation in the backlog
CENTS = Decimal("0.01")
BAD_ORDER = "The period must start on or before its end"
TOO_LONG = f"The period can be at most {MAX_DAYS} days"

Key = tuple[UUID, UUID | None]  # (BDM, organization); a trip has no organization


def period(from_: date | None, to: date | None, today: date) -> tuple[date, date]:
    """P2: inclusive IST dates; each end defaults to the current IST month's."""
    month_start, month_end = month_range(today.replace(day=1))
    start = from_ or month_start.date()
    end = to or (month_end - timedelta(days=1)).date()
    if start > end:
        raise HTTPException(422, BAD_ORDER)
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(422, TOO_LONG)
    return start, end


def _instants(start: date, end: date) -> tuple[datetime, datetime]:
    """The inclusive IST dates as a half-open instant range (the bdm_metrics builders' window)."""
    return datetime.combine(start, time.min, tzinfo=IST), datetime.combine(end + timedelta(days=1), time.min, tzinfo=IST)


def trip_filter(team: Select, start: date, end: date) -> list:
    """P-03 (T-M05's rule): trips travelling in the period, except cancelled or rejected ones."""
    return [BdmTrip.bdm_user_id.in_(team), BdmTrip.travel_status != "cancelled", BdmTrip.approval_status != "rejected",
            BdmTrip.travel_date >= start, BdmTrip.travel_date <= end]


def _statements(team: Select, start: date, end: date) -> list[tuple[str, Select]]:
    """(figure, SELECT bdm, organization, value GROUP BY both). Students has one statement per organization module."""
    lo, hi = _instants(start, end)

    def within(column) -> list:
        return [column >= lo, column < hi]

    def grouped(owner, org, value, *where, joins=()) -> Select:
        stmt = select(owner, org, value)
        for target, on in joins:
            stmt = stmt.join(target, on)
        return stmt.where(*where).group_by(owner, org)

    def assigned(bdm_type: str) -> list:
        """P5/P6: Students and Revenue go to the BDM the organization is assigned to now, by its module's rule."""
        return [BdmOrganization.assigned_bdm_user_id.in_(team), BdmOrganization.bdm_type == bdm_type]

    owner, org = BdmOrganization.assigned_bdm_user_id, BdmOrganization.id
    return [
        ("meetings", grouped(BdmAppointment.bdm_user_id, BdmAppointment.organization_id, func.count(), *_completed(team, lo, hi))),  # M-06
        ("trips", select(BdmTrip.bdm_user_id, null(), func.count()).where(*trip_filter(team, start, end)).group_by(BdmTrip.bdm_user_id)),
        ("new_organizations", grouped(BdmOrganization.created_by_user_id, org, func.count(), BdmOrganization.created_by_user_id.in_(team),
                                      *within(BdmOrganization.created_at))),  # M-14, any type
        ("mous", grouped(BdmMouEvent.actor_user_id, BdmMou.organization_id, func.count(), BdmMouEvent.actor_user_id.in_(team),
                         BdmMouEvent.to_status == "signed", BdmMouEvent.from_status.is_distinct_from("signed"), *within(BdmMouEvent.created_at),
                         joins=[(BdmMou, BdmMou.id == BdmMouEvent.mou_id)])),  # M-11
        ("leads", grouped(Enquiry.bdm_user_id, Enquiry.bdm_organization_id, func.count(), Enquiry.bdm_user_id.in_(team),
                          *within(Enquiry.created_at))),  # M-12
        ("students", grouped(owner, org, func.count(distinct(Enquiry.converted_user_id)), *assigned("college"), *within(Enquiry.converted_at),
                             joins=[(Enquiry, Enquiry.bdm_organization_id == org)])),  # F-3's population, converted in the period
        ("students", grouped(owner, org, func.count(SchoolStudent.id), *assigned("school"), *within(SchoolStudent.created_at),
                             joins=[(SchoolStudent, SchoolStudent.school_id == BdmOrganization.school_id)])),  # M-22
        ("students", grouped(owner, org, func.count(distinct(AgentStudent.id)), *assigned("agent"), AgentStudent.status == "active",
                             *within(AgentStudent.created_at),
                             joins=[(AgentOrgMember, AgentOrgMember.org_id == BdmOrganization.agent_org_id),
                                    (AgentStudent, AgentStudent.agent_id == AgentOrgMember.user_id)])),  # A-01's population, added in the period
        ("revenue", grouped(owner, org, func.sum(Payment.amount), *assigned("college"), *fee_filter(), *within(Payment.created_at),
                            joins=[(Enquiry, Enquiry.bdm_organization_id == org), (Payment, Payment.user_id == Enquiry.converted_user_id)])),  # R-1
    ]


async def figures(db: AsyncSession, team: Select, start: date, end: date) -> dict[Key, dict[str, int | Decimal]]:
    """(BDM, organization) -> the non-zero figures of the period. A constant number of statements whatever the team size."""
    out: dict[Key, dict[str, int | Decimal]] = defaultdict(dict)
    for figure, stmt in _statements(team, start, end):
        for bdm_id, org_id, value in (await db.execute(stmt)).all():
            row = out[(bdm_id, org_id)]
            row[figure] = row.get(figure, 0) + value
    return out


async def team_members(db: AsyncSession, team: Select) -> list:
    """The BDMs in scope (active or not, P4), by name: rows of (id, full_name, active, bdm_type)."""
    stmt = (select(User.id, User.full_name, User.active, BdmProfile.bdm_type).join(BdmProfile, BdmProfile.user_id == User.id)
            .where(User.id.in_(team)).order_by(User.full_name, User.id))
    return list((await db.execute(stmt)).all())


def total(rows, bdm_type: str) -> dict:
    """The figures of some (BDM, organization) rows of one BDM type summed; Revenue is tracked for College only (P6, D17)."""
    out: dict = dict.fromkeys(FIGURES, 0)
    out["revenue"] = Decimal(0) if bdm_type == "college" else None
    for row in rows:
        for figure, value in row.items():
            if figure != "revenue" or out["revenue"] is not None:
                out[figure] += value
    if out["revenue"] is not None:
        out["revenue"] = Decimal(out["revenue"]).quantize(CENTS)
    return out
