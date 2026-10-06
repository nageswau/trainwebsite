"""bdm-018 (DEC-SCOPE-079, spec §5): the school onboarding handover.

The BDM side resolves `{org_id}` through `services.bdm_organizations.load_scoped` (out of scope = 404) and writes under the organization
row lock. The admin side is Overseas Admin / super_admin only (403 otherwise) and never reads a BDM organization except through a
request. Every write is one transaction -- rows, audit and in-app notices (H7) -- committed here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.workflows import _notify_user
from app.core.database import get_db
from app.models import BdmOnboardingRequest, BdmOrganization, School, User
from app.schemas import (
    BdmOnboardingItem,
    BdmOnboardingLinkIn,
    BdmOnboardingPage,
    BdmOnboardingRejectIn,
    BdmOnboardingRequestIn,
    BdmOnboardingStatus,
    BdmOrganizationEnvelope,
)
from app.services import bdm_onboarding as svc
from app.services import bdm_organizations as org_svc

router = APIRouter(prefix="/bdm", tags=["bdm-onboarding"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["bdm-onboarding"])


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


@admin_router.get("/bdm-onboarding-requests", response_model=BdmOnboardingPage)
async def onboarding_queue(status: BdmOnboardingStatus = "pending", limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §5.2: the queue with each organization's details, which prefill the School create form."""
    svc.require_admin(user)
    return await svc.queue_page(db, status, limit, offset)


async def notify_outcome(db: AsyncSession, request: BdmOnboardingRequest, org: BdmOrganization, school: School | None) -> None:
    """H7, in the resolving transaction: the organization's assigned BDM learns the outcome."""
    title, body = svc.outcome_notice(org, request, school)
    await _notify_user(db, await db.get_one(User, org.assigned_bdm_user_id), title, body, f"/bdm/organizations/{org.id}", channels=[])


async def _item(db: AsyncSession, request: BdmOnboardingRequest) -> dict:
    return (await svc.items_out(db, [request]))[0]


@admin_router.post("/bdm-onboarding-requests/{request_id}/reject", response_model=BdmOnboardingItem)
async def reject_request(request_id: UUID, payload: BdmOnboardingRejectIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_admin(user)
    request, org = await svc.lock_pending(db, request_id)
    svc.reject(db, user, request, payload.reason)
    await notify_outcome(db, request, org, None)
    await db.commit()
    svc.log("bdm_onboarding_rejected", user, request)
    return await _item(db, request)


@admin_router.post("/bdm-onboarding-requests/{request_id}/link", response_model=BdmOnboardingItem)
async def link_school(request_id: UUID, payload: BdmOnboardingLinkIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """H3: a School onboarded before this feature (or without the request) is linked through the BDM's request."""
    svc.require_admin(user)
    request, org = await svc.lock_pending(db, request_id)
    school = await svc.school_by_code(db, payload.school_code)
    await svc.complete(db, user, request, org, school, "linked")
    await notify_outcome(db, request, org, school)
    await db.commit()
    svc.log("bdm_onboarding_linked", user, request, school_id=str(school.id))
    return await _item(db, request)
