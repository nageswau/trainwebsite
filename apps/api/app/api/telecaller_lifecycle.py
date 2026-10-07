"""tel-025 (DEC-SCOPE-104, spec §2): the admin's telecaller lifecycle routes -- open-work preview, deactivate with a reassignment choice,
later handover from an inactive telecaller (LC4), team move (T22) and telecaller manager deactivation (D4). Inline authorization (backlog
convention): `ensure_admin`, then the team scope (LC1), then the write. Every refusal happens before any write; one transaction per route."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import ensure_admin
from app.api.workflows import _audit
from app.core.database import get_db
from app.models import User
from app.schemas import (
    TelecallerDeactivateOut,
    TelecallerHandoverOut,
    TelecallerManagerDeactivate,
    TelecallerManagerDeactivateOut,
    TelecallerManagerOpenWork,
    TelecallerOpenWork,
    TelecallerReassign,
    TelecallerTeamMove,
    TelecallerTeamMoveOut,
)
from app.services import telecaller_lifecycle as svc

router = APIRouter(prefix="/admin", tags=["telecaller-admin"])
ROUTE = "/admin/telecallers/{id}"


def _target_id(target: User | None) -> str | None:
    return str(target.id) if target else None


@router.get("/telecallers/{user_id}/open-work", response_model=TelecallerOpenWork)
async def open_work(user_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The deactivate / move dialog's preview: what would move (LC2)."""
    await svc.load_telecaller(db, user, user_id, ROUTE)
    return await svc.open_work(db, user_id)


@router.post("/telecallers/{user_id}/deactivate", response_model=TelecallerDeactivateOut)
async def deactivate(user_id: UUID, payload: TelecallerReassign, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """AC1/AC3: the open leads go to a telecaller of the same team or its queue, then the account is deactivated -- atomically."""
    await svc.load_telecaller(db, user, user_id, ROUTE)
    source, profile, leads = await svc.lock_source(db, user_id)
    if not source.active:
        raise HTTPException(409, "This telecaller is already inactive")
    moved = await svc.open_work(db, source.id)
    target = await svc.locked_target(db, source, profile.team, payload.target, payload.reassign_to, bool(leads))
    await svc.move_leads(db, user, leads, target, "deactivation")
    rules_removed = await svc.remove_rules(db, user, source.id)
    await svc.deactivate_user(db, source)
    target_kind = payload.target if leads else None
    await _audit(db, user, "telecaller.deactivate", "user", source.id, {
        "target": target_kind, "reassign_to": _target_id(target), "moved": moved, "rules_removed": rules_removed})
    await svc.notify_target(db, source, target, moved)
    await db.commit()
    svc.log("telecaller_deactivated", user, telecaller_id=str(source.id), target=target_kind, target_id=_target_id(target),
            rules_removed=rules_removed, **moved)
    return {"id": source.id, "active": False, "target": target_kind, "moved": moved, "rules_removed": rules_removed}


@router.post("/telecallers/{user_id}/handover", response_model=TelecallerHandoverOut)
async def handover(user_id: UUID, payload: TelecallerReassign, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """LC4: open leads still on an inactive telecaller (deactivated before tel-025, or routed to them in the deactivation instant)."""
    await svc.load_telecaller(db, user, user_id, ROUTE)
    source, profile, leads = await svc.lock_source(db, user_id)
    if source.active:
        raise HTTPException(409, "Deactivate this telecaller first")
    if not leads:
        raise HTTPException(409, "No open leads to hand over")
    moved = await svc.open_work(db, source.id)
    target = await svc.locked_target(db, source, profile.team, payload.target, payload.reassign_to, True)
    await svc.move_leads(db, user, leads, target, "handover")
    await _audit(db, user, "telecaller.handover", "user", source.id, {"target": payload.target, "reassign_to": _target_id(target), "moved": moved})
    await svc.notify_target(db, source, target, moved)
    await db.commit()
    svc.log("telecaller_handed_over", user, telecaller_id=str(source.id), target=payload.target, target_id=_target_id(target), **moved)
    return {"id": source.id, "target": payload.target, "moved": moved}


@router.post("/telecallers/{user_id}/move-team", response_model=TelecallerTeamMoveOut)
async def move_team(user_id: UUID, payload: TelecallerTeamMove, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """T22: the open leads stay in their division -- they go to a telecaller of the OLD team or its queue; then the team and division
    change (and optionally the reporting manager). The telecaller stays active and signs in again (D2)."""
    profile = await svc.load_telecaller(db, user, user_id, ROUTE)
    svc.require_new_team(user, profile, payload.team, ROUTE)
    source, profile, leads = await svc.lock_source(db, user_id)
    from_team = profile.team
    moved = await svc.open_work(db, source.id)
    target = await svc.locked_target(db, source, from_team, payload.target, payload.reassign_to, bool(leads))
    await svc.change_team(db, user, source, profile, payload.team, payload.reporting_manager_user_id)
    await svc.move_leads(db, user, leads, target, "team_move")
    rules_removed = await svc.remove_rules(db, user, source.id)
    target_kind = payload.target if leads else None
    await _audit(db, user, "telecaller.move_team", "user", source.id, {
        "from_team": from_team, "to_team": payload.team, "reporting_manager_user_id": str(profile.reporting_manager_user_id),
        "target": target_kind, "reassign_to": _target_id(target), "moved": moved, "rules_removed": rules_removed})
    await svc.notify_target(db, source, target, moved)
    await db.commit()
    svc.log("telecaller_team_moved", user, telecaller_id=str(source.id), from_team=from_team, to_team=payload.team, target=target_kind,
            target_id=_target_id(target), rules_removed=rules_removed, **moved)
    return {"id": source.id, "team": payload.team, "target": target_kind, "moved": moved, "rules_removed": rules_removed}


def _super_admin_only(user: User) -> None:
    if user.role != "super_admin":
        raise HTTPException(403, "Only a Super Administrator can deactivate a telecaller manager")


@router.get("/telecaller-managers/{manager_id}/open-work", response_model=TelecallerManagerOpenWork)
async def manager_open_work(manager_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    _super_admin_only(user)
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != "telecaller_manager":
        raise HTTPException(404, "Telecaller manager not found")
    return {"telecallers": await svc.team_size(db, manager_id)}


@router.post("/telecaller-managers/{manager_id}/deactivate", response_model=TelecallerManagerDeactivateOut)
async def deactivate_manager(manager_id: UUID, payload: TelecallerManagerDeactivate, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """D4: super_admin only (managers are created by super_admin only, T21). Every telecaller reporting to the manager -- active or not --
    moves to the replacement in the same transaction."""
    _super_admin_only(user)
    source = await svc.lock_manager(db, manager_id)
    if not source.active:
        raise HTTPException(409, "This manager is already inactive")
    moved: list[UUID] = []
    target = None
    if await svc.team_size(db, source.id) or payload.reassign_to is not None:
        target = await svc.locked_manager_target(db, source, payload.reassign_to)
        moved = await svc.move_reports(db, source, target)
    await svc.deactivate_user(db, source)
    await _audit(db, user, "telecaller_manager.deactivate", "user", source.id, {
        "reassign_to": _target_id(target), "moved_telecaller_ids": [str(i) for i in moved]})
    await db.commit()
    svc.log("telecaller_manager_deactivated", user, manager_id=str(source.id), target_id=_target_id(target), moved_telecallers=len(moved))
    return {"id": source.id, "active": False, "moved_telecallers": len(moved)}
