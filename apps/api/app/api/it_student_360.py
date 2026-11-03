"""itc-029 (DEC-SCOPE-358) -- the IT student 360 on /it/students/{id}/360 (the scope and the section allow-list are the caller's role,
services/it_student_360). API_CONTRACT.md §12JD; RBAC_MATRIX.md §2.258. Read only, never cached (AC1)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import it_student_360 as svc

router = APIRouter(prefix="/it/students", tags=["it-student-360"])


@router.get("/{student_id}/360")
async def student_360(student_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    response.headers.update(NO_STORE)
    return await svc.read(db, user, student_id)


@router.get("/{student_id}/360/lead-timeline")
async def student_lead_timeline(
    student_id: UUID, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):  # fmt: skip
    response.headers.update(NO_STORE)
    return await svc.lead_timeline_page(db, user, student_id, limit, offset)
