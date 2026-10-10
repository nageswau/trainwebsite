"""upc-015 (DEC-SCOPE-162 AL12, spec §2): the §32 "Alerts" list -- the caller's own partnership alerts (recipients only), newest first.
The beat raises them (services/partnership_alerts); read state is the shared `PATCH /workflows/notifications/{id}/read` (AL13)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import PartnershipAlertKind, PartnershipAlertPage
from app.services import partnership_alerts as alerts
from app.services.partnership import partnership_context

router = APIRouter(prefix="/partnership", tags=["partnership-alerts"])
READERS = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # super_admin receives none: an empty list


@router.get("/alerts", response_model=PartnershipAlertPage)
async def list_alerts(
    kind: Literal["all"] | PartnershipAlertKind = "all",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in READERS:
        raise HTTPException(403, "Partnership alerts are for partnership managers and heads")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)
    return await alerts.page(db, user, kind, limit, offset)
