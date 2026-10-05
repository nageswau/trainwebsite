"""bdm-004 (DEC-SCOPE-070, spec §6.3): stage moves, Lost / Revive, stage history and the pipeline view.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, `require(can_edit)` (S1: the assigned BDM or super_admin), the pipeline rules, change + history row + audit row,
one commit here, then the log line."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmLostIn, BdmOrganizationEnvelope, BdmReviveIn, BdmStageMove
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


@router.post("/organizations/{org_id}/lost", response_model=BdmOrganizationEnvelope)
async def mark_lost(org_id: UUID, payload: BdmLostIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S5: a flag with a reason on top of the stage; the stage is kept."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "lost")
    if org.lost_at is not None:
        raise HTTPException(409, svc.LOST_CONFLICT)
    org.lost_at, org.lost_reason = datetime.now(UTC), payload.reason
    svc.record_event(db, user, org, "lost", org.pipeline_stage, org.pipeline_stage, payload.reason)
    org_svc.audit(db, user, "lost", org.id, {"stage": org.pipeline_stage})
    await db.commit()
    org_svc.log("bdm_org_lost", user, org.id, stage=org.pipeline_stage)
    return {"organization": await org_svc.organization_out(db, user, org)}


@router.post("/organizations/{org_id}/revive", response_model=BdmOrganizationEnvelope)
async def revive(org_id: UUID, payload: BdmReviveIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S5: clears the flag with a reason; the organization is back at the stage it was lost at."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "revive")
    if org.lost_at is None:
        raise HTTPException(409, svc.NOT_LOST_CONFLICT)
    org.lost_at = org.lost_reason = None
    svc.record_event(db, user, org, "revived", org.pipeline_stage, org.pipeline_stage, payload.reason)
    org_svc.audit(db, user, "revived", org.id, {"stage": org.pipeline_stage})
    await db.commit()
    org_svc.log("bdm_org_revived", user, org.id, stage=org.pipeline_stage)
    return {"organization": await org_svc.organization_out(db, user, org)}
