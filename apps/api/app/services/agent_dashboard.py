"""AGN-018 -- the agency dashboard aggregates (DEC-SCOPE-062; spec §4-§5).

Every count is SQL over the existing scope helpers, so a Master counts the agency and a staff member only their assigned students
(G4) with no new scope logic. Read-only: nothing here writes, locks or commits."""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Select, and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import agent_may, is_agent_staff
from app.models import AgentCommission, AgentOrgMember, AgentStudent, Country, OverseasApplication, StudentDocument, University, User, VisaCase
from app.services.agent_applications import OFFER_COUNTED_STATUSES, WITHDRAWN
from app.services.agent_documents import document_scope
from app.services.agent_orgs import org_member_ids
from app.services.agent_students import application_scope, student_scope
from app.services.agent_tasks import pending_stmt

BREAKDOWN_SIZE = 10  # D2: the top ten, the rest summed into `other`
CLAIMABLE = ("eligible", "estimated")  # the portal's "Claimable commission" statuses


def offer_clause() -> ColumnElement[bool]:
    """O5 (DEC-SCOPE-056) in SQL -- `counts_as_offer`'s twin (a parity test pins them): the stage reached `offer` (legacy values
    included) or an offer is recorded, so an application withdrawn after its offer still counts."""
    return or_(OverseasApplication.status.in_(OFFER_COUNTED_STATUSES), OverseasApplication.offer_type.is_not(None))


def owner_join() -> ColumnElement[bool]:
    """An application belongs to an agency student by the agency record, or by the student's login (AGN-008 A6). Shared by the
    AGN-018 staff table and AGN-019 performance, so both attribute an application to the same student."""
    return or_(OverseasApplication.agent_student_id == AgentStudent.id, and_(AgentStudent.student_id.is_not(None), OverseasApplication.student_id == AgentStudent.student_id))


def agency_applications(user) -> list[ColumnElement]:
    """The applications the caller may see, School-bridged rows left out exactly as `with_owner` leaves them out (A12)."""
    return [*application_scope(user), OverseasApplication.school_student_id.is_(None)]


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _visa(user: User, *extra):
    """Distinct applications with a visa case -- a second case on one application is not a second visa application."""
    stmt = select(func.count(distinct(VisaCase.application_id))).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
    return stmt.where(*agency_applications(user), *extra).scalar_subquery()


async def headline_counts(db: AsyncSession, user: User) -> dict[str, int]:
    """The eight headline KPIs (spec §4) as scalar subqueries of ONE statement, so they come from one snapshot."""
    apps = agency_applications(user)
    columns = {
        "students": _count(AgentStudent, *student_scope(user), AgentStudent.status == "active"),
        "applications": _count(OverseasApplication, *apps, OverseasApplication.status != WITHDRAWN),
        "offers": _count(OverseasApplication, *apps, offer_clause()),
        "visa_applications": _visa(user),
        "visa_approvals": _visa(user, VisaCase.decision == "approved"),
        "enrollments": _count(OverseasApplication, *apps, OverseasApplication.status == "enrolled"),
        "pending_documents": _count(StudentDocument, *document_scope(user), StudentDocument.verification_status == "pending"),
        "pending_actions": pending_stmt(user).scalar_subquery(),
    }
    row = (await db.execute(select(*(column.label(key) for key, column in columns.items())))).one()
    return dict(row._mapping)


async def breakdown(db: AsyncSession, user: User, label, key) -> dict:
    """Open applications grouped by `key` (shown as `label`), the top ten (D2). The window total comes from the same statement, so
    `other` can never disagree with the items."""
    count = func.count()
    stmt = (
        select(label, count, func.sum(count).over())
        .select_from(OverseasApplication)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .where(*agency_applications(user), OverseasApplication.status != WITHDRAWN)
        .group_by(key, label)
        .order_by(count.desc(), label)
        .limit(BREAKDOWN_SIZE)
    )
    rows = (await db.execute(stmt)).all()
    items = [{"label": name, "count": n} for name, n, _ in rows]
    total = int(rows[0][2]) if rows else 0
    return {"items": items, "other": total - sum(i["count"] for i in items)}


