"""bdm-021 (DEC-SCOPE-086, spec §4): a College organization's student funnel and revenue. Read-only.

Scope is `load_scoped`'s (an organization the caller can't read is the same 404 as a missing one); an organization of another module
has no business view and is that same 404 (B1). Revenue is null unless the caller may see it (B3)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmBusinessOut
from app.services import bdm_metrics as svc
from app.services import bdm_organizations as org_svc

router = APIRouter(prefix="/bdm/organizations", tags=["bdm-metrics"])


@router.get("/{org_id}/business", response_model=BdmBusinessOut)
async def organization_business(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await org_svc.load_scoped(db, user, org_id)
    if org.bdm_type != "college":
        raise HTTPException(404, org_svc.NOT_FOUND)
    return await svc.college_business(db, org, svc.show_revenue(user, org))
