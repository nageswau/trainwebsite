"""rec-005 (DEC-SCOPE-126, spec §4): company stage moves, Lost / reopen, stage history and the pipeline board.

Every `{company_id}` resolves through `recruiter_companies.load_scoped` (out of scope = 404); every write locks the row, changes it through
`services.company_pipeline`, audits and commits here, in one transaction. Audits carry stage keys and flags, never the reason text."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import RecBoardOut, RecCompanyEnvelope, RecStageEventPage, RecStageMove, RecStageReason
from app.services import company_pipeline as svc
from app.services import recruiter_companies as companies

router = APIRouter(prefix="/recruiter", tags=["recruiter-pipeline"])


@router.post("/companies/{company_id}/stage", response_model=RecCompanyEnvelope)
async def move_stage(company_id: UUID, payload: RecStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1/AC2: a manual stage only; back needs a reason; a stale `from_stage` is 409 `stage_changed`."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    from_stage = company.stage
    backward = await svc.person_move(db, user, company, payload.from_stage, payload.to_stage, payload.reason)
    companies.audit(db, user, "stage_changed", company.id, {"from": from_stage, "to": company.stage, "backward": backward, "reason": payload.reason is not None})
    await db.commit()
    return {"company": await companies.company_out(db, user, company)}


@router.post("/companies/{company_id}/lost", response_model=RecCompanyEnvelope)
async def mark_lost(company_id: UUID, payload: RecStageReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: Lost needs a reason; the stage is kept."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    await svc.mark_lost(db, user, company, payload.reason)
    companies.audit(db, user, "lost", company.id, {"stage": company.stage})
    await db.commit()
    return {"company": await companies.company_out(db, user, company)}


@router.post("/companies/{company_id}/reopen", response_model=RecCompanyEnvelope)
async def reopen(company_id: UUID, payload: RecStageReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P5: a placement manager (or super_admin) reopens a Lost company at the stage it was lost at."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    await svc.reopen(db, user, company, payload.reason)
    companies.audit(db, user, "reopened", company.id, {"stage": company.stage})
    await db.commit()
    return {"company": await companies.company_out(db, user, company)}


@router.get("/companies/{company_id}/stage-history", response_model=RecStageEventPage)
async def stage_history(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    company = await companies.load_scoped(db, user, company_id)
    return await svc.history_page(db, company, limit, offset)


@router.get("/pipeline", response_model=RecBoardOut)
async def pipeline_board(
    stage: str | None = Query(None, max_length=40),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """P7: counts per stage in the caller's company scope; the page lists one stage, `lost`, or every open company."""
    return await svc.board(db, await companies.caller_scope(db, user), stage, limit, offset)
