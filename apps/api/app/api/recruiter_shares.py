"""rec-019 (DEC-SCOPE-159, spec §3): profile sharing -- share, the requirement's and the company's shares, the recruiter's response and
feedback, and the public resume link.

Every write is one transaction -- scope, the requirement lock, the writer (403), state, the rules, the change, audit, one commit here; then
(an email) the publish and the log line. The public route needs no session: the token is the credential (S7), and every failure is the same
404 so nothing is learned about which."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.portfolio_certificates import HEADERS
from app.core.database import get_db
from app.models import AuditLog, ProfileShare, ProfileShareItem, User
from app.notifications.dispatch import enqueue_recruiter_email
from app.schemas import RecShareCreate, RecShareItemUpdate
from app.services import applications, candidates
from app.services import profile_sharing as svc
from app.services import recruiter_companies as companies
from app.services import recruiter_requirements as requirements
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-shares"])
public_router = APIRouter(prefix="/public", tags=["public"])


@router.post("/shares", status_code=201)
async def create_share(payload: RecShareCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent, but a retry of the same candidates is the repeat 409 (S5) unless the recruiter confirms `repeat`."""
    share, url = await svc.create(db, user, payload, await db_now(db))
    await db.commit()
    if share.channel == "email":
        enqueue_recruiter_email(share.message_id)
    svc.log("profile_share_created", user, share.id, channel=share.channel, items=len(payload.candidate_ids))
    return {"share": await svc.one(db, user, share.id), "whatsapp_url": url}


@router.get("/requirements/{requirement_id}/shares")
async def requirement_shares(requirement_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The requirement's readers (rec-007 scope: the manager and the assigned BDM read)."""
    job = await requirements.load_scoped(db, user, requirement_id)
    return await svc.page(db, user, ProfileShare.job_id == job.id, limit, offset)


@router.get("/companies/{company_id}/shares")
async def company_shares(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await companies.load_scoped(db, user, company_id)
    return await svc.page(db, user, ProfileShare.company_id == company_id, limit, offset)


@router.patch("/shares/{share_id}/items/{item_id}")
async def update_share_item(share_id: UUID, item_id: UUID, payload: RecShareItemUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S9: the company's response (who and when are kept) and the recruiter's feedback. The requirement's scope decides 404 first."""
    share, _ = await svc.load_item(db, share_id, item_id)
    job = await requirements.load_scoped(db, user, share.job_id, lock=True)
    applications.require_writer(user, item_id, "update_share_item")
    if job.status in requirements.ENDED:
        raise HTTPException(409, "This requirement is closed or cancelled")
    item = await db.get(ProfileShareItem, item_id, with_for_update=True, populate_existing=True)
    changed = svc.respond(item, user, payload.response, await db_now(db))
    if "feedback" in payload.model_fields_set and payload.feedback != item.feedback:
        item.feedback = payload.feedback
        changed.append("feedback")
    if changed:
        db.add(AuditLog(user_id=user.id, action="profile_share.respond", entity_type="profile_share_item", entity_id=str(item.id), metadata_json={"fields": changed, "response": item.response}))
    await db.commit()
    if changed:
        svc.log("profile_share_item_updated", user, item.id, fields=changed)
    shared = await svc.one(db, user, share_id)
    return next(i for i in shared["items"] if i["id"] == item_id)


@public_router.get("/shared-resume/{token}")
async def shared_resume(token: str, db: AsyncSession = Depends(get_db)):
    """S7: no session; the audit row is committed before any byte leaves."""
    found = await svc.item_by_token(db, token, await db_now(db))
    data = None
    if found:
        item, candidate, resume = found
        try:
            data = candidates.read_file(resume)
        except HTTPException:
            data = None
    if data is None:
        raise HTTPException(404, svc.LINK_GONE)
    svc.download_audit(db, None, item, "link")
    await db.commit()
    svc.log("profile_share_resume_downloaded", None, item.id, via="link")
    return Response(content=data, media_type=resume.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{svc.resume_name(candidate, resume)}"'})
