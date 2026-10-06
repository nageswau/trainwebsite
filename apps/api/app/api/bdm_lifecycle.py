"""bdm-025 (DEC-SCOPE-076, spec §5): the admin's BDM lifecycle routes -- portfolio preview, deactivate with a handover choice,
later handover from an inactive BDM, and BDM manager deactivation. Inline authorization (backlog convention): `ensure_admin`, then
the creator-type scope, then the write. Every refusal happens before any write; one transaction per route."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import ensure_admin
from app.core.database import get_db
from app.models import User
from app.schemas import BdmDeactivate, BdmDeactivateOut, BdmHandover, BdmHandoverOut, BdmPortfolio
from app.services import bdm_lifecycle as svc

router = APIRouter(prefix="/admin", tags=["bdm-admin"])


@router.get("/bdms/{bdm_id}/portfolio", response_model=BdmPortfolio)
async def portfolio(bdm_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The deactivate dialog's preview: what would move, and how many not-started trips would be cancelled (§5.1)."""
    await svc.load_bdm(db, user, bdm_id)
    return await svc.portfolio_counts(db, bdm_id)


@router.post("/bdms/{bdm_id}/deactivate", response_model=BdmDeactivateOut)
async def deactivate(bdm_id: UUID, payload: BdmDeactivate, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """AC1/AC2/AC5: hand the open portfolio to another BDM of the same module (or keep it, L3), cancel not-started trips (L2), then
    deactivate -- atomically."""
    _, profile = await svc.load_bdm(db, user, bdm_id)
    source = await svc.lock_source(db, bdm_id)
    if not source.active:
        raise HTTPException(409, "This BDM is already inactive")
    moved = dict.fromkeys(svc.PORTFOLIO, 0)
    target = None
    if payload.mode == "reassign":
        target = await svc.locked_target(db, source, profile, payload.reassign_to)
        moved = await svc.move_portfolio(db, user, source, target, "bdm_deactivated")
    trips_cancelled = await svc.cancel_trips(db, user, source)
    await svc.deactivate_user(db, source)
    svc.audit(db, user, "bdm.deactivate", "user", source.id, {
        "mode": payload.mode, "reassign_to": str(target.id) if target else None, "moved": moved, "trips_cancelled": trips_cancelled})
    if target is not None:
        await svc.notify_handover(db, source, target, moved)
    await db.commit()
    svc.log("bdm_deactivated", user, bdm_id=str(source.id), mode=payload.mode, target_id=str(target.id) if target else None,
            trips_cancelled=trips_cancelled, **moved)
    return {"id": source.id, "active": False, "mode": payload.mode, "moved": moved, "trips_cancelled": trips_cancelled}


@router.post("/bdms/{bdm_id}/handover", response_model=BdmHandoverOut)
async def handover(bdm_id: UUID, payload: BdmHandover, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """L3: an inactive BDM's work that was kept (mode=leave), or that landed on them in the deactivation instant (§5.9), moves to an
    active BDM of the same module. Trips are not touched: deactivation already cancelled the not-started ones."""
    _, profile = await svc.load_bdm(db, user, bdm_id)
    source = await svc.lock_source(db, bdm_id)
    if source.active:
        raise HTTPException(409, "Deactivate this BDM first")
    target = await svc.locked_target(db, source, profile, payload.reassign_to)
    moved = await svc.move_portfolio(db, user, source, target, "portfolio_handover")
    if not any(moved.values()):
        raise HTTPException(409, "No open work to hand over")
    svc.audit(db, user, "bdm.portfolio_handover", "user", source.id, {"reassign_to": str(target.id), "moved": moved})
    await svc.notify_handover(db, source, target, moved)
    await db.commit()
    svc.log("bdm_portfolio_handed_over", user, bdm_id=str(source.id), target_id=str(target.id), **moved)
    return {"id": source.id, "moved": moved}
