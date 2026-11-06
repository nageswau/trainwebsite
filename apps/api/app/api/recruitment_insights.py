"""hrc-034 (DEC-SCOPE-416): the three report pages' data. `reports.recruitment_insights.view` opens every route; the service only reads."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import require_permission
from app.core.database import get_db
from app.models import User
from app.services import recruitment_insights as svc
from app.services.permissions import user_has_grant

router = APIRouter(prefix="/recruiter/recruitment-insights", tags=["recruitment-insights"])
READER = require_permission("reports.recruitment_insights", "view", "You cannot read the recruitment insights")


@router.get("/skill-demand")
async def skill_demand(sort: Literal["demand", "supply"] = "demand", limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(READER), db: AsyncSession = Depends(get_db)):
    return await svc.skill_demand(db, sort=sort, limit=limit, offset=offset)


@router.get("/skill-demand/vacancies")
async def thin_vacancies(n: int = Query(5, ge=1, le=100), limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(READER), db: AsyncSession = Depends(get_db)):
    return await svc.thin_vacancies(db, n=n, limit=limit, offset=offset)


@router.get("/portal-analytics")
async def portal_analytics(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"), user: User = Depends(READER), db: AsyncSession = Depends(get_db)):
    return await svc.portal_analytics(db, date_from=date_from, date_to=date_to)


@router.get("/data-quality")
async def data_quality(user: User = Depends(READER), db: AsyncSession = Depends(get_db)):
    async def holds(resource: str, action: str) -> bool:
        return await user_has_grant(db, user, resource, action)

    return await svc.data_quality(db, holds)


@router.get("/data-quality/{figure}")
async def data_quality_rows(figure: str, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(READER), db: AsyncSession = Depends(get_db)):
    return await svc.drill(db, figure, limit, offset)
