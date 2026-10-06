"""bdm-008 (DEC-SCOPE-074, spec §6): BDM follow-ups and tasks.

Every `{task_id}` resolves through `services.bdm_tasks` scope (out of scope = 404); every write is one transaction -- scope, locks
(appointment or organization before the task), owner, state, validation, change, audit, one commit here, log. Lists carry the
counts the tabs and type chips show, computed from the same filters."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmTask, User
from app.schemas import BdmTaskBucket, BdmTaskKind, BdmTaskOrgType, BdmTaskPage
from app.services import bdm_tasks as svc
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/bdm/tasks", tags=["bdm-tasks"])


@router.get("", response_model=BdmTaskPage)
async def list_tasks(
    bucket: BdmTaskBucket = "today",
    kind: BdmTaskKind | None = None,
    org_type: BdmTaskOrgType | None = None,
    organization_id: UUID | None = None,
    bdm_user_id: UUID | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they only narrow it (bdm-006 R-A10)."""
    base = await svc.caller_filters(db, user)
    if bdm_user_id is not None:
        if user.role == "bdm":
            raise HTTPException(422, "bdm_user_id is only for managers")
        base.append(BdmTask.assignee_user_id == bdm_user_id)
    if kind:
        base.append(BdmTask.kind == kind)
    if organization_id:
        base.append(BdmTask.organization_id == organization_id)
    return await svc.page(db, user, base, bucket, org_type, today_ist(await db_now(db)), limit, offset)
