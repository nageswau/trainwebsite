"""pob-014 (DEC-SCOPE-425, spec docs/superpowers/specs/2026-11-07-pob-014-institution-student-pool-design.md): institution data
permissions -- who may see an institution's students, for what, and until when.

A candidate with `institution_permission_id` is in the pool only for a user listed on that permission while it is active (S2/S3/S6). With
no viewer the predicate fails closed. Expiry is evaluated in each query against today in IST, so nothing has to run when a permission
lapses. Functions only; nothing here commits. Imports models only (services/candidates imports this module)."""

from uuid import UUID

from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models import Candidate, InstitutionDataPermission, InstitutionDataPermissionUser

P, PU = InstitutionDataPermission, InstitutionDataPermissionUser
IST = "Asia/Kolkata"
RESTRICTED_NAME = "Restricted record"


def today():
    return cast(func.timezone(IST, func.now()), Date)


def active(permission=P) -> ColumnElement:
    """S2: not revoked and today (IST) within [valid_from, expires_on]."""
    return and_(permission.revoked_at.is_(None), permission.valid_from <= today(), permission.expires_on >= today())


def status(permission=P) -> ColumnElement:
    """The permission's state as one SQL expression: revoked, scheduled (not yet valid), expired or active."""
    return case(
        (permission.revoked_at.is_not(None), "revoked"),
        (permission.valid_from > today(), "scheduled"),
        (permission.expires_on < today(), "expired"),
        else_="active",
    )


def usable_by(viewer_id: UUID):
    """The ids of the active permissions the viewer is listed on."""
    return select(P.id).join(PU, PU.permission_id == P.id).where(PU.user_id == viewer_id, active())


def visible(viewer_id: UUID | None, candidate=Candidate) -> ColumnElement:
    """S6: an ordinary candidate, or an institution student the viewer may see now. No viewer = institution students hidden."""
    ordinary = candidate.institution_permission_id.is_(None)
    if viewer_id is None:
        return ordinary
    return or_(ordinary, candidate.institution_permission_id.in_(usable_by(viewer_id)))
