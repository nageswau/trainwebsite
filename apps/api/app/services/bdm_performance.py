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
    OverseasApplication,
    Payment,
    SchoolStudent,
    User,
)
from app.api.school_analytics import student_indicators, students_in
from app.services.agent_dashboard import funnel_columns
from app.services.agent_network import NETWORK_APPLICATION, members_of
from app.services.bdm_appointments import IST
from app.services.bdm_metrics import _completed, college_columns, fee_filter, month_range

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


# The master view (spec §3 P10/P11): type -> BDMs -> linked organizations -> value chain (Appendix B.6 V-A / V-S / V-C), live and all
# time. Each organization's figures run the same SQL as its own panels (bdm-020/021/022), one statement per module for every
# organization in scope; the BDM and type figures are sums of them.
# type -> ((key, label, definition, source figure; None = not tracked), ...)
CHAINS: dict[str, tuple[tuple[str, str, str, str | None], ...]] = {
    "agent": (
        ("students", "Students", "Active students of the linked agency.", "students"),
        ("applications", "Applications", "The agency's applications, except withdrawn ones.", "applications"),
        ("enrollment", "Enrollment", "Applications at the Enrolled stage.", "enrollments"),
        ("revenue", "Revenue", "Not tracked: deposits pass through to universities and commission is not BDM revenue.", None),
    ),
    "school": (
        ("students", "Students", "Students of the linked school.", "students"),
        ("profile_building", "Profile Building", "Not tracked: the School module has no profile completion figure.", None),
        ("career_university", "Career/University", "Students with a career guidance session completed.", "career_guidance"),
        ("future_student", "Future Student", "Students with an overseas application.", "future_students"),
    ),
    "college": (
        ("students", "Students", "Students whose account is linked to one of the organization's leads.", "registrations"),
        ("training", "Training", "Those students with at least one enrollment that is not withdrawn.", "training"),
        ("internship", "Internship", "Not tracked: internships are not recorded in EduSphere.", None),
        ("placement", "Placement", "Those students with an accepted or joined job offer.", "placement"),
        ("revenue", "Revenue", "Paid INR fees of those students (agent deposits excluded).", "fees"),
    ),
}


async def _college(db: AsyncSession, ids: list[UUID]) -> dict[UUID, dict]:
    columns = college_columns(BdmOrganization.id)  # correlated: one row per organization, the bdm-021 panel's SQL
    stmt = select(BdmOrganization.id, *(c.label(k) for k, c in columns.items())).where(BdmOrganization.id.in_(ids))
    return {row.id: {**row._mapping, "fees": Decimal(row.fees).quantize(CENTS)} for row in (await db.execute(stmt)).all()}


async def _agent(db: AsyncSession, ids: list[UUID]) -> dict[UUID, dict]:
    members = members_of(BdmOrganization.agent_org_id).correlate(BdmOrganization)  # nested two levels deep: correlate explicitly
    columns = funnel_columns([AgentStudent.agent_id.in_(members)], [OverseasApplication.agent_id.in_(members), NETWORK_APPLICATION])
    stmt = select(BdmOrganization.id, *(c.label(k) for k, c in columns.items())).where(BdmOrganization.id.in_(ids))
    return {row.id: dict(row._mapping) for row in (await db.execute(stmt)).all()}


async def _school(db: AsyncSession, schools: dict[UUID, UUID]) -> dict[UUID, dict]:
    """organization -> figures of its school (`schools`: organization -> school). Career guidance is the School module's own indicator
    (bdm-020 A1), computed once over every school's students and split by school."""
    if not schools:
        return {}
    school_ids = list(set(schools.values()))
    of_school = dict((await db.execute(select(SchoolStudent.id, SchoolStudent.school_id).where(SchoolStudent.school_id.in_(school_ids)))).all())
    guided = (await student_indicators(db, students_in(school_ids)))["guidance"]
    future = set((await db.scalars(select(OverseasApplication.school_student_id).where(
        OverseasApplication.school_student_id.in_(list(of_school))).distinct())).all())
    per_school = {s: {"students": 0, "career_guidance": 0, "future_students": 0} for s in school_ids}
    for student, school in of_school.items():
        per_school[school]["students"] += 1
        per_school[school]["career_guidance"] += student in guided
        per_school[school]["future_students"] += student in future
    return {org: per_school[school] for org, school in schools.items()}


def _chain(bdm_type: str, rows: list[dict]) -> list:
    """The chain's figures summed over organization figures; None for a step that is not tracked."""
    return [None if source is None else sum((r[source] for r in rows), Decimal("0.00") if source == "fees" else 0)
            for _key, _label, _definition, source in CHAINS[bdm_type]]


async def hierarchy(db: AsyncSession, team: Select) -> list[dict]:
    """P10: non-archived organizations of the BDM's own module; Agent / School ones only once linked (the rest are counted)."""
    members = await team_members(db, team)
    orgs = (await db.execute(
        select(BdmOrganization.id, BdmOrganization.code, BdmOrganization.name, BdmOrganization.assigned_bdm_user_id, BdmOrganization.bdm_type,
               BdmOrganization.school_id, BdmOrganization.agent_org_id)
        .join(BdmProfile, BdmProfile.user_id == BdmOrganization.assigned_bdm_user_id)
        .where(BdmOrganization.assigned_bdm_user_id.in_(team), BdmOrganization.archived_at.is_(None), BdmOrganization.bdm_type == BdmProfile.bdm_type)
        .order_by(BdmOrganization.name, BdmOrganization.id))).all()
    link = {"agent": lambda o: o.agent_org_id, "school": lambda o: o.school_id, "college": lambda o: o.id}
    linked = [o for o in orgs if link[o.bdm_type](o) is not None]
    figures_of = {
        **await _college(db, [o.id for o in linked if o.bdm_type == "college"]),
        **await _agent(db, [o.id for o in linked if o.bdm_type == "agent"]),
        **await _school(db, {o.id: o.school_id for o in linked if o.bdm_type == "school"}),
    }
    out = []
    for bdm_type in TYPES:
        bdms = []
        for m in members:
            if m.bdm_type != bdm_type:
                continue
            own = [o for o in linked if o.assigned_bdm_user_id == m.id]
            bdms.append({
                "id": m.id, "full_name": m.full_name, "active": m.active, "organization_count": len(own),
                "not_linked": sum(1 for o in orgs if o.assigned_bdm_user_id == m.id) - len(own),
                "totals": _chain(bdm_type, [figures_of[o.id] for o in own]),
                "organizations": [{"id": o.id, "code": o.code, "name": o.name, "counts": _chain(bdm_type, [figures_of[o.id]])} for o in own],
            })
        ids = {b["id"] for b in bdms}
        out.append({
            "type": bdm_type, "label": f"{bdm_type.capitalize()} BDM",
            "chain": [{"key": k, "label": label, "definition": d, "tracked": s is not None} for k, label, d, s in CHAINS[bdm_type]],
            "bdm_count": sum(1 for b in bdms if b["active"]), "organization_count": sum(b["organization_count"] for b in bdms),
            "not_linked": sum(b["not_linked"] for b in bdms),
            "totals": _chain(bdm_type, [figures_of[o.id] for o in linked if o.assigned_bdm_user_id in ids]),
            "bdms": bdms,
        })
    return out
