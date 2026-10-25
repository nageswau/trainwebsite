"""ccrm-036 (DEC-SCOPE-269, P1-P9): the overseas counselor's own performance report. Their own figures only -- the request names no
counselor, so there is nothing to tamper with. Read-only and not audited (P9)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import CounselorPerformanceOut
from app.services import counselor_performance
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_performance import period

router = APIRouter(prefix="/counselor/performance", tags=["counselor-performance"])

FORBIDDEN = "Only an overseas counselor has a performance report"


@router.get("", response_model=CounselorPerformanceOut)
async def my_performance(from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P1: the overseas counselor only. P2: `from`..`to` inclusive IST dates, default this month (the `/management/counseling` rule)."""
    if user.role != "counselor" or user.division != "overseas":
        raise HTTPException(403, FORBIDDEN)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await counselor_performance.report(db, user, start, end, now)
