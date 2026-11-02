"""itc-023 (DEC-SCOPE-352) -- at-risk thresholds (the IT Admin) and the scoped at-risk list (IT Admin, IT counselor, trainer).
API_CONTRACT.md §12IX; RBAC_MATRIX.md §2.252. Logs carry ids only."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import ItRiskThresholdIn
from app.services import it_at_risk

logger = logging.getLogger("app.it_at_risk")
admin_router = APIRouter(prefix="/admin/it/risk-thresholds", tags=["it-at-risk"])
router = APIRouter(prefix="/it/at-risk", tags=["it-at-risk"])


@admin_router.get("")
async def read_thresholds(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    it_at_risk.require_admin(user)
    return await it_at_risk.list_thresholds(db)


@admin_router.put("/{program_id}")
async def save_threshold(program_id: UUID, payload: ItRiskThresholdIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    it_at_risk.require_admin(user)
    out = await it_at_risk.save_threshold(db, user, program_id, payload)
    logger.info("it_risk_thresholds_saved", extra={"extra_fields": {"actor_id": str(user.id), "program_id": str(program_id)}})
    return out


@router.get("")
async def read_flags(student_id: UUID | None = None, history: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Open flags (and, with `history=true`, cleared ones), newest first, at most 200; `student_id` narrows to one student (the 360)."""
    return await it_at_risk.list_flags(db, user, student_id=student_id, history=history)
