"""bdm-005 (DEC-SCOPE-074, spec §6.3): an organization's MoU, its document and history, and the MoU lists.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404). Every write is one transaction --
scope, organization row lock, `writable` (the assigned BDM or super_admin; archived / Lost 409), the current MoU row lock, the rules,
change + history row + audit row, one commit here, then the log line (spec §6.4-§6.6)."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.core.database import get_db
from app.models import BdmMou, User
from app.api.bdm import LIMIT, OFFSET
from app.schemas import BdmMouCreate, BdmMouEnvelope, BdmMouEventPage, BdmMouPage, BdmMouStatus, BdmMouUpdate, BdmOrgMouOut, BdmType
from app.services import bdm_mous as svc
from app.services import bdm_organizations as org_svc
from app.services.agent_documents import read_upload

router = APIRouter(prefix="/bdm", tags=["bdm-mous"])


@router.get("/organizations/{org_id}/mou", response_model=BdmOrgMouOut)
async def get_mou(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await org_svc.load_scoped(db, user, org_id)
    return await svc.org_mou_out(db, user, org)


@router.post("/organizations/{org_id}/mou", status_code=201, response_model=BdmMouEnvelope)
async def create_mou(org_id: UUID, payload: BdmMouCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A first MoU, or a renewal once the current one reads Expired or Rejected (M6): the old row stops being current and keeps its
    history. 409 `mou_exists` while a current one is in progress; the partial unique index is the backstop under the lock."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    svc.writable(user, org, "mou_create")
    on = svc.today()
    current = await svc.load_current(db, org, lock=True)
    previous = svc.effective_status(current, on) if current else None
    if current is not None and previous not in svc.RENEWABLE:
        raise HTTPException(409, svc.MOU_EXISTS)
    state = payload.model_dump()
    svc.apply_defaults(state, on)
    svc.check_rules(state)
    if current is not None:
        current.is_current = False
        await db.flush()  # the index allows the new current row only after this
    mou = BdmMou(organization_id=org.id, created_by_user_id=user.id, **state)
    db.add(mou)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, svc.MOU_EXISTS) from None
    if current is not None:
        svc.record(db, user, current, "renewed", previous, previous, [])
        svc.audit(db, user, "renewed", current, {"renewed_by": str(mou.id)})
    svc.record(db, user, mou, "created", None, mou.status, [])
    svc.audit(db, user, "created", mou, {"status": mou.status})
    advanced = svc.advance_on_sign(db, user, org) if mou.status == "signed" else None
    await db.commit()
    await db.refresh(mou)
    svc.log("bdm_mou_created", user, mou, status=mou.status, renewed=current is not None)
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
    await db.refresh(mou)
    svc.log(f"bdm_mou_{action}", user, mou, from_status=before, to_status=after, changed=changed)
    svc.log_advance(user, org, advanced)
    return {"mou": await svc.mou_out(db, user, org, mou, on)}


@router.put("/organizations/{org_id}/mou/document", response_model=BdmMouEnvelope)
async def upload_document(org_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """M4 / M8 (spec §6.5): scope and role first, then the bytes (type by content, size cap, metadata stripped) before any lock, then
    the locked write. The new object is deleted when anything after storing it fails; a replaced object is kept (its key is in the
    event row, never returned)."""
    svc.writable(user, await org_svc.load_scoped(db, user, org_id), "mou_document")
    data, content_type, name = await read_upload(file)
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    svc.writable(user, org, "mou_document")
    mou = await svc.load_current(db, org, lock=True)
    if mou is None:
        raise HTTPException(404, svc.NO_MOU)
    wait = await svc.upload_wait(db, user)
    if wait:
        svc.log("bdm_mou_throttled", user, mou, wait_seconds=wait)
        raise HTTPException(429, svc.THROTTLED, headers={"Retry-After": str(wait)})
    on = svc.today()
    old_key = mou.document_key
    key = svc.store(data, content_type)
    try:
        mou.document_key, mou.document_content_type, mou.document_name, mou.document_uploaded_at = key, content_type, name, svc.now()
        status = svc.effective_status(mou, on)
        svc.record(db, user, mou, "document", status, status, ["document"], document_key=old_key)
        svc.audit(db, user, "document_uploaded", mou, {"content_type": content_type, "replaced": old_key is not None, "bytes": len(data)})
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    await db.refresh(mou)
    svc.log("bdm_mou_document_uploaded", user, mou, content_type=content_type, replaced=old_key is not None, bytes=len(data))
    return {"mou": await svc.mou_out(db, user, org, mou, on)}


@router.get("/mous", response_model=BdmMouPage)
async def list_mous(
    status: BdmMouStatus | None = None,
    bdm_type: BdmType | None = None,
    organization: UUID | None = None,
    current: bool = True,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Scoped as the organizations (a BDM: their type; a manager: their team; super_admin: all). `status` filters on the derived
    status, so `expired` lists Signed / Active MoUs past their date. `current=false` lists previous MoUs (renewed ones)."""
    return await svc.list_page(db, user, on=svc.today(), status=status, bdm_type=bdm_type, organization=organization, current=current, limit=limit, offset=offset)


@router.get("/mous/{mou_id}/history", response_model=BdmMouEventPage)
async def mou_history(mou_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mou, _ = await svc.load_scoped_mou(db, user, mou_id)
    return await svc.history_page(db, mou, limit, offset)


@router.get("/mous/{mou_id}/document")
async def download_document(mou_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """M3 / AC4: in the organization's read scope only (404 otherwise, as an unknown id). The audit row is committed before any byte
    leaves (a failed commit serves nothing); the file name is built from the organization code, never the uploaded name."""
    mou, org = await svc.load_scoped_mou(db, user, mou_id)
    data = svc.read_document(mou)
    media_type = mou.document_content_type or "application/octet-stream"
    filename = f"mou-{org.code}.{EXTENSION.get(media_type, 'bin')}"
    svc.audit(db, user, "document_downloaded", mou, {"role": user.role})
    await db.commit()
    svc.log("bdm_mou_document_downloaded", user, mou, role=user.role)
    return Response(content=data, media_type=media_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
