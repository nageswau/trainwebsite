"""pob-024 (DEC-SCOPE-432): the placement closure record -- list, read, confirmations / PO owner, and the invoice draft's issue or discard.
Mounted under rec-022's `/recruiter` router (recruiter_offers.py). Scope first (other roles 403, out of scope 404), then the role/grant
(403), the row lock and state (409), validation (422), the write and its audit, one commit here, then the log line."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.client_ip import client_ip
from app.core.database import get_db
from app.models import User
from app.schemas import PlacementInvoiceIssue, PlacementSurveyAnswer, PlacementUpdate, RecInvoiceCancel
from app.services import placement_surveys as surveys
from app.services import placements as svc
from app.services.bdm_appointments import db_now

router = APIRouter(tags=["recruiter-placements"])
public_router = APIRouter(prefix="/public/placement-surveys", tags=["public"])  # pob-026: no session; the signed link is the credential


@router.get("/placements")
async def list_placements(
    view: Literal["pending", "joined", "did_not_join", "invoice_drafts"] = "pending",
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_page(db, user, view, limit, offset)


@router.get("/placements/{placement_id}")
async def get_placement(placement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement, offer = await svc.load(db, user, placement_id)
    return {"placement": await svc.out(db, user, placement, offer)}


@router.patch("/placements/{placement_id}")
async def update_placement(placement_id: UUID, payload: PlacementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement, offer = await svc.load(db, user, placement_id, lock=True)
    changed = await svc.update(db, user, placement, offer, payload)
    await db.commit()
    if changed:
        svc.log("placement_updated", user, placement_id, fields=changed)
    placement, offer = await svc.load(db, user, placement_id)
    return {"placement": await svc.out(db, user, placement, offer)}


@router.post("/placements/{placement_id}/invoice-draft/issue", status_code=201)
async def issue_invoice_draft(placement_id: UUID, payload: PlacementInvoiceIssue, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P10 (AC3): one rec-031 invoice; a retry is the 409 (no draft left)."""
    placement, _offer = await svc.load(db, user, placement_id, lock=True)
    invoice = await svc.issue(db, user, placement, payload)
    await db.commit()
    svc.log("placement_invoice_issued", user, placement_id, invoice_id=invoice.id)
    placement, offer = await svc.load(db, user, placement_id)
    return {"placement": await svc.out(db, user, placement, offer)}


@router.post("/placements/{placement_id}/invoice-draft/cancel")
async def discard_invoice_draft(placement_id: UUID, payload: RecInvoiceCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement, _offer = await svc.load(db, user, placement_id, lock=True)
    await svc.discard(db, user, placement, payload.reason)
    await db.commit()
    svc.log("placement_invoice_discarded", user, placement_id)
    placement, offer = await svc.load(db, user, placement_id)
    return {"placement": await svc.out(db, user, placement, offer)}


# --- pob-026 (DEC-SCOPE-435 S8/S9): the no-login satisfaction survey -------------------------------------------------------------------
async def _survey(request: Request, db: AsyncSession, token: str, *, lock: bool = False):
    """429 while this IP has too many refused lookups; a refused lookup (404/410) is recorded, committed, then raised."""
    ip = client_ip(request)
    wait = await surveys.wait_seconds(db, ip)
    if wait:
        raise HTTPException(429, surveys.THROTTLED, headers={"Retry-After": str(wait)})
    try:
        return await surveys.from_token(db, token, lock=lock)
    except HTTPException as refused:
        await db.rollback()
        surveys.refused(db, ip, refused.status_code)
        await db.commit()
        raise


@public_router.get("/{token}")
async def survey_form(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    return await surveys.public_out(db, await _survey(request, db, token))


@public_router.post("/{token}", status_code=201)
async def answer_survey(token: str, payload: PlacementSurveyAnswer, request: Request, db: AsyncSession = Depends(get_db)):
    """One response: the row is locked and answered only while empty, so a second POST (or a race) is 410."""
    survey = await _survey(request, db, token, lock=True)
    surveys.respond(db, survey, payload.rating, payload.comment, await db_now(db))
    await db.commit()
    surveys.logger.info("placement_survey_responded", extra={"extra_fields": {"survey_id": str(survey.id), "rating": payload.rating}})
    return {"ok": True}
