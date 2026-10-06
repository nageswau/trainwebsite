"""bdm-018 (DEC-SCOPE-079, spec §5): the school onboarding handover.

The BDM side resolves `{org_id}` through `services.bdm_organizations.load_scoped` (out of scope = 404) and writes under the organization
row lock. The admin side is Overseas Admin / super_admin only (403 otherwise) and never reads a BDM organization except through a
request. Every write is one transaction -- rows, audit and in-app notices (H7) -- committed here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import _notify_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmOnboardingRequestIn, BdmOrganizationEnvelope
from app.services import bdm_onboarding as svc
from app.services import bdm_organizations as org_svc

router = APIRouter(prefix="/bdm", tags=["bdm-onboarding"])


@router.post("/organizations/{org_id}/onboarding-request", status_code=201, response_model=BdmOrganizationEnvelope)
async def request_onboarding(org_id: UUID, payload: BdmOnboardingRequestIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1 / H5-H6: the assigned BDM or super_admin, a School organization whose MoU reads Signed or Active, no link, none pending."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "onboarding_request")
    await svc.check_request(db, org)
    request = await svc.add_request(db, user, org, payload.note)
    for admin in await svc.overseas_admins(db):
        await _notify_user(db, admin, "School onboarding requested", f"{org.code} · {org.name} is ready for onboarding.", svc.ADMIN_URL, channels=[])
    await db.commit()
    svc.log("bdm_onboarding_requested", user, request)
    return {"organization": await org_svc.organization_out(db, user, org)}
