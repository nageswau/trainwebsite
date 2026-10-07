"""bdm-016 (DEC-SCOPE-103, spec §5): BDM monthly targets.

A BDM reads only their own sheet (`bdm_context`). Managers read and set their team's targets (`require_manager` + `team_filter`; a BDM
outside the team is the same 404 as a missing one); super_admin all and, alone, past months (AC4). Every write is one transaction:
rules (422 / 404), change, audit, one commit here."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmProfile, User
from app.schemas import BDM_TARGET_MONTH_PATTERN, BdmTargetsCopied, BdmTargetsCopy, BdmTargetSheet, BdmTargetsPut, BdmTargetsSaved, BdmTargetTeam
from app.services import bdm_targets as svc
from app.services.bdm import bdm_context, require_manager, team_filter
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_metrics import TARGET_KPIS

router = APIRouter(prefix="/bdm", tags=["bdm-targets"])
MONTH = Query(None, pattern=BDM_TARGET_MONTH_PATTERN, description="IST month, YYYY-MM (default the current month)")


async def _current_month(db: AsyncSession):
    return india_date(await db_now(db)).replace(day=1)


@router.get("/targets", response_model=BdmTargetSheet)
async def my_targets(month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    current = await _current_month(db)
    return await svc.sheet(db, user, profile.bdm_type, svc.parse_month(month, current), current, editable=False)


@router.get("/manager/targets", response_model=BdmTargetTeam)
async def team_targets(month: str | None = MONTH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Active team BDMs with how many of their KPIs have a target this month. Three queries whatever the team size."""
    require_manager(user)
    current = await _current_month(db)
    chosen = svc.parse_month(month, current)
    members = select(User, BdmProfile).join(BdmProfile, BdmProfile.user_id == User.id).where(User.active.is_(True), *team_filter(user))
    total = await db.scalar(select(func.count()).select_from(members.subquery()))
    rows = (await db.execute(members.order_by(User.full_name, User.id).limit(limit).offset(offset))).all()
    counts = await svc.targets_set(db, [u.id for u, _ in rows], chosen) if rows else {}
    items = [{"bdm": {"id": u.id, "full_name": u.full_name}, "bdm_type": p.bdm_type, "targets_set": counts.get(u.id, 0), "kpi_count": len(TARGET_KPIS[p.bdm_type])}
             for u, p in rows]
    return {"month": svc.month_text(chosen), "month_status": svc.month_status(chosen, current), "editable": svc.edit_refusal(user, chosen, current) is None,
            "items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/manager/targets/{bdm_user_id}", response_model=BdmTargetSheet)
async def team_member_targets(bdm_user_id: UUID, month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    row = (await db.execute(select(User, BdmProfile).join(BdmProfile, BdmProfile.user_id == User.id).where(User.id == bdm_user_id, *team_filter(user)))).first()
    if row is None:
        raise HTTPException(404, svc.BDM_NOT_FOUND)
    member, profile = row
    current = await _current_month(db)
    chosen = svc.parse_month(month, current)
    editable = member.active and svc.edit_refusal(user, chosen, current) is None
    return await svc.sheet(db, member, profile.bdm_type, chosen, current, editable=editable)


@router.put("/manager/targets", response_model=BdmTargetsSaved)
async def save_targets(payload: BdmTargetsPut, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Batch upsert (a null target clears it). All or nothing: any refusal writes nothing."""
    require_manager(user)
    current = await _current_month(db)
    month = svc.parse_month(payload.month, current)
    svc.check_editable(user, month, current)
    changed = await svc.save(db, user, month, payload.items)
    await db.commit()
    svc.log("bdm_targets_saved", user, month, changed)
    return {"month": payload.month, "changed": changed}


@router.post("/manager/targets/copy", response_model=BdmTargetsCopied)
async def copy_targets(payload: BdmTargetsCopy, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """R8: fill this month's missing targets from last month's; a repeat copies nothing."""
    require_manager(user)
    current = await _current_month(db)
    month = svc.parse_month(payload.month, current)
    svc.check_editable(user, month, current)
    copied = await svc.copy_previous(db, user, month)
    await db.commit()
    svc.log("bdm_targets_copied", user, month, copied)
    return {"month": payload.month, "copied": copied}
