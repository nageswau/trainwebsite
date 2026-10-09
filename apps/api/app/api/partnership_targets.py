"""upc-021 (DEC-SCOPE-144, spec §4): monthly partnership targets vs actual (EVID-020 §21).

Checks run role → scope → write (the partnership convention): a role with no access is a 403, a manager outside the caller's scope a 404.
A manager reads only their own figures; a head reads and sets their direct reports'; super_admin all and, alone, past months (TG3). The
write is one transaction: rules (422 / 404), change, audit, one commit here."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm_targets import _current_month
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BDM_TARGET_MONTH_PATTERN, BdmTargetsSaved, PartnershipTargetSheet, PartnershipTargetsPut, PartnershipTargetTeam
from app.services import partnership_targets as svc
from app.services.bdm_targets import check_editable, parse_month

router = APIRouter(prefix="/partnership", tags=["partnership-targets"])
MONTH = Query(None, pattern=BDM_TARGET_MONTH_PATTERN, description="IST month, YYYY-MM (default the current month)")


@router.get("/targets", response_model=PartnershipTargetTeam)
async def team_targets(month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Target vs actual per manager in scope and for the team (TG12). Constant query count whatever the team size."""
    await svc.require_reader(db, user)
    current = await _current_month(db)
    return await svc.team(db, user, parse_month(month, current), current)


@router.get("/targets/{manager_user_id}", response_model=PartnershipTargetSheet)
async def manager_targets(manager_user_id: UUID, month: str | None = MONTH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_reader(db, user)
    manager = await svc.manager_in_scope(db, user, manager_user_id)
    current = await _current_month(db)
    return await svc.sheet(db, user, manager, parse_month(month, current), current)


@router.put("/targets", response_model=BdmTargetsSaved)
async def save_targets(payload: PartnershipTargetsPut, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Batch upsert (a null target clears it). All or nothing: any refusal writes nothing."""
    svc.require_setter(user)
    current = await _current_month(db)
    month = parse_month(payload.month, current)
    check_editable(user, month, current)
    changed = await svc.save(db, user, month, payload.items)
    await db.commit()
    svc.log("partnership_targets_saved", user, month, changed)
    return {"month": payload.month, "changed": changed}
