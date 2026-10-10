"""upc-027 (DEC-SCOPE-169, spec §3): a university's partner onboarding checklist (§29).

Reads are open to every university reader (OB11). Every write is one transaction, as upc-003's: the university row lock (FOR UPDATE), the
scope check (`can_edit_timeline`: 403 logged; inactive 409), the started / Lost checks (409), the change, the Partner Activated move when
all ten are completed (OB8), audit rows only when something changed, one commit here, then the structured logs (ids, kind, field names)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.partnership_universities import _locked
from app.core.database import get_db
from app.models import User
from app.schemas import OnboardingItemKind, UniversityOnboardingPage, UniversityOnboardingUpdate, UniversityOnboardingUpdateOut
from app.services import partnership_universities as svc
from app.services import university_onboarding as onboarding

router = APIRouter(prefix="/partnership/universities", tags=["partnership-onboarding"])


@router.get("/{university_id}/onboarding", response_model=UniversityOnboardingPage)
async def get_onboarding(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The ten §29 items in source order with their status, and the derived overall status (OB6)."""
    await svc.require_reader(db, user)
    uni = await svc.load(db, university_id)
    can_edit = svc.permissions(user, uni, await svc.team_of(db, user))["can_edit_timeline"]
    return await onboarding.page(db, uni, can_edit)


@router.patch("/{university_id}/onboarding/{kind}", response_model=UniversityOnboardingUpdateOut)
async def update_onboarding_item(university_id: UUID, kind: OnboardingItemKind, payload: UniversityOnboardingUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One item's status, owner, due date and / or note (null clears); returns the whole checklist, since the overall status depends on
    every item, and whether this write moved the university to Partner Activated."""
    uni, _ = await _locked(db, user, university_id, "can_edit_timeline", "onboarding")
    metadata = await onboarding.update(db, user, uni, kind, payload)
    advanced = False
    if metadata is not None:
        svc.audit(db, user, "onboarding_item_updated", uni.id, metadata)
        advanced = await onboarding.activate_if_complete(db, user, uni)
    await db.commit()
    if metadata is not None:
        svc.log("university_onboarding_item_updated", user, uni.id, kind=kind, fields=metadata["fields"])
    if advanced:
        svc.log("university_onboarding_completed", user, uni.id)
    return {**await onboarding.page(db, uni, True), "stage_advanced": advanced}
