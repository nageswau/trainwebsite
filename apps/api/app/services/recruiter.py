"""rec-001 (DEC-SCOPE-116, spec §4): recruiter provisioning rules and the self/team scope every later rec item calls.

Functions only; nothing here commits -- the route owns the transaction. Logs carry ids and the route, never email, phone or
Employee ID. The tel-001 helpers are reused where the rule is identical (readable 422s, the phone self-edit)."""

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RecruiterProfile, User
from app.schemas import RECRUITER_FIELD_LABELS, RecruiterProfileCreate, RecruiterProfileUpdate
from app.services.telecaller import _parse

logger = logging.getLogger("app.recruiter")

ROLE = "placement_team"
MANAGER_ROLE = "placement_manager"
ADMIN_ROLES = frozenset({"super_admin", "it_admin"})  # R2: recruiters are IT; overseas_admin has no recruiter access
EMPLOYEE_ID_INDEX = "uq_recruiter_profiles_employee_id"


def require_recruiter_admin(actor: User, route: str) -> None:
    if actor.role not in ADMIN_ROLES:
        logger.warning("recruiter_admin_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route}})
        raise HTTPException(403, "Your role cannot manage recruiters")


def parse_profile_create(raw) -> RecruiterProfileCreate:
    return _parse(RecruiterProfileCreate, raw, "recruiter_profile must be an object", RECRUITER_FIELD_LABELS)


def parse_profile_update(raw) -> RecruiterProfileUpdate:
    return _parse(RecruiterProfileUpdate, raw, "recruiter_profile must be an object", RECRUITER_FIELD_LABELS)


async def locked_active_manager(db: AsyncSession, manager_id) -> User:
    """FOR SHARE: a concurrent deactivation of this manager waits for the assignment's commit (the tel-001 rule)."""
    manager = await db.scalar(select(User).where(User.id == manager_id).with_for_update(read=True))
    if not manager or not manager.active or manager.role != MANAGER_ROLE:
        raise HTTPException(422, "Reporting manager must be an active placement manager")
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


def profile_snapshot(profile: RecruiterProfile) -> dict:
    """The audit form (JSON-safe)."""
    manager = profile.reporting_manager_user_id
    return {"employee_id": profile.employee_id, "reporting_manager_user_id": str(manager) if manager else None}


def manager_ref(manager: User | None) -> dict | None:
    return {"id": manager.id, "full_name": manager.full_name, "active": manager.active} if manager else None


def profile_out(profile: RecruiterProfile, manager: User | None) -> dict:
    return {"employee_id": profile.employee_id, "reporting_manager": manager_ref(manager)}


async def create_profile(db: AsyncSession, user: User, raw) -> tuple[RecruiterProfile, User | None]:
    """A new recruiter's profile, in the caller's transaction: validated and manager-locked when the Recruiter Staff page sends one,
    empty when the generic Users form sends none (spec §3 edge case)."""
    manager = None
    values = {}
    if raw is not None:
        values = parse_profile_create(raw).model_dump()
        manager = await locked_active_manager(db, values["reporting_manager_user_id"])
    profile = RecruiterProfile(user_id=user.id, **values)
    db.add(profile)
    await flush_profile(db)
    return profile, manager


async def locked_profile(db: AsyncSession, user: User) -> RecruiterProfile:
    """The recruiter's profile locked FOR UPDATE, so concurrent edits serialise; a missing one (a row written outside the API) is created."""
    profile = await db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user.id).with_for_update())
    if profile is None:
        profile = RecruiterProfile(user_id=user.id)
        db.add(profile)
        await flush_profile(db)
    return profile


async def apply_profile_update(db: AsyncSession, profile: RecruiterProfile, raw) -> tuple[dict, dict]:
    """PATCH semantics on a locked profile: a manager is re-checked only when it changes; a duplicate Employee ID is the 409.
    Returns the audit (before, after)."""
    changes = parse_profile_update(raw).model_dump(exclude_unset=True)
    new_manager = changes.get("reporting_manager_user_id")
    if new_manager is not None and new_manager != profile.reporting_manager_user_id:
        await locked_active_manager(db, new_manager)
    before = profile_snapshot(profile)
    for key, value in changes.items():
        setattr(profile, key, value)
    await flush_profile(db)
    return before, profile_snapshot(profile)


async def recruiter_context(db: AsyncSession, user: User) -> RecruiterProfile:
    """Every recruiter route's gate: the caller is a `placement_team` user with a profile row; otherwise 403 (hr_team included, Q-28)."""
    if user.role != ROLE:
        raise HTTPException(403, "Recruiter role required")
    profile = await db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user.id))
    if not profile:
        raise HTTPException(403, "Recruiter profile not set up — contact your administrator")
    return profile


def require_manager(user: User) -> None:
    if user.role not in (MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, "Placement manager role required")


def team_filter(user: User) -> list:
    """R2: a manager's recruiters are exactly their direct reports; super_admin sees all."""
    return [] if user.role == "super_admin" else [RecruiterProfile.reporting_manager_user_id == user.id]
