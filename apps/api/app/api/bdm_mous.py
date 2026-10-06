"""bdm-005 (DEC-SCOPE-074, spec §6.3): an organization's MoU, its document and history, and the MoU lists.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404). Every write is one transaction --
scope, organization row lock, `writable` (the assigned BDM or super_admin; archived / Lost 409), the current MoU row lock, the rules,
change + history row + audit row, one commit here, then the log line (spec §6.4-§6.6)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmMou, User
from app.schemas import BdmMouCreate, BdmMouEnvelope, BdmMouUpdate, BdmOrgMouOut
from app.services import bdm_mous as svc
from app.services import bdm_organizations as org_svc

router = APIRouter(prefix="/bdm", tags=["bdm-mous"])


@router.get("/organizations/{org_id}/mou", response_model=BdmOrgMouOut)
async def get_mou(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await org_svc.load_scoped(db, user, org_id)
    return await svc.org_mou_out(db, user, org)


@router.post("/organizations/{org_id}/mou", status_code=201, response_model=BdmMouEnvelope)
async def create_mou(org_id: UUID, payload: BdmMouCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A first MoU (M6). 409 `mou_exists` while a current one is in progress."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    svc.writable(user, org, "mou_create")
    on = svc.today()
    current = await svc.load_current(db, org, lock=True)
    if current is not None:
        raise HTTPException(409, svc.MOU_EXISTS)
    state = payload.model_dump()
    svc.apply_defaults(state, on)
    svc.check_rules(state)
    mou = BdmMou(organization_id=org.id, created_by_user_id=user.id, **state)
    db.add(mou)
    await db.flush()
    svc.record(db, user, mou, "created", None, mou.status, [])
    svc.audit(db, user, "created", mou, {"status": mou.status})
    advanced = svc.advance_on_sign(db, user, org) if mou.status == "signed" else None
    await db.commit()
    await db.refresh(org)
    await db.refresh(mou)
    svc.log("bdm_mou_created", user, mou, status=mou.status)
    svc.log_advance(user, org, advanced)
    return {"mou": await svc.mou_out(db, user, org, mou, on)}


@router.patch("/organizations/{org_id}/mou", response_model=BdmMouEnvelope)
async def change_mou(org_id: UUID, payload: BdmMouUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Dates, reference, notes and an optional status change (spec §6.4 step 5). Nothing changed = nothing recorded."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    svc.writable(user, org, "mou_change")
    on = svc.today()
    mou = await svc.load_current(db, org, lock=True)
    if mou is None:
        raise HTTPException(404, svc.NO_MOU)
    sent = payload.model_dump(exclude_unset=True)
    status, from_status = sent.pop("status", None), sent.pop("from_status", None)
    before = svc.effective_status(mou, on)
    if status is not None:
        if from_status != before:
            raise svc.stale_status(before)
        if before == "expired":
            raise HTTPException(409, svc.MOU_EXPIRED)
        if status == before:
            raise svc._invalid("status", svc.SAME_STATUS, status)
    state = {**svc.stored_state(mou), **sent, **({"status": status} if status else {})}
    if status is not None:
        svc.apply_defaults(state, on)
    svc.check_rules(state)
    changed = [f for f in svc.FIELDS if state[f] != getattr(mou, f)] + (["status"] if status else [])
    if not changed:
        return {"mou": await svc.mou_out(db, user, org, mou, on)}
    for field in svc.FIELDS:
        setattr(mou, field, state[field])
    if status is not None:
        mou.status, mou.status_changed_at = status, svc.now()
    after = svc.effective_status(mou, on)
    kind, action = ("status", "status_changed") if status else ("updated", "updated")
    svc.record(db, user, mou, kind, before, after, changed)
    svc.audit(db, user, action, mou, {"from": before, "to": after, "changed": changed})
    advanced = svc.advance_on_sign(db, user, org) if status == "signed" else None
    await db.commit()
    await db.refresh(org)
    await db.refresh(mou)
    svc.log(f"bdm_mou_{action}", user, mou, from_status=before, to_status=after, changed=changed)
    svc.log_advance(user, org, advanced)
    return {"mou": await svc.mou_out(db, user, org, mou, on)}
