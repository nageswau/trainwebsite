"""upc-001 (DEC-SCOPE-116, spec §5): partnership manager provisioning rules and the self/team gates later upc items call.

Functions only; nothing here commits -- the route owns the transaction. Logs carry ids and route, never email, phone or Employee ID.
The university scope (`scope(user)`) arrives with upc-003, which adds the owner columns it filters on."""

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PartnershipProfile, User
from app.schemas import PARTNERSHIP_FIELD_LABELS, PartnershipProfileCreate, PartnershipProfileUpdate
from app.services.telecaller import _parse, person_ref

logger = logging.getLogger("app.partnership")

# PU7: a manager's division is overseas, so its admins are super_admin and overseas_admin. Only super_admin creates heads
# (admin.create_user); the admin reads use the same pair.
CREATOR_ROLES = frozenset({"super_admin", "overseas_admin"})
EMPLOYEE_ID_INDEX = "uq_partnership_profiles_employee_id"


def require_creator_may(actor: User, route: str) -> None:
    if actor.role not in CREATOR_ROLES:
        logger.warning("partnership_creator_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route}})
        raise HTTPException(403, "Your role cannot manage partnership managers")


def parse_profile_create(raw) -> PartnershipProfileCreate:
    return _parse(PartnershipProfileCreate, raw, "Partnership profile is required", PARTNERSHIP_FIELD_LABELS, "head")


def parse_profile_update(raw) -> PartnershipProfileUpdate:
    return _parse(PartnershipProfileUpdate, raw, "partnership_profile must be an object", PARTNERSHIP_FIELD_LABELS, "head")


async def locked_active_head(db: AsyncSession, head_id) -> User:
    """FOR SHARE: a concurrent deactivation of this head (an UPDATE of the same row) waits for the assignment's commit, so a manager is
    never committed against a head deactivated in the same instant."""
    head = await db.scalar(select(User).where(User.id == head_id).with_for_update(read=True))
    if not head or not head.active or head.role != "partnership_head":
        raise HTTPException(422, "Reporting head must be an active partnership head")
    return head


async def flush_profile(db: AsyncSession) -> None:
    """The unique index decides a duplicate Employee ID (case-insensitive) even under a race; the whole transaction rolls back."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if EMPLOYEE_ID_INDEX in str(exc.orig):
            raise HTTPException(409, "Employee ID already exists") from None
        raise


def profile_snapshot(profile: PartnershipProfile) -> dict:
    """The audit form (JSON-safe)."""
    return {"employee_id": profile.employee_id, "reporting_head_user_id": str(profile.reporting_head_user_id)}


def profile_out(profile: PartnershipProfile, head: User) -> dict:
    return {"employee_id": profile.employee_id, "reporting_head": person_ref(head)}


async def apply_profile_update(db: AsyncSession, profile: PartnershipProfile, raw) -> tuple[dict, dict]:
    """PATCH semantics on a profile the caller has already locked: a head is re-checked only when it changes, so a manager whose head
    has since been deactivated stays editable (upc-032 reassigns); a duplicate Employee ID is the 409. Returns the audit (before, after)."""
    changes = parse_profile_update(raw).model_dump(exclude_unset=True)
    new_head = changes.get("reporting_head_user_id")
    if new_head is not None and new_head != profile.reporting_head_user_id:
        await locked_active_head(db, new_head)
    before = profile_snapshot(profile)
    for key, value in changes.items():
        setattr(profile, key, value)
    await flush_profile(db)
    return before, profile_snapshot(profile)


async def partnership_context(db: AsyncSession, user: User) -> PartnershipProfile:
    """Every partnership-manager route's gate: the caller is a `partnership_manager` with a profile row; otherwise 403."""
    if user.role != "partnership_manager":
        raise HTTPException(403, "Partnership manager role required")
    profile = await db.get(PartnershipProfile, user.id)
    if not profile:
        raise HTTPException(403, "Partnership profile not set up — contact your administrator")
    return profile


def require_head(user: User) -> None:
    if user.role not in ("partnership_head", "super_admin"):
        raise HTTPException(403, "Partnership head role required")


def team_filter(user: User) -> list:
    """U3: a head's managers are exactly their direct reports; super_admin sees all."""
    return [] if user.role == "super_admin" else [PartnershipProfile.reporting_head_user_id == user.id]
