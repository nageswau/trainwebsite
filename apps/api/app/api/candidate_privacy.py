"""hrc-035 (DEC-SCOPE-396 K7/K8, API §12KO): the HR Manager's candidate deletion requests and the retention rule. Every route needs
`candidates.erase` (the HR Manager by default; super_admin always); only super_admin changes the retention period. Each write is one
transaction committed here; stored files are deleted after the commit."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import candidate_privacy as privacy

router = APIRouter(prefix="/recruiter", tags=["recruiter-candidates"])


@router.get("/candidate-data-requests")
async def data_requests(state: Literal["open", "decided"] = Query("open"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await privacy.require_eraser(db, user)
    return {"items": await privacy.queue(db, state)}


@router.post("/candidate-data-requests/{request_id}/decision")
async def decide(request_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await privacy.require_eraser(db, user)
    row, keys = await privacy.decide(db, user, request_id, payload.get("decision"), payload.get("reason"))
    await db.commit()
    privacy.purge_files(keys)
    return row


@router.get("/candidate-retention")
async def retention(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await privacy.require_eraser(db, user)
    return await privacy.retention_out(db, user)


@router.put("/candidate-retention")
async def save_retention(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await privacy.save_retention(db, user, payload.get("months"))
    await db.commit()
    return await privacy.retention_out(db, user)
