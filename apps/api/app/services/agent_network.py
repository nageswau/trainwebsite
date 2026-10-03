"""AGN-022 -- Overseas Admin's agent network figures (DEC-SCOPE-064; spec §4, §5.1).

Read-only: nothing here writes, locks or commits. Every function takes organisation ids, never a user -- the admin is not a member
of the agencies it reads. Students, applications and commissions belong to an organisation through the `agent_id` of one of its
members, exactly as AGN-001 scopes them, and the definitions (active student, non-withdrawn application, enrolled) are AGN-018's,
so an agency's own dashboard and this screen cannot disagree."""

from sqlalchemy import Select, and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AgentOrgMember, AgentStudent, ApplicationDeposit, Country, OverseasApplication, University, User
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, with_owner
from app.services.agent_dashboard import commission_totals
from app.services.agent_deposits import PAID_STATES

# School-bridged applications are not agency applications (`with_owner`, A12).
NETWORK_APPLICATION = OverseasApplication.school_student_id.is_(None)
# The applications list filters on the confirmed stages and `withdrawn`; a legacy value is refused, not silently empty.
APPLICATION_FILTERS = (*OVERSEAS_APPLICATION_STAGES, WITHDRAWN)
Assignee = aliased(AgentOrgMember)


def members_of(org_id) -> Select:
    """User ids of every member of one organisation (any member status): the org's side of every `agent_id` join."""
    return select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org_id)


async def org_counts(db: AsyncSession, org_ids) -> dict:
    """`{org_id: {staff_count, students, applications, enrollments}}` for the given orgs -- three statements grouped by
    organisation (never one per org); an org with nothing gets zeros."""
    ids = list(org_ids)
    if not ids:
        return {}
    result = {oid: {"staff_count": 0, "students": 0, "applications": 0, "enrollments": 0} for oid in ids}
    org = AgentOrgMember.org_id
    staff = select(org, func.count()).where(org.in_(ids), AgentOrgMember.role == "staff", AgentOrgMember.status == "active").group_by(org)
    students = (
        select(org, func.count())
        .join(AgentStudent, AgentStudent.agent_id == AgentOrgMember.user_id)
        .where(org.in_(ids), AgentStudent.status == "active")
        .group_by(org)
    )
    applications = (
        select(org, func.count(case((OverseasApplication.status != WITHDRAWN, 1))), func.count(case((OverseasApplication.status == "enrolled", 1))))
        .join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
        .where(org.in_(ids), NETWORK_APPLICATION)
        .group_by(org)
    )
    for oid, n in (await db.execute(staff)).all():
        result[oid]["staff_count"] = n
    for oid, n in (await db.execute(students)).all():
        result[oid]["students"] = n
    for oid, open_apps, enrolled in (await db.execute(applications)).all():
        result[oid]["applications"], result[oid]["enrollments"] = open_apps, enrolled
    return result


async def org_money(db: AsyncSession, org_id) -> dict:
    """N4: commissions in AGN-018's buckets (per currency, never summed across currencies) and the org's deposits (INR only):
    collected = paid + remitted + refunded, then remitted and refunded amounts, not netted; pending / not required excluded."""
    paid = ApplicationDeposit.status.in_(PAID_STATES)
    deposits = (
        await db.execute(
            select(
                func.count(case((paid, 1))),
                func.coalesce(func.sum(case((paid, ApplicationDeposit.amount))), 0),
                func.coalesce(func.sum(case((ApplicationDeposit.status == "remitted", ApplicationDeposit.amount))), 0),
                func.coalesce(func.sum(case((ApplicationDeposit.status == "refunded", ApplicationDeposit.refund_amount))), 0),
            )
            .join(OverseasApplication, OverseasApplication.id == ApplicationDeposit.application_id)
            .where(OverseasApplication.agent_id.in_(members_of(org_id)), NETWORK_APPLICATION)
        )
    ).one()
    count, collected, remitted, refunded = deposits
    return {
        "commission": await commission_totals(db, members_of(org_id)),
        "deposits": {"currency": "INR", "count": count, "collected": float(collected), "remitted": float(remitted), "refunded": float(refunded)},
    }


async def org_students(db: AsyncSession, org_id, *, status: str, limit: int, offset: int) -> tuple[list[dict], int]:
    """N1: one page of the org's students, newest first -- name, status, assignee code, whether a login exists and the open
    applications this agency made for them (by the agency record or the linked login, as AGN-018 `staff_rows`). No contact data."""
    where = [AgentStudent.agent_id.in_(members_of(org_id)), AgentStudent.status == status]
    total = await db.scalar(select(func.count()).select_from(AgentStudent).where(*where))
    applications = (
        select(func.count(distinct(OverseasApplication.id)))
        .where(
            OverseasApplication.agent_id.in_(members_of(org_id)),
            NETWORK_APPLICATION,
            OverseasApplication.status != WITHDRAWN,
            or_(OverseasApplication.agent_student_id == AgentStudent.id, and_(AgentStudent.student_id.is_not(None), OverseasApplication.student_id == AgentStudent.student_id)),
        )
        .correlate(AgentStudent)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(AgentStudent, func.coalesce(User.full_name, AgentStudent.full_name), Assignee.code, applications)
        .outerjoin(User, User.id == AgentStudent.student_id)
        .outerjoin(Assignee, Assignee.id == AgentStudent.assigned_member_id)
        .where(*where)
        .order_by(AgentStudent.created_at.desc(), AgentStudent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        {"id": s.id, "full_name": name, "status": s.status, "assigned_code": code, "has_login": s.student_id is not None, "applications": n, "created_at": s.created_at}
        for s, name, code, n in rows.all()
    ]
    return items, total or 0


async def org_applications(db: AsyncSession, org_id, *, status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    """N1: one page of the org's applications, newest first, School-bridged rows left out (`with_owner`). The student is the
    account's name, else the agency record's."""
    where = [OverseasApplication.agent_id.in_(members_of(org_id)), NETWORK_APPLICATION]
    if status:
        where.append(OverseasApplication.status == status)
    total = await db.scalar(select(func.count()).select_from(OverseasApplication).where(*where))
    stmt = with_owner(
        select(OverseasApplication, University.name, Country.name)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .where(*where)
    )
    rows = await db.execute(stmt.order_by(OverseasApplication.created_at.desc(), OverseasApplication.id.desc()).limit(limit).offset(offset))
    items = [
        {
            "id": a.id, "student_name": name, "university": university, "country": country, "status": a.status,
            "enrollment_date": a.enrollment_date, "created_at": a.created_at, "updated_at": a.updated_at,
        }
        for a, university, country, _account, name in rows.all()
    ]
    return items, total or 0
