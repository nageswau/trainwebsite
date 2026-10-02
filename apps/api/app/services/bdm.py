"""bdm-001 (DEC-SCOPE-052, spec §5.3): BDM provisioning rules and the type/own/team scope every later bdm item calls.

Functions only; nothing here commits -- the route owns the transaction. Logs carry ids, route and type, never email, phone or
Employee ID."""

import logging

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BdmProfile, User
from app.schemas import BdmProfileCreate, BdmProfileUpdate

logger = logging.getLogger("app.bdm")

BDM_TYPES = ("agent", "school", "college")
BDM_DIVISION = {"college": "it", "agent": "overseas", "school": "overseas"}  # D3
CREATOR_TYPES = {  # D10 (Q-01): who may create/edit which BDM type; only super_admin creates bdm_manager (admin.create_user)
    "super_admin": frozenset(BDM_TYPES),
    "it_admin": frozenset({"college"}),
    "overseas_admin": frozenset({"agent", "school"}),
}
EMPLOYEE_ID_INDEX = "uq_bdm_profiles_employee_id"
PROFILE_FIELDS = ("bdm_type", "employee_id", "designation", "department", "territory")


def creatable_types(actor: User) -> frozenset[str]:
    return CREATOR_TYPES.get(actor.role, frozenset())


def require_creator_may(actor: User, bdm_type: str, route: str) -> None:
    if bdm_type not in creatable_types(actor):
        logger.warning("bdm_creator_type_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route, "bdm_type": bdm_type}})
        raise HTTPException(403, f"Your role cannot manage {bdm_type} BDMs")


def _parse(model: type[BaseModel], raw, not_an_object: str):
    """The /admin/users payload is an untyped dict (existing contract), so the nested profile is validated here; the first error
    becomes a 422 that names the field."""
    if not isinstance(raw, dict):
        raise HTTPException(422, not_an_object)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        field = ".".join(str(part) for part in error["loc"])
        raise HTTPException(422, f"bdm_profile.{field}: {error['msg']}" if field else f"bdm_profile: {error['msg']}") from None


def parse_profile_create(raw) -> BdmProfileCreate:
    return _parse(BdmProfileCreate, raw, "BDM profile is required")


def parse_profile_update(raw) -> BdmProfileUpdate:
    return _parse(BdmProfileUpdate, raw, "bdm_profile must be an object")


async def locked_active_manager(db: AsyncSession, manager_id) -> User:
    """FOR UPDATE: a concurrent deactivation of this manager (an UPDATE of the same row) is serialised with the assignment, so a
    BDM is never committed against a manager deactivated in the same instant (spec §5.8)."""
    manager = await db.scalar(select(User).where(User.id == manager_id).with_for_update())
    if not manager or not manager.active or manager.role != "bdm_manager":
        raise HTTPException(422, "Reporting manager must be an active BDM manager")
    return manager


async def flush_profile(db: AsyncSession) -> None:
    """The unique index decides a duplicate Employee ID (case-insensitive) even under a race; the whole transaction rolls back,
    as `provisioning.flush_unique_email` does for a duplicate email."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if EMPLOYEE_ID_INDEX in str(exc.orig):
            raise HTTPException(409, "Employee ID already exists") from None
        raise


def profile_snapshot(profile: BdmProfile) -> dict:
    """The audit form (JSON-safe): every profile field plus the manager id as a string."""
    return {**{k: getattr(profile, k) for k in PROFILE_FIELDS}, "reporting_manager_user_id": str(profile.reporting_manager_user_id)}


def profile_out(profile: BdmProfile, manager: User) -> dict:
    return {
        **{k: getattr(profile, k) for k in PROFILE_FIELDS},
        "reporting_manager": {"id": manager.id, "full_name": manager.full_name, "active": manager.active},
    }


async def bdm_context(db: AsyncSession, user: User) -> BdmProfile:
    """Every BDM route's gate: the caller is a `bdm` with a profile row; otherwise 403."""
    if user.role != "bdm":
        raise HTTPException(403, "BDM role required")
    profile = await db.scalar(select(BdmProfile).where(BdmProfile.user_id == user.id))
    if not profile:
        raise HTTPException(403, "BDM profile not set up — contact your administrator")
    return profile


def require_manager(user: User) -> None:
    if user.role not in ("bdm_manager", "super_admin"):
        raise HTTPException(403, "BDM manager role required")


def team_filter(user: User) -> list:
    """Team scope (D4): a manager's BDMs are exactly those reporting to them; super_admin sees all."""
    return [] if user.role == "super_admin" else [BdmProfile.reporting_manager_user_id == user.id]


def admin_type_filter(actor: User, bdm_type: str | None) -> list:
    allowed = creatable_types(actor)
    if bdm_type is not None:
        if bdm_type not in allowed:
            raise HTTPException(403, f"Your role cannot manage {bdm_type} BDMs")
        return [BdmProfile.bdm_type == bdm_type]
    return [BdmProfile.bdm_type.in_(sorted(allowed))]
