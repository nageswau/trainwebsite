"""AGN-018 -- the agency dashboard aggregates (DEC-SCOPE-060; spec §4-§5).

Every count is SQL over the existing scope helpers, so a Master counts the agency and a staff member only their assigned students
(G4) with no new scope logic. Read-only: nothing here writes, locks or commits."""

from sqlalchemy import ColumnElement, or_

from app.models import OverseasApplication
from app.services.agent_applications import OFFER_COUNTED_STATUSES
from app.services.agent_students import application_scope


def offer_clause() -> ColumnElement[bool]:
    """O5 (DEC-SCOPE-056) in SQL -- `counts_as_offer`'s twin (a parity test pins them): the stage reached `offer` (legacy values
    included) or an offer is recorded, so an application withdrawn after its offer still counts."""
    return or_(OverseasApplication.status.in_(OFFER_COUNTED_STATUSES), OverseasApplication.offer_type.is_not(None))


def agency_applications(user) -> list[ColumnElement]:
    """The applications the caller may see, School-bridged rows left out exactly as `with_owner` leaves them out (A12)."""
    return [*application_scope(user), OverseasApplication.school_student_id.is_(None)]
