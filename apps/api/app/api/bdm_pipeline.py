"""bdm-004 (DEC-SCOPE-070, spec §6.3): stage moves, Lost / Revive, stage history and the pipeline view.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, `require(can_edit)` (S1: the assigned BDM or super_admin), the pipeline rules, change + history row + audit row,
one commit here, then the log line."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.bdm_organizations import _assigned
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmOrganization, User
from app.schemas import (
    BdmLostIn,
    BdmOrganizationEnvelope,
    BdmPipelinePage,
    BdmReviveIn,
    BdmStageEventPage,
    BdmStageMove,
    BdmType,
)
from app.services import bdm_organizations as org_svc
from app.services import bdm_pipeline as svc

router = APIRouter(prefix="/bdm", tags=["bdm-pipeline"])


@router.post("/organizations/{org_id}/stage", response_model=BdmOrganizationEnvelope)
async def move_stage(org_id: UUID, payload: BdmStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S6: any manual stage; backward needs a note; a stale `from_stage` is 409 `stage_changed`."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "stage")
    backward = svc.check_move(user, org, payload)
    from_stage = org.pipeline_stage
    org.pipeline_stage = payload.to_stage
    svc.record_event(db, user, org, "move", from_stage, payload.to_stage, payload.note)
    org_svc.audit(db, user, "stage_changed", org.id, {"from": from_stage, "to": payload.to_stage, "backward": backward, "note": payload.note is not None})
    await db.commit()
    org_svc.log("bdm_org_stage_changed", user, org.id, from_stage=from_stage, to_stage=payload.to_stage, backward=backward)
    return {"organization": await org_svc.organization_out(db, user, org)}


async def _set_lost(org_id: UUID, user: User, db: AsyncSession, reason: str, lost: bool) -> dict:
    """S5: Lost is a flag with a reason on top of the stage, which is kept; revive clears it, so the organization is back at the
    stage it was lost at. One shape for both, as bdm-002's `_set_archived`."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "lost" if lost else "revive")
    already_lost = org.lost_at is not None
    if lost and already_lost:
        raise HTTPException(409, svc.LOST_CONFLICT)
    if not lost and not already_lost:
        raise HTTPException(409, svc.NOT_LOST_CONFLICT)
    org.lost_at, org.lost_reason = (datetime.now(UTC), reason) if lost else (None, None)
    kind = "lost" if lost else "revived"
    svc.record_event(db, user, org, kind, org.pipeline_stage, org.pipeline_stage, reason)
    org_svc.audit(db, user, kind, org.id, {"stage": org.pipeline_stage})
    await db.commit()
    org_svc.log(f"bdm_org_{kind}", user, org.id, stage=org.pipeline_stage)
    return {"organization": await org_svc.organization_out(db, user, org)}


@router.post("/organizations/{org_id}/lost", response_model=BdmOrganizationEnvelope)
async def mark_lost(org_id: UUID, payload: BdmLostIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_lost(org_id, user, db, payload.reason, lost=True)


@router.post("/organizations/{org_id}/revive", response_model=BdmOrganizationEnvelope)
async def revive(org_id: UUID, payload: BdmReviveIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_lost(org_id, user, db, payload.reason, lost=False)


@router.get("/organizations/{org_id}/stage-history", response_model=BdmStageEventPage)
async def stage_history(org_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readable by everyone who can read the organization (bdm, its manager, super_admin)."""
    org = await org_svc.load_scoped(db, user, org_id)
    return await svc.history_page(db, org, limit, offset)


@router.get("/pipeline", response_model=BdmPipelinePage)
async def pipeline(
    bdm_type: BdmType | None = None,
    assigned: str | None = Query(None, max_length=36),
    stage: str | None = Query(None, max_length=40),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """S7: counts per stage in the caller's read scope (bdm: module; manager: team; super_admin: all), optionally one assignee
    (`me` or a BDM id, the organization list's rule); the page lists one stage, `lost`, or every open organization."""
    filters = await org_svc.caller_scope(db, user)
    chosen = await svc.view_type(db, user, bdm_type)
    assignee = _assigned(user, assigned)
    if assignee is not None:
        filters.append(BdmOrganization.assigned_bdm_user_id == assignee)
    return await svc.pipeline_view(db, filters, chosen, stage, limit, offset)
