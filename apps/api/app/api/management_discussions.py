"""mgmt-027 (spec MD1-MD14): management discussions & decisions. `router` is the operational tier's (partner, super_admin; M13);
`me_router` is the responsible person's slice, the decision line only (MD8/MD14). Every write locks its row, adds a management audit
row and commits once here; a log line follows the commit (ids only)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.models import DISCUSSION_STATUSES, ManagementDiscussion, ManagementDiscussionAttachment, User
from app.schemas import (
    DiscussionCreate,
    DiscussionDetail,
    DiscussionOptions,
    DiscussionPage,
    DiscussionUpdate,
    MyDecisionOut,
    MyDecisionPage,
    MyDecisionStatusIn,
)
from app.services import management_audit
from app.services import management_discussions as svc
from app.services.agent_documents import read_upload

router = APIRouter(prefix="/management/discussions", tags=["management-discussions"])
me_router = APIRouter(prefix="/me/management-decisions", tags=["management-discussions"])


def _file(discussion: ManagementDiscussion, attachment: ManagementDiscussionAttachment) -> Response:
    data = svc.read(attachment)
    name = svc.download_name(discussion, attachment, EXTENSION.get(attachment.content_type, "bin"))
    return Response(content=data, media_type=attachment.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{name}"'})


@router.get("", response_model=DiscussionPage)
async def list_discussions(
    status: Literal[DISCUSSION_STATUSES] | None = None,  # type: ignore[valid-type]
    responsible: UUID | None = None,
    pending: bool = False,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MD12: newest discussion first; `pending=true` is the Pending decisions panel (by deadline)."""
    svc.require_operational(user)
    return await svc.page(db, status=status, responsible=responsible, pending=pending, limit=limit, offset=offset)


@router.get("/options", response_model=DiscussionOptions)
async def discussion_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The form's people: active staff users (MD6)."""
    svc.require_operational(user)
    return await svc.options(db)


