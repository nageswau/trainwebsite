"""bdm-004 (DEC-SCOPE-070, spec §6.3): stage moves, Lost / Revive, stage history and the pipeline view.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, `require(can_edit)` (S1: the assigned BDM or super_admin), the pipeline rules, change + history row + audit row,
one commit here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmOrganizationEnvelope, BdmStageMove
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