async def staff_rows(db: AsyncSession, user: User) -> tuple[list[dict], int]:
    """Master only (G2): per staff member, exactly what that member's own dashboard shows -- students by assignment (active),
    applications by `application_scope`'s two paths (the agency record, or the linked login), each application once. Plus the
    agency's unassigned active students."""
    agency = org_member_ids(user)
    by_assignee = select(AgentStudent.assigned_member_id, func.count()).where(AgentStudent.agent_id.in_(agency), AgentStudent.status == "active")
    students = dict((await db.execute(by_assignee.group_by(AgentStudent.assigned_member_id))).all())

    def distinct_apps(condition):
        return func.count(distinct(case((condition, OverseasApplication.id))))

    per_member = (
        select(AgentStudent.assigned_member_id, distinct_apps(OverseasApplication.status != WITHDRAWN), distinct_apps(offer_clause()), distinct_apps(OverseasApplication.status == "enrolled"))
        .select_from(OverseasApplication)
        .join(AgentStudent, owner_join())
        .where(*agency_applications(user), AgentStudent.agent_id.in_(agency), AgentStudent.assigned_member_id.is_not(None))
        .group_by(AgentStudent.assigned_member_id)
    )
    apps = {member_id: counts for member_id, *counts in (await db.execute(per_member)).all()}
    members = await db.execute(
        select(AgentOrgMember, User.full_name)
        .join(User, User.id == AgentOrgMember.user_id)
        .where(AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == "staff")
        .order_by(AgentOrgMember.seq)
    )
    rows = []
    for member, name in members.all():
        active = member.status == "active"
        if not active and not students.get(member.id):
            continue  # D3: a deactivated member drops out once they hold no active students
        applications, offers, enrollments = apps.get(member.id, (0, 0, 0))
        rows.append({"code": member.code, "name": name, "active": active, "students": students.get(member.id, 0), "applications": applications, "offers": offers, "enrollments": enrollments})
    return rows, students.get(None, 0)


async def commission_summary(db: AsyncSession, user: User) -> dict:
    """Master only (DEC-SCOPE-040 S1): the portal's three commission figures, per currency and never summed across currencies."""
    return await commission_totals(db, org_member_ids(user))


async def commission_totals(db: AsyncSession, member_ids: Select) -> dict:
    """The three commission figures for the agents in `member_ids` -- the caller's agency (above) or, for Overseas Admin, any one
    organisation (AGN-022), so the two screens share one definition."""
    figure = case((AgentCommission.status.in_(CLAIMABLE), "claimable"), (AgentCommission.status == "paid", "revenue"), (AgentCommission.status == "claimed", "claims"))
    stmt = (
        select(figure, AgentCommission.currency, func.count(), func.sum(AgentCommission.amount))
        .where(AgentCommission.agent_id.in_(member_ids), figure.is_not(None))
        .group_by(figure, AgentCommission.currency)
        .order_by(AgentCommission.currency)
    )
    summary = {"claimable": [], "claims": 0, "revenue": []}
    for name, currency, count, amount in (await db.execute(stmt)).all():
        if name == "claims":
            summary["claims"] += count
        else:
            summary[name].append({"currency": currency, "count": count, "amount": float(amount)})
    return summary


async def dashboard(db: AsyncSession, user: User) -> dict:
    """The AGN-018 payload (spec §5.3). Staff get the Master-only fields as null; they are never queried for staff."""
    staff = is_agent_staff(user)
    result = {
        "scope": "own" if staff else "agency",
        "member_code": user.agent_membership.code,  # the route's gate admits members only
        **await headline_counts(db, user),
        "by_country": await breakdown(db, user, Country.name, Country.id),
        "by_university": await breakdown(db, user, University.name, University.id),
        "staff": None,
        "unassigned_students": None,
        "commission": None,
        "reports_available": agent_may(user, "can_view_reports"),
        "as_of": datetime.now(UTC),
    }
    if not staff:
        result["staff"], result["unassigned_students"] = await staff_rows(db, user)
        result["commission"] = await commission_summary(db, user)
    return result