@router.post("", status_code=201, response_model=DiscussionDetail)
async def create_discussion(payload: DiscussionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_operational(user)
    state = payload.model_dump(exclude={"participant_ids"})
    await svc.check(db, state, payload.participant_ids)
    discussion = ManagementDiscussion(**state, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(discussion)
    await db.flush()
    await svc.set_participants(db, discussion, payload.participant_ids)
    fields = [f for f in svc.FIELDS if state[f] is not None] + (["participants"] if payload.participant_ids else [])
    management_audit.record(db, user, "mgmt.decision", "create", str(discussion.id), fields=fields)
    await svc.notify_after_write(db, user, discussion, fields, None)
    await db.commit()
    svc.log("discussion_created", user, discussion.id, responsible=discussion.responsible_user_id is not None)
    return await svc.detail(db, discussion)


@router.get("/{discussion_id}", response_model=DiscussionDetail)
async def get_discussion(discussion_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_operational(user)
    return await svc.detail(db, await svc.load(db, discussion_id))


@router.patch("/{discussion_id}", response_model=DiscussionDetail)
async def change_discussion(discussion_id: UUID, payload: DiscussionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A partial change; nothing changed = nothing recorded. The responsible person hears about a new assignment or a changed line."""
    svc.require_operational(user)
    discussion = await svc.load(db, discussion_id, lock=True)
    sent = payload.model_dump(exclude_unset=True)
    members = sent.pop("participant_ids", None)
    before = {f: getattr(discussion, f) for f in svc.FIELDS}
    state = {**before, **sent}
    await svc.check(db, state, members, before["responsible_user_id"])
    changed = [f for f in svc.FIELDS if state[f] != before[f]]
    if members is not None and set(members) != set(await svc.participant_ids(db, discussion.id)):
        changed.append("participants")
    if not changed:
        return await svc.detail(db, discussion)
    for field in changed:
        if field != "participants":
            setattr(discussion, field, state[field])
    if "participants" in changed:
        await svc.set_participants(db, discussion, members)
    discussion.updated_by_user_id = user.id
    svc.audit(db, user, discussion, changed, before["status"])
    await svc.notify_after_write(db, user, discussion, changed, before["responsible_user_id"])
    await db.commit()
    svc.log("discussion_changed", user, discussion.id, changed=changed)
    return await svc.detail(db, discussion)


# --- attachments (MD10) --------------------------------------------------------------------------------------------------------
@router.post("/{discussion_id}/attachments", status_code=201, response_model=DiscussionDetail)
async def add_attachment(discussion_id: UUID, file: UploadFile = File(...), shareable: bool = Form(False), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Role first, then the bytes (type by content, size cap, metadata stripped), then the locked write. The stored object is deleted
    when anything after storing it fails."""
    svc.require_operational(user)
    data, content_type, name = await read_upload(file)
    discussion = await svc.load(db, discussion_id, lock=True)
    if await svc.attachment_count(db, discussion.id) >= svc.MAX_ATTACHMENTS:
        raise HTTPException(409, svc.TOO_MANY)
    key = svc.store(data, content_type)
    try:
        attachment = ManagementDiscussionAttachment(discussion_id=discussion.id, storage_key=key, content_type=content_type, name=name, shareable=shareable, uploaded_by_user_id=user.id)
        db.add(attachment)
        discussion.updated_by_user_id = user.id
        management_audit.record(db, user, "mgmt.decision", "update", str(discussion.id), fields=["attachments"])
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("discussion_attachment_added", user, discussion.id, content_type=content_type, shareable=shareable, bytes=len(data))
    return await svc.detail(db, discussion)


@router.get("/{discussion_id}/attachments/{attachment_id}")
async def download_attachment(discussion_id: UUID, attachment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The audit row is committed before any byte leaves."""
    svc.require_operational(user)
    discussion = await svc.load(db, discussion_id)
    attachment = await svc.load_attachment(db, discussion.id, attachment_id)
    response = _file(discussion, attachment)
    management_audit.record(db, user, "mgmt.decision", "download", str(discussion.id), fields=["attachments"])
    await db.commit()
    svc.log("discussion_attachment_downloaded", user, discussion.id)
    return response


@router.delete("/{discussion_id}/attachments/{attachment_id}", status_code=204)
async def remove_attachment(discussion_id: UUID, attachment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The stored object is deleted only after the row's removal commits."""
    svc.require_operational(user)
    discussion = await svc.load(db, discussion_id, lock=True)
    attachment = await svc.load_attachment(db, discussion.id, attachment_id)
    key = attachment.storage_key
    await db.delete(attachment)
    discussion.updated_by_user_id = user.id
    management_audit.record(db, user, "mgmt.decision", "update", str(discussion.id), fields=["attachments"])
    await db.commit()
    svc.discard(key)
    svc.log("discussion_attachment_removed", user, discussion.id)
    return Response(status_code=204)


# --- the responsible person's slice (MD8) -----------------------------------------------------------------------------------
@me_router.get("", response_model=MyDecisionPage)
async def my_decisions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"items": await svc.my_decisions(db, user)}


@me_router.patch("/{discussion_id}", response_model=MyDecisionOut)
async def update_my_decision(discussion_id: UUID, payload: MyDecisionStatusIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussion = await svc.load_mine(db, user, discussion_id, lock=True)
    if discussion.status == "cancelled":
        raise HTTPException(409, svc.CANCELLED)
    if discussion.status != payload.status:
        previous = discussion.status
        discussion.status, discussion.updated_by_user_id = payload.status, user.id
        svc.audit(db, user, discussion, ["status"], previous)
        await db.commit()
        svc.log("decision_status_changed", user, discussion.id, from_status=previous, to_status=payload.status)
    return await svc.my_decision(db, discussion)


@me_router.get("/{discussion_id}/attachments/{attachment_id}")
async def download_my_attachment(discussion_id: UUID, attachment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Shareable attachments of the caller's own decision only; anything else is a 404."""
    discussion = await svc.load_mine(db, user, discussion_id)
    if discussion.status == "cancelled":
        raise HTTPException(404, svc.ATTACHMENT_NOT_FOUND)
    attachment = await svc.load_attachment(db, discussion.id, attachment_id, shareable_only=True)
    response = _file(discussion, attachment)
    management_audit.record(db, user, "mgmt.decision", "download", str(discussion.id), fields=["attachments"])
    await db.commit()
    svc.log("decision_attachment_downloaded", user, discussion.id)
    return response
