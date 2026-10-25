"""ccrm-032 (DEC-SCOPE-277; API §12GD): GET /counselor/dashboard -- the overseas counselor's action dashboard, their own work only (the
request names nobody, so there is nothing to tamper with). Anyone else 403. Read-only and not audited (D1)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import counselor_dashboard
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/counselor", tags=["counselor-dashboard"])

FORBIDDEN = "Only an overseas counselor has an action dashboard"


@router.get("/dashboard")
async def my_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "counselor" or user.division != "overseas":  # D1: an IT counselor works leads only (tel-017)
        raise HTTPException(403, FORBIDDEN)
    return await counselor_dashboard.dashboard(db, user, await db_now(db))
