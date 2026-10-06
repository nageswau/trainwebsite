"""tel-001 (DEC-SCOPE-073, spec §5.3): telecaller provisioning rules and the self/team scope every later tel item calls.

Functions only; nothing here commits -- the route owns the transaction. Logs carry ids, route and team, never email, phone or
Employee ID."""

import logging

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelecallerProfile, User
from app.schemas import TELECALLER_FIELD_LABELS, TelecallerProfileCreate, TelecallerProfileUpdate, TelecallerSelfUpdate

logger = logging.getLogger("app.telecaller")

TEAMS = ("it", "overseas")
TEAM_LABEL = {"it": "IT", "overseas": "Overseas"}
CREATOR_TEAMS = {  # T21: super_admin creates both teams; a division admin only its own (only super_admin creates managers, admin.create_user)
    "super_admin": frozenset(TEAMS),
    "it_admin": frozenset({"it"}),
    "overseas_admin": frozenset({"overseas"}),
}
EMPLOYEE_ID_INDEX = "uq_telecaller_profiles_employee_id"


def creatable_teams(actor: User) -> frozenset[str]:
    return CREATOR_TEAMS.get(actor.role, frozenset())


def _cannot_manage(team: str) -> HTTPException:
    return HTTPException(403, f"Your role cannot manage {TEAM_LABEL.get(team, team)} telecallers")


def require_creator_may(actor: User, team: str, route: str) -> None:
    if team not in creatable_teams(actor):
        logger.warning("telecaller_creator_team_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route, "team": team}})
        raise _cannot_manage(team)


def _readable(error: dict, labels: dict[str, str]) -> str:
    """The admin sees a sentence naming the field, not a pydantic path (bdm-001 QA-08)."""
    field = str(error["loc"][0]) if error["loc"] else ""
    label = labels.get(field, field)
    if error["type"] == "extra_forbidden":
        return f"Unknown field: {field}"
    explicit_null = "input" in error and error["input"] is None
    if error["type"] == "missing" or (explicit_null and field in labels and field != "phone"):
        return f"{label} is required"
    if error["type"] == "value_error":
        return error["msg"].removeprefix("Value error, ")
    if error["type"] == "uuid_parsing":
        return f"{label}: choose a manager from the list"
    return f"{label}: {error['msg']}"


def _parse(model: type[BaseModel], raw, not_an_object: str, labels: dict[str, str] = TELECALLER_FIELD_LABELS):
    """The /admin/users payload is an untyped dict (existing contract), so nested objects are validated here; the first error becomes
    a readable 422. tel-002 reuses it for the catalogue bodies with its own labels."""
    if not isinstance(raw, dict):
        raise HTTPException(422, not_an_object)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(422, _readable(exc.errors()[0], labels)) from None


def parse_profile_create(raw) -> TelecallerProfileCreate:
    return _parse(TelecallerProfileCreate, raw, "Telecaller profile is required")


def parse_profile_update(raw) -> TelecallerProfileUpdate:
    return _parse(TelecallerProfileUpdate, raw, "telecaller_profile must be an object")


def parse_self_update(raw) -> TelecallerSelfUpdate:
    return _parse(TelecallerSelfUpdate, raw, "The request body must be an object")


async def locked_active_manager(db: AsyncSession, manager_id) -> User:
    """FOR SHARE: a concurrent deactivation of this manager (an UPDATE of the same row) waits for the assignment's commit, so a
    telecaller is never committed against a manager deactivated in the same instant (spec §5.8)."""
    manager = await db.scalar(select(User).where(User.id == manager_id).with_for_update(read=True))
    if not manager or not manager.active or manager.role != "telecaller_manager":
        raise HTTPException(422, "Reporting manager must be an active telecaller manager")
    return manager


async def flush_profile(db: AsyncSession) -> None:
    """The unique index decides a duplicate Employee ID (case-insensitive) even under a race; the whole transaction rolls back."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if EMPLOYEE_ID_INDEX in str(exc.orig):
            raise HTTPException(409, "Employee ID already exists") from None
        raise


def profile_snapshot(profile: TelecallerProfile) -> dict:
    """The audit form (JSON-safe)."""
    return {"team": profile.team, "employee_id": profile.employee_id, "reporting_manager_user_id": str(profile.reporting_manager_user_id)}


def person_ref(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "active": user.active}


def profile_out(profile: TelecallerProfile, manager: User) -> dict:
    return {"team": profile.team, "employee_id": profile.employee_id, "reporting_manager": person_ref(manager)}


async def apply_profile_update(db: AsyncSession, profile: TelecallerProfile, raw) -> tuple[dict, dict]:
    """PATCH semantics on a profile the caller has already locked: the team is fixed here (TL7, tel-025 moves teams); a manager is
    re-checked only when it changes; a duplicate Employee ID is the 409 from flush_profile. Returns the audit (before, after)."""
    changes = parse_profile_update(raw).model_dump(exclude_unset=True)
    if "team" in changes and changes.pop("team") != profile.team:
        raise HTTPException(422, "Team cannot be changed here")
    new_manager = changes.get("reporting_manager_user_id")
    if new_manager is not None and new_manager != profile.reporting_manager_user_id:
        await locked_active_manager(db, new_manager)
    before = profile_snapshot(profile)
    for key, value in changes.items():
        setattr(profile, key, value)
    await flush_profile(db)
    return before, profile_snapshot(profile)


async def telecaller_context(db: AsyncSession, user: User) -> TelecallerProfile:
    """Every telecaller route's gate: the caller is a `telecaller` with a profile row; otherwise 403."""
    if user.role != "telecaller":
        raise HTTPException(403, "Telecaller role required")
    profile = await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(403, "Telecaller profile not set up — contact your administrator")
    return profile


def require_manager(user: User) -> None:
    if user.role not in ("telecaller_manager", "super_admin"):
        raise HTTPException(403, "Telecaller manager role required")


def team_filter(user: User) -> list:
    """T23: a manager's telecallers are exactly their direct reports; super_admin sees all."""
    return [] if user.role == "super_admin" else [TelecallerProfile.reporting_manager_user_id == user.id]


def admin_team_filter(actor: User, team: str | None) -> list:
    allowed = creatable_teams(actor)
    if team is not None:
        if team not in allowed:
            raise _cannot_manage(team)
        return [TelecallerProfile.team == team]
    return [TelecallerProfile.team.in_(sorted(allowed))]
