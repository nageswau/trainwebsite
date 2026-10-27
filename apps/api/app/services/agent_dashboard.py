"""AGN-018 -- the agency dashboard aggregates (DEC-SCOPE-062; spec §4-§5).

Every count is SQL over the existing scope helpers, so a Master counts the agency and a staff member only their assigned students
(G4) with no new scope logic. Read-only: nothing here writes, locks or commits.

nehn-038 (DEC-SCOPE-306) adds applications submitted, the visa outcome split and conversion, and an optional referral-date range:
the cohort of agency student records created in the range (AGN-019 P4). Work queues and commission are never date-filtered (D2)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta

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


def created_range(start: date | None, end: date | None) -> list[ColumnElement]:
    """Agency student records created within the inclusive UTC days, when given (AGN-019 P4; nehn-038 D1)."""
    where = []
    if start:
        where.append(AgentStudent.created_at >= datetime.combine(start, time.min, UTC))
    if end:
        where.append(AgentStudent.created_at < datetime.combine(end + timedelta(days=1), time.min, UTC))
    return where


def cohort_scopes(user: User, start: date | None, end: date | None) -> tuple[list[ColumnElement], list[ColumnElement]]:
    """The caller's student and application scopes, narrowed to the referral cohort when a range is given: an application counts
    when its owner (the agency record, or the linked login -- `owner_join`'s two paths) is a cohort student. No range, no change."""
    students = [*student_scope(user), *created_range(start, end)]
    apps = agency_applications(user)
    if start or end:
        records = select(AgentStudent.id).where(*students)
        logins = select(AgentStudent.student_id).where(*students, AgentStudent.student_id.is_not(None))
        apps.append(or_(OverseasApplication.agent_student_id.in_(records), OverseasApplication.student_id.in_(logins)))
    return students, apps


def converted(apps: Sequence[ColumnElement[bool]]) -> ColumnElement[bool]:
    """nehn-038 D4: the agency student has an enrolled application in scope, by either `owner_join` path -- per student, so a
    student with two enrolments converts once."""
    enrolled = [*apps, OverseasApplication.status == "enrolled"]
    return or_(
        AgentStudent.id.in_(select(OverseasApplication.agent_student_id).where(*enrolled)),
        and_(AgentStudent.student_id.is_not(None), AgentStudent.student_id.in_(select(OverseasApplication.student_id).where(*enrolled))),
    )


def rate(part: int, whole: int) -> float | None:
    """A percentage to one decimal; None when there is nothing to divide by."""
    return round(100 * part / whole, 1) if whole else None


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _visa(apps: Sequence[ColumnElement[bool]], *extra):
    """Distinct applications with a visa case -- a second case on one application is not a second visa application."""
    stmt = select(func.count(distinct(VisaCase.application_id))).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
    return stmt.where(*apps, *extra).scalar_subquery()


def funnel_columns(students: Sequence[ColumnElement[bool]], apps: Sequence[ColumnElement[bool]]) -> dict:
    """The six student-to-enrollment KPIs as scalar subqueries over the given student and application scopes. Shared by this
    dashboard and bdm-022's agent performance (DEC-SCOPE-110 B3), so an agency's own figures and the BDM's cannot disagree."""
    return {
        "students": _count(AgentStudent, *students, AgentStudent.status == "active"),
        "applications": _count(OverseasApplication, *apps, OverseasApplication.status != WITHDRAWN),
        "offers": _count(OverseasApplication, *apps, offer_clause()),
        "visa_applications": _visa(apps),
        "visa_approvals": _visa(apps, VisaCase.decision == "approved"),
        "enrollments": _count(OverseasApplication, *apps, OverseasApplication.status == "enrolled"),
    }


def visa_outcomes(apps: Sequence[ColumnElement[bool]]) -> dict:
    """nehn-038 D3: each decided application once, by its strongest decision (approved > refused > withdrawn), so approvals +
    refusals + withdrawals = decisions. Approvals stay `funnel_columns`' "any case approved", which is the same set."""
    strongest = func.max(case((VisaCase.decision == "approved", 3), (VisaCase.decision == "refused", 2), else_=1)).label("rank")
    decided = select(strongest).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id).where(*apps, VisaCase.decision.is_not(None)).group_by(VisaCase.application_id).subquery()

    def count(*where):
        return select(func.count()).select_from(decided).where(*where).scalar_subquery()

    return {"visa_decisions": count(), "visa_refusals": count(decided.c.rank == 2), "visa_withdrawals": count(decided.c.rank == 1)}


