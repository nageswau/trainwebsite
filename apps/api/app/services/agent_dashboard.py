"""AGN-018 -- the agency dashboard aggregates (DEC-SCOPE-060; spec §4-§5).

Every count is SQL over the existing scope helpers, so a Master counts the agency and a staff member only their assigned students
(G4) with no new scope logic. Read-only: nothing here writes, locks or commits."""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import agent_may, is_agent_staff
from app.models import AgentStudent, OverseasApplication, StudentDocument, User, VisaCase
from app.services.agent_applications import OFFER_COUNTED_STATUSES, WITHDRAWN
from app.services.agent_documents import document_scope
from app.services.agent_students import application_scope, student_scope
from app.services.agent_tasks import pending_stmt


def offer_clause() -> ColumnElement[bool]:
    """O5 (DEC-SCOPE-056) in SQL -- `counts_as_offer`'s twin (a parity test pins them): the stage reached `offer` (legacy values
    included) or an offer is recorded, so an application withdrawn after its offer still counts."""
    return or_(OverseasApplication.status.in_(OFFER_COUNTED_STATUSES), OverseasApplication.offer_type.is_not(None))


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
    return {key: int(value or 0) for key, value in row._mapping.items()}


async def dashboard(db: AsyncSession, user: User) -> dict:
    """The AGN-018 payload (spec §5.3)."""
    staff = is_agent_staff(user)
    return {
        "scope": "own" if staff else "agency",
        "member_code": user.agent_membership.code if user.agent_membership else None,
        **await headline_counts(db, user),
        "by_country": {"items": [], "other": 0},
        "by_university": {"items": [], "other": 0},
        "staff": None,
        "unassigned_students": None,
        "commission": None,
        "reports_available": agent_may(user, "can_view_reports"),
        "as_of": datetime.now(UTC),
    }
