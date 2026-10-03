"""AGN-019 -- staff performance and the student funnel (DEC-SCOPE-063; spec §4-§5).

Master only (the route refuses staff). Students count for their current owner (P1), selected by the day their agency record was
created (P4). Read-only: nothing here writes, locks or commits."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import ColumnElement, Select, and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrgMember, AgentStudent, OverseasApplication, User, VisaCase
from app.services.agent_applications import WITHDRAWN
from app.services.agent_dashboard import agency_applications, offer_clause, owner_join
from app.services.agent_orgs import org_member_ids
from app.services.agent_students import student_scope

TABLE = ("students", "applications", "offers", "visa_applications", "visa_approvals", "enrollments")
STAGES = ("students", "applications", "submitted", "offers", "visa", "enrolled")
ZEROS = (0,) * 6  # an owner with no row in a GROUP BY result


def cohort(user: User, start: date | None, end: date | None) -> list[ColumnElement]:
    """The caller's agency students (archived included), created within the inclusive UTC days when given (P4, spec §4.1)."""
    where = list(student_scope(user))
    if start:
        where.append(AgentStudent.created_at >= datetime.combine(start, time.min, UTC))
    if end:
        where.append(AgentStudent.created_at < datetime.combine(end + timedelta(days=1), time.min, UTC))
    return where


def _visa_by_application(user: User):
    """One row per application with a visa case, `approved` when any case is: a second case is not a second visa application.
    Limited to the caller's agency applications, so the grouping never reads other agencies' cases."""
    approved = func.bool_or(VisaCase.decision == "approved").label("approved")
    agency = select(OverseasApplication.id).where(*agency_applications(user))
    return select(VisaCase.application_id, approved).where(VisaCase.application_id.in_(agency)).group_by(VisaCase.application_id).subquery()


def _from_cohort(user: User, start: date | None, end: date | None, visa, *columns) -> Select:
    """Cohort students LEFT JOIN their agency applications (by `owner_join`, School-bridged rows excluded) and those applications'
    visa summary, so a student with no application still counts as a student."""
    return (
        select(*columns)
        .select_from(AgentStudent)
        .outerjoin(OverseasApplication, and_(owner_join(), *agency_applications(user)))
        .outerjoin(visa, visa.c.application_id == OverseasApplication.id)
        .where(*cohort(user, start, end))
    )


async def table_counts(db: AsyncSession, user: User, start: date | None, end: date | None) -> dict:
    """Per current owner (P1), AGN-018's G3 columns over the cohort (P5), each application once. Keyed by member id; None =
    unassigned."""
    visa = _visa_by_application(user)

    def applications(condition):
        return func.count(distinct(case((condition, OverseasApplication.id))))

    stmt = _from_cohort(
        user,
        start,
        end,
        visa,
        AgentStudent.assigned_member_id,
        func.count(distinct(case((AgentStudent.status == "active", AgentStudent.id)))),
        applications(OverseasApplication.status != WITHDRAWN),
        applications(offer_clause()),
        applications(visa.c.application_id.is_not(None)),
        applications(visa.c.approved.is_(True)),
        applications(OverseasApplication.status == "enrolled"),
    ).group_by(AgentStudent.assigned_member_id)
    return {member_id: tuple(counts) for member_id, *counts in (await db.execute(stmt)).all()}


def _level(visa) -> ColumnElement[int]:
    """An application's furthest stage (spec §4.2); the first true branch wins, highest first, so a later stage implies the earlier."""
    return case(
        (OverseasApplication.status == "enrolled", 5),
        (visa.c.application_id.is_not(None), 4),
        (offer_clause(), 3),
        (OverseasApplication.submitted_on.is_not(None), 2),
        (OverseasApplication.id.is_not(None), 1),
        else_=0,
    )


async def funnel_counts(db: AsyncSession, user: User, start: date | None, end: date | None) -> dict:
    """P3: per current owner, the cohort's students (archived included) at each stage or a later one, from each student's furthest
    application -- non-increasing by construction. Keyed by member id; None = unassigned."""
    visa = _visa_by_application(user)
    member = AgentStudent.assigned_member_id.label("member_id")
    per_student = _from_cohort(user, start, end, visa, member, func.max(_level(visa)).label("level")).group_by(AgentStudent.id, AgentStudent.assigned_member_id).subquery()
    reached = [func.sum(case((per_student.c.level >= k, 1), else_=0)) for k in range(1, 6)]
    stmt = select(per_student.c.member_id, func.count(), *reached).group_by(per_student.c.member_id)
    return {member_id: tuple(counts) for member_id, *counts in (await db.execute(stmt)).all()}


def _any(counts: dict) -> bool:
    return any(counts[k] for k in TABLE) or any(counts["funnel"].values())


def _sum(parts: list[dict]) -> dict:
    return {**{k: sum(p[k] for p in parts) for k in TABLE}, "funnel": {k: sum(p["funnel"][k] for p in parts) for k in STAGES}}


async def performance(db: AsyncSession, user: User, start: date | None, end: date | None) -> dict:
    """The AGN-019 payload (spec §5.3). Rows (P6): every active staff member; a deactivated one only while they have counts."""
    table = await table_counts(db, user, start, end)
    funnel = await funnel_counts(db, user, start, end)

    def counts(key) -> dict:
        return {**dict(zip(TABLE, table.get(key, ZEROS), strict=True)), "funnel": dict(zip(STAGES, funnel.get(key, ZEROS), strict=True))}

    members = await db.execute(
        select(AgentOrgMember, User.full_name)
        .join(User, User.id == AgentOrgMember.user_id)
        .where(AgentOrgMember.user_id.in_(org_member_ids(user)), AgentOrgMember.role == "staff")
        .order_by(AgentOrgMember.seq)
    )
    rows = []
    for member, name in members.all():
        row = counts(member.id)
        active = member.status == "active"
        if active or _any(row):
            rows.append({"code": member.code, "name": name, "active": active, **row})
    unassigned_counts = counts(None)
    unassigned = unassigned_counts if _any(unassigned_counts) else None
    parts = [*rows, *([unassigned] if unassigned else [])]
    return {
        "date_from": start,
        "date_to": end,
        "rows": rows,
        "unassigned": unassigned,
        "total": _sum(parts),  # an empty list sums to zeros
        "as_of": datetime.now(UTC),
    }
