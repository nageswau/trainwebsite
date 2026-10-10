"""upc-007 (DEC-SCOPE-126, spec §3): stage moves, Lost / Reopen, stage history and the Kanban board. upc-020: a move creates the new
stage's Q-22 auto-task in the same transaction.

Every write is one transaction, as upc-003's: the university row lock (FOR UPDATE), the scope check (`can_move_stage` / `can_reopen`: 403
logged; inactive 409), the pipeline rules (services.partnership_pipeline, the single writer), change + history row + audit row, one commit
here, then the structured log."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.partnership_universities import _locked
from app.core.database import get_db
from app.models import User
from app.schemas import UniversityEnvelope, UniversityPipelinePage, UniversityStageEventPage, UniversityStageMove, UniversityStageReason
from app.services import partnership_pipeline as pipeline
from app.services import partnership_tasks as tasks
from app.services import partnership_universities as svc

router = APIRouter(prefix="/partnership", tags=["partnership-pipeline"])


@router.post("/universities/{university_id}/stage", response_model=UniversityEnvelope)
async def move_stage(university_id: UUID, payload: UniversityStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PS4: any stage; backward needs a note; a stale `from_stage` is 409 `stage_changed` (logged as a conflict)."""
    uni, team = await _locked(db, user, university_id, "can_move_stage", "stage")
    from_stage = uni.stage
    try:
        backward = pipeline.move(db, user, uni, payload)
    except HTTPException as e:
        if isinstance(e.detail, dict) and e.detail.get("code") == "stage_changed":
            svc.log("university_stage_conflict", user, uni.id, current_stage=uni.stage, to_stage=payload.to_stage)
        raise
    await tasks.on_stage_entered(db, user, uni)  # upc-020 Q-22: the new stage's auto-task, in this transaction
    svc.audit(db, user, "stage_changed", uni.id, {"from": from_stage, "to": payload.to_stage, "backward": backward, "note": payload.note is not None})
    await db.commit()
    svc.log("university_stage_changed", user, uni.id, from_stage=from_stage, to_stage=payload.to_stage, backward=backward)
    return {"university": await svc.detail_out(db, user, uni, team)}


async def _set_lost(university_id: UUID, user: User, db: AsyncSession, reason: str, lost: bool) -> dict:
    uni, team = await _locked(db, user, university_id, "can_move_stage" if lost else "can_reopen", "lost" if lost else "reopen")
    kind = pipeline.set_lost(db, user, uni, reason, lost)
    svc.audit(db, user, kind, uni.id, {"stage": uni.stage})
    await db.commit()
    svc.log(f"university_{kind}", user, uni.id, stage=uni.stage)
    return {"university": await svc.detail_out(db, user, uni, team)}


@router.post("/universities/{university_id}/lost", response_model=UniversityEnvelope)
async def mark_lost(university_id: UUID, payload: UniversityStageReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3: Lost/Closed needs a reason; the stage is kept."""
    return await _set_lost(university_id, user, db, payload.reason, lost=True)


@router.post("/universities/{university_id}/reopen", response_model=UniversityEnvelope)
async def reopen(university_id: UUID, payload: UniversityStageReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PS6: the head (or super_admin) reopens; the university is back at the stage it was lost at."""
    return await _set_lost(university_id, user, db, payload.reason, lost=False)


@router.get("/universities/{university_id}/stage-history", response_model=UniversityStageEventPage)
async def stage_history(university_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readable by every role that reads the university (PS9); newest first."""
    await svc.require_reader(db, user)
    uni = await svc.load(db, university_id)
    return await pipeline.history_page(db, uni.id, limit, offset)


@router.get("/pipeline", response_model=UniversityPipelinePage)
async def board(
    column: str | None = Query(None, max_length=40),
    manager: str | None = Query(None, max_length=36),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PS11/PS12: counts per Kanban column over every active university the filters keep (each read role reads every row, UM9),
    optionally one manager (`me`, `none` or an id, the list's rule); the page lists one column, `lost`, or every open university."""
    await svc.require_reader(db, user)
    return await pipeline.board(db, svc.manager_filter(user, manager), column, limit, offset)