async def headline_counts(db: AsyncSession, user: User, start: date | None = None, end: date | None = None) -> dict[str, int]:
    """The headline KPIs (spec §4; nehn-038) as scalar subqueries of ONE statement, so they come from one snapshot. A range narrows
    the funnel figures to the referral cohort; pending documents and actions are work queues and stay current (D2)."""
    students, apps = cohort_scopes(user, start, end)
    columns = {
        **funnel_columns(students, apps),
        "applications_submitted": _count(OverseasApplication, *apps, OverseasApplication.submitted_on.is_not(None)),
        **visa_outcomes(apps),
        "conversions": _count(AgentStudent, *students, AgentStudent.status == "active", converted(apps)),
        "pending_documents": _count(StudentDocument, *document_scope(user), StudentDocument.verification_status == "pending", StudentDocument.archived_at.is_(None)),
        "pending_actions": pending_stmt(user).scalar_subquery(),
    }
    row = (await db.execute(select(*(column.label(key) for key, column in columns.items())))).one()
    return dict(row._mapping)


async def breakdown(db: AsyncSession, apps: Sequence[ColumnElement[bool]], label, key) -> dict:
    """Open applications in `apps` grouped by `key` (shown as `label`), the top ten (D2). The window total comes from the same
    statement, so `other` can never disagree with the items."""
    count = func.count()
    stmt = (
        select(label, count, func.sum(count).over())
        .select_from(OverseasApplication)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .where(*apps, OverseasApplication.status != WITHDRAWN)
        .group_by(key, label)
        .order_by(count.desc(), label)
        .limit(BREAKDOWN_SIZE)
    )
    rows = (await db.execute(stmt)).all()
    items = [{"label": name, "count": n} for name, n, _ in rows]
    total = int(rows[0][2]) if rows else 0
    return {"items": items, "other": total - sum(i["count"] for i in items)}


async def staff_rows(db: AsyncSession, user: User, start: date | None = None, end: date | None = None) -> tuple[list[dict], int]:
    """Master only (G2): per staff member, exactly what that member's own dashboard shows -- students by assignment (active),
    applications by `application_scope`'s two paths (the agency record, or the linked login), each application once, and
    conversions (nehn-038). Plus the agency's unassigned active students. A range narrows each to the referral cohort."""
    agency = org_member_ids(user)
    cohort = [AgentStudent.agent_id.in_(agency), *created_range(start, end)]
    by_assignee = select(AgentStudent.assigned_member_id, func.count()).where(*cohort, AgentStudent.status == "active").group_by(AgentStudent.assigned_member_id)
    students = dict((await db.execute(by_assignee)).all())
    conversions = dict((await db.execute(by_assignee.where(converted(agency_applications(user))))).all())

    def distinct_apps(condition):
        return func.count(distinct(case((condition, OverseasApplication.id))))

    per_member = (
        select(AgentStudent.assigned_member_id, distinct_apps(OverseasApplication.status != WITHDRAWN), distinct_apps(offer_clause()), distinct_apps(OverseasApplication.status == "enrolled"))
        .select_from(OverseasApplication)
        .join(AgentStudent, owner_join())
        .where(*agency_applications(user), *cohort, AgentStudent.assigned_member_id.is_not(None))
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
        count, won = students.get(member.id, 0), conversions.get(member.id, 0)
        rows.append(
            {
                "code": member.code,
                "name": name,
                "active": active,
                "students": count,
                "applications": applications,
                "offers": offers,
                "enrollments": enrollments,
                "conversions": won,
                "conversion_rate": rate(won, count),
            }
        )
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


async def dashboard(db: AsyncSession, user: User, start: date | None = None, end: date | None = None) -> dict:
    """The AGN-018 payload (spec §5.3; nehn-038). Staff get the Master-only fields as null; they are never queried for staff."""
    staff = is_agent_staff(user)
    _, apps = cohort_scopes(user, start, end)
    counts = await headline_counts(db, user, start, end)
    result = {
        "scope": "own" if staff else "agency",
        "member_code": user.agent_membership.code,  # the route's gate admits members only
        **counts,
        "conversion_rate": rate(counts["conversions"], counts["students"]),
        "date_from": start,
        "date_to": end,
        "by_country": await breakdown(db, apps, Country.name, Country.id),
        "by_university": await breakdown(db, apps, University.name, University.id),
        "staff": None,
        "unassigned_students": None,
        "commission": None,
        "reports_available": agent_may(user, "can_view_reports"),
        "as_of": datetime.now(UTC),
    }
    if not staff:
        result["staff"], result["unassigned_students"] = await staff_rows(db, user, start, end)
        result["commission"] = await commission_summary(db, user)
    return result
