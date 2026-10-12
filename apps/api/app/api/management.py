"""mgmt-001: the Management Command Center's own routes. Every later mgmt item adds its routes here or beside it, each asking
`services/management_access` for its tier first (M13)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas import ManagementActivityOut, ManagementMeOut, ManagementSnapshotOut
from app.services import management_audit, management_metrics
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.management_access import can_view_operational, require_management, tiers

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/me", response_model=ManagementMeOut)
async def management_me(user: User = Depends(get_current_user)):
    """The caller and the tiers they may see: partner (all), accountant (finance), super_admin (operational); anyone else 403."""
    require_management(user)
    return {"id": user.id, "full_name": user.full_name, "role": user.role, "tiers": tiers(user)}


@router.get("/activity", response_model=ManagementActivityOut)
async def management_activity(
    actor: UUID | None = None,
    kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-002 (MA5-MA7): who did what in management, newest first, limited to the kinds the caller's tier may see. Read-only."""
    require_management(user)
    if kind and kind not in management_audit.KINDS:
        raise HTTPException(422, "Unknown activity kind")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    return await management_audit.activity(db, user, actor_id=actor, kind=kind, date_from=date_from, date_to=date_to, limit=limit, offset=offset)


@router.get("/snapshot", response_model=ManagementSnapshotOut)
async def management_snapshot(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-003 (§3, spec MS1-MS19): S1-S15 for the operational tier (partner, super_admin); the accountant and everyone else 403."""
    require_management(user)
    if not can_view_operational(user):
        raise HTTPException(403, "Operational access required")
    today = india_date(await db_now(db))
    figures = await management_metrics.snapshot(db, today)
    return {"as_of": today, "kpis": [{"id": kpi_id, "key": key, "label": label, "value": figures[key]} for kpi_id, key, label in management_metrics.SNAPSHOT]}
