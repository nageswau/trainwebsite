"""mgmt-001: the Management Command Center's own routes. Every later mgmt item adds its routes here or beside it, each asking
`services/management_access` for its tier first (M13)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import INVESTMENT_STATUSES, INVESTMENT_VERTICALS, User
from app.schemas import (
    InvestmentCreate,
    InvestmentOut,
    InvestmentPageOut,
    InvestmentUpdate,
    ManagementActivityOut,
    ManagementMeOut,
    ManagementSnapshotOut,
)
from app.services import investments, management_audit, management_metrics
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.management_access import can_view_operational, require_management, require_partner_only, tiers

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


def _partner(user: User) -> User:
    """mgmt-014 (MI12, M13): partner-only. The accountant and super_admin get "Only partners can open this"; anyone else 403 too."""
    return require_partner_only(require_management(user))


@router.get("/investments", response_model=InvestmentPageOut)
async def list_investments(
    date_from: date | None = None,
    date_to: date | None = None,
    vertical: str | None = None,
    status: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-014 (§23, MI8/MI9): the register, newest first, with totals over every match (cancelled excluded) and the investor choices."""
    _partner(user)
    if vertical and vertical not in INVESTMENT_VERTICALS:
        raise HTTPException(422, "Unknown vertical")
    if status and status not in INVESTMENT_STATUSES:
        raise HTTPException(422, "Unknown status")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    return await investments.page(db, date_from=date_from, date_to=date_to, vertical=vertical, status=status, limit=limit, offset=offset)


@router.post("/investments", response_model=InvestmentOut, status_code=201)
async def create_investment(body: InvestmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-014 (MI1-MI6, MI11): records an investment and its audit entry together."""
    _partner(user)
    return await investments.one(db, await investments.create(db, user, body))


@router.get("/investments/{investment_id}", response_model=InvestmentOut)
async def get_investment(investment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _partner(user)
    return await investments.one(db, await investments.get(db, investment_id))


@router.patch("/investments/{investment_id}", response_model=InvestmentOut)
async def update_investment(investment_id: UUID, body: InvestmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-014 (MI10/MI11): changes only the fields sent; a change is audited with before and after values."""
    _partner(user)
    return await investments.one(db, await investments.update(db, user, investment_id, body))
