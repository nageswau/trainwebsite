"""tel-013 (DEC-SCOPE-100, spec §3): messages to a lead -- render a library template with the lead's values, the lead's send log, record
a WhatsApp send and the sender's same-day delete.

Scope is the lead's (tel-004 `lead_pipeline.scope`; other roles 403, out of scope 404). Every write is one transaction -- scope, the lead
lock, role, handover, the rules, the row, audit, one commit here, then the log."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Enquiry, User
from app.notifications import dispatch
from app.schemas import LeadMessageCreate
from app.services import lead_messages as svc
from app.services import lead_pipeline, telecaller_leads
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/telecaller", tags=["telecaller-messages"])


async def _lead_in_scope(db: AsyncSession, user: User, lead_id: UUID) -> Enquiry:
    _, scope = lead_pipeline.scope(user)
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *scope))
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return lead


@router.get("/leads/{lead_id}/render")
async def render_for_lead(lead_id: UUID, template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-012 C2: an active template (WhatsApp or email) rendered with the lead's values (D5). Read-only, so the lead's scope suffices."""
    lead = await _lead_in_scope(db, user, lead_id)
    return await svc.render(db, lead, await svc.active_template(db, template_id))


@router.get("/leads/{lead_id}/messages")
async def lead_messages(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lead = await _lead_in_scope(db, user, lead_id)
    return await svc.lead_page(db, user, lead, await db_now(db), limit, offset)


@router.post("/leads/{lead_id}/messages", status_code=201)
async def record_message(lead_id: UUID, payload: LeadMessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: the telecaller confirms a WhatsApp send (D3), or (tel-014) sends an email: stored `queued` and published only after the commit,
    so the worker never looks for an uncommitted row (E4). Not idempotent -- each call is one send; the daily caps bound a retry."""
    _, scope = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *scope)
    if user.role != "telecaller":
        raise HTTPException(403, svc.TELECALLER_ONLY)
    telecaller_leads.require_writable(user, lead)
    now = await db_now(db)
    message = await svc.create(db, user, lead, payload, now)
    await db.commit()
    if message.channel == "email":
        dispatch.enqueue_lead_email(message.id)
    svc.log("lead_message_sent", user, message.id, lead_id=str(lead_id), channel=message.channel)
    return await svc.one(db, user, message.id, now)


@router.delete("/messages/{message_id}", status_code=204)
async def delete_message(message_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """WA3: the sender, on the message's IST day, lead still theirs."""
    _, scope = lead_pipeline.scope(user)
    message = await svc.load_for_delete(db, user, message_id, scope, await db_now(db))
    svc.audit(db, user, "delete", message.id, {"lead_id": str(message.lead_id), "channel": message.channel})
    await db.delete(message)
    await db.commit()
    svc.log("lead_message_deleted", user, message_id)
    return Response(status_code=204)
