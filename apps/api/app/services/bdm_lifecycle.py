"""bdm-025 (DEC-SCOPE-076, spec §5): BDM deactivation, portfolio handover and BDM manager deactivation.

Functions only; nothing here commits -- the route owns the transaction. Lock order everywhere: the source's open organizations,
then the source user (FOR UPDATE), then the target (FOR SHARE) -- the same organization-before-user order as bdm-002's reassign,
so the two cannot deadlock. Logs and audit metadata carry ids and counts, never names, emails or task text."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workflows import _notify_user
from app.models import (
    BDM_APPOINTMENT_OPEN,
    AuditLog,
    BdmAppointment,
    BdmAssignmentHistory,
    BdmOrganization,
    BdmProfile,
    BdmTask,
    BdmTrip,
    User,
)
from app.services import bdm_travel as travel
from app.services.bdm import require_creator_may
from app.services.provisioning import revoke_welcome_tokens

logger = logging.getLogger("app.bdm")

BDM_TARGET_INVALID = "Choose an active BDM of the same module"
MANAGER_TARGET_INVALID = "Choose another active BDM manager"
TRIP_CANCEL_REASON = "BDM deactivated"

# L5: the open portfolio -- (history entity, model, owner column, extra filters). Everything else stays with the original BDM.
PORTFOLIO = {
    "organizations": ("organization", BdmOrganization, BdmOrganization.assigned_bdm_user_id, lambda: [BdmOrganization.archived_at.is_(None)]),
    "appointments": ("appointment", BdmAppointment, BdmAppointment.bdm_user_id,
                     lambda: [BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at > func.now()]),
    "tasks": ("task", BdmTask, BdmTask.assignee_user_id, lambda: [BdmTask.status == "open"]),
}


def _not_started_trips(user_id: UUID) -> list:
    """L2: any trip not yet started (draft, submitted, approved or rejected, still `planned`) is cancelled on deactivation."""
    return [BdmTrip.bdm_user_id == user_id, BdmTrip.travel_status == "planned"]


async def portfolio_counts(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    counts = {}
    for key, (_, model, owner, filters) in PORTFOLIO.items():
        counts[key] = await db.scalar(select(func.count()).select_from(model).where(owner == user_id, *filters())) or 0
    counts["trips"] = await db.scalar(select(func.count()).select_from(BdmTrip).where(*_not_started_trips(user_id))) or 0
    return counts


async def load_bdm(db: AsyncSession, actor: User, bdm_id: UUID) -> tuple[User, BdmProfile]:
    """404 unless a BDM with a profile; then 403 unless the actor manages that type (Q-01, `require_creator_may`)."""
    bdm = await db.get(User, bdm_id)
    profile = await db.scalar(select(BdmProfile).where(BdmProfile.user_id == bdm_id)) if bdm is not None and bdm.role == "bdm" else None
    if profile is None:
        raise HTTPException(404, "BDM not found")
    require_creator_may(actor, profile.bdm_type, "/admin/bdms/{id}")
    return bdm, profile


async def lock_source(db: AsyncSession, user_id: UUID) -> User:
    """The source's open organizations FOR UPDATE, then the user row FOR UPDATE, re-read so state checks see committed values."""
    await db.execute(select(BdmOrganization.id).where(BdmOrganization.assigned_bdm_user_id == user_id, BdmOrganization.archived_at.is_(None)).with_for_update())
    return await db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))


async def locked_target(db: AsyncSession, source: User, profile: BdmProfile, target_id: UUID) -> User:
    """An active `bdm` of the same type, not the source. FOR SHARE: a deactivation of the target in the same instant waits for this
    commit. One message for every invalid target, so the route can't be used to probe users."""
    target = None if target_id == source.id else await db.scalar(select(User).where(User.id == target_id).with_for_update(read=True))
    target_type = await db.scalar(select(BdmProfile.bdm_type).where(BdmProfile.user_id == target_id)) if target is not None else None
    if target is None or not target.active or target.role != "bdm" or target_type != profile.bdm_type:
        raise HTTPException(422, BDM_TARGET_INVALID)
    return target


async def move_portfolio(db: AsyncSession, actor: User, source: User, target: User, reason: str) -> dict[str, int]:
    """One bulk UPDATE per entity plus one history row per moved item (AC2). Returns the moved counts."""
    moved = {}
    for key, (entity, model, owner, filters) in PORTFOLIO.items():
        stmt = update(model).where(owner == source.id, *filters()).values({owner.key: target.id}).returning(model.id)
        ids = (await db.execute(stmt.execution_options(synchronize_session=False))).scalars().all()
        db.add_all(BdmAssignmentHistory(entity_type=entity, entity_id=i, from_user_id=source.id, to_user_id=target.id, actor_user_id=actor.id,
                                        reason=reason) for i in ids)
        moved[key] = len(ids)
    return moved


async def cancel_trips(db: AsyncSession, actor: User, source: User) -> int:
    trips = (await db.scalars(select(BdmTrip).where(*_not_started_trips(source.id)).with_for_update())).all()
    for trip in trips:
        before = [trip.approval_status, trip.travel_status]
        trip.travel_status, trip.cancelled_at = "cancelled", travel.now()
        travel.audit(db, actor, "cancel", trip, before=before, after=[trip.approval_status, trip.travel_status], reason=TRIP_CANCEL_REASON)
    return len(trips)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


async def notify_handover(db: AsyncSession, source: User, target: User, moved: dict[str, int]) -> None:
    """In-app + email (ENH-014 queue, sent after commit) when anything moved."""
    if not any(moved.values()):
        return
    summary = (f"{_plural(moved['organizations'], 'organization', 'organizations')}, "
               f"{_plural(moved['appointments'], 'appointment', 'appointments')} and "
               f"{_plural(moved['tasks'], 'follow-up/task', 'follow-ups/tasks')}")
    await _notify_user(db, target, "Work handed over to you", f"{summary} from {source.full_name} are now yours.", "/bdm/organizations")


async def deactivate_user(db: AsyncSession, user: User) -> None:
    """The existing lifecycle effects of `admin.update_user` (ENH-003: open welcome links are revoked on any change of `active`)."""
    user.active = False
    await revoke_welcome_tokens(db, user.id)


def audit(db: AsyncSession, actor: User, action: str, entity_type: str, entity_id: UUID, metadata: dict) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


def log(event: str, actor: User, **fields) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), **fields}})
