"""upc-008 (DEC-SCOPE-142, spec §3): a university's expected timeline (§5) and milestone tracker (§6).

Reads are open to every university reader (MS11). Every write is one transaction, as upc-003's: the university row lock (FOR UPDATE), the
scope check (`can_edit_timeline`: 403 logged; inactive 409), the change, an audit row only when something changed, one commit here, then
the structured log (ids, kind and field names only)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.partnership_universities import _locked
from app.core.database import get_db
from app.models import User
from app.schemas import MilestoneKind, UniversityEnvelope, UniversityExpectedUpdate, UniversityMilestonePage, UniversityMilestoneUpdate
from app.services import partnership_milestones as milestones
from app.services import partnership_universities as svc

router = APIRouter(prefix="/partnership/universities", tags=["partnership-milestones"])


@router.get("/{university_id}/milestones", response_model=UniversityMilestonePage)
async def list_milestones(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The 13 §6 milestones in source order with their Q-11 status (computed for today, IST)."""
    await svc.require_reader(db, user)
    uni = await svc.load(db, university_id)
    can_edit = svc.permissions(user, uni, await svc.team_of(db, user))["can_edit_timeline"]
    return await milestones.page(db, uni.id, can_edit)


@router.patch("/{university_id}/milestones/{kind}", response_model=UniversityMilestonePage)
async def update_milestone(university_id: UUID, kind: MilestoneKind, payload: UniversityMilestoneUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One milestone's target and / or achieved date (null clears); returns every milestone, since the statuses depend on each other."""
    uni, _ = await _locked(db, user, university_id, "can_edit_timeline", "milestone")
    out, metadata = await milestones.update(db, user, uni, kind, payload)
    if metadata is not None:
        svc.audit(db, user, "milestone_updated", uni.id, metadata)
    await db.commit()
    if metadata is not None:
        svc.log("university_milestone_updated", user, uni.id, kind=kind, fields=metadata["fields"])
    return out


@router.patch("/{university_id}/expected", response_model=UniversityEnvelope)
async def update_expected(university_id: UUID, payload: UniversityExpectedUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§5: the target partnership date, expected intake, agreement date and recruitment start (month and quarter are derived)."""
    uni, team = await _locked(db, user, university_id, "can_edit_timeline", "expected")
    changed = milestones.update_expected(uni, payload)
    if changed:
        svc.audit(db, user, "expected_updated", uni.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("university_expected_updated", user, uni.id, fields=changed)
    return {"university": await svc.detail_out(db, user, uni, team)}
