"""tel-013 (DEC-SCOPE-100, spec §1-§3): messages sent to a lead -- a library template rendered with the lead's values (tel-012 C2), the
WhatsApp send log (wa.me can't report delivery, so a row is the telecaller's confirmation, T8) and the sender's same-day delete (WA3).

A message belongs to its lead: reads go through the lead's scope (`lead_pipeline.scope`), so a message on a lead the caller can't see is the
same 404 as a missing one. Only the lead's telecaller sends (WA2), and only the sender deletes, on its IST day. Writes lock the lead first.
Functions only; nothing here commits. Logs and audit carry ids, the channel and the template id -- never the text or a number (WA1).

tel-014 (DEC-SCOPE-102) adds email: the row is stored `queued` and the caller publishes it after the commit (E4); the worker
(`notifications/lead_email`) sends it. An email row is never deleted (EM2) and has its own daily cap (EM3, 429)."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.core.config import settings
from app.models import LEAD_APPOINTMENT_OPEN, Appointment, AuditLog, Enquiry, LeadMessage, TelAsset, TelMessageTemplate, TelProduct, User
from app.schemas import LeadEmailCreate, LeadWhatsAppCreate
from app.services import lead_pipeline, telecaller_content, telecaller_leads
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import IST, today_ist
from app.services.lead_appointments import invalid

logger = logging.getLogger("app.leads")

DAILY_CAP = 300  # D8: an abuse bound, far above real use (WhatsApp sends)
EMAIL_DAILY_CAP = 100  # EM3: emails per sender per IST day; also guards the shared SMTP account
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec")  # the app's en-GB short months

NOT_FOUND = "Message not found"
TEMPLATE_NOT_FOUND = "Template not found"
TELECALLER_ONLY = "Only the lead's telecaller can send a message"
SENDER_ONLY = "Only the telecaller who sent this message can delete it"
LEAD_CLOSED = "This lead is closed. A manager can reopen it before a message is sent"
NO_NUMBER = "This lead has no WhatsApp or mobile number"
TEMPLATE_UNUSABLE = "Choose an active WhatsApp template"
CAP_REACHED = f"You've sent {DAILY_CAP} messages today"
NO_EMAIL = "This lead has no email address"
EMAIL_TEMPLATE_UNUSABLE = "Choose an active email template"
EMAIL_CAP_REACHED = f"You've sent {EMAIL_DAILY_CAP} emails today"
EMAIL_NOT_CONFIGURED = "Email is not set up. Ask an administrator to configure SMTP."
EMAIL_NO_DELETE = "A sent email can't be deleted"
NOT_TODAY = "Only today's messages can be deleted"


def when_text(at: datetime) -> str:
    """D5: `{appointment_time}` as tel-012's sample, e.g. "Mon 14 Sept 2026, 10:30 AM" (IST)."""
    local = at.astimezone(IST)
    hour = local.hour % 12 or 12
    return f"{local:%a} {local.day} {MONTHS[local.month - 1]} {local.year}, {hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


async def active_template(db: AsyncSession, template_id: UUID) -> TelMessageTemplate:
    template = await db.get(TelMessageTemplate, template_id)
    if template is None or not template.active:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


async def render(db: AsyncSession, lead: Enquiry, template: TelMessageTemplate) -> dict:
    """D5: the lead's name; its product, else the template's; a fresh 7-day brochure link while the brochure is active (tel-012 C1); the
    lead's open counselling appointment. A missing value renders empty. D4: another product's template is a warning, never a refusal."""
    product_id = lead.product_id or template.product_id
    product = await db.get(TelProduct, product_id) if product_id else None
    asset = await db.get(TelAsset, template.asset_id) if template.asset_id else None
    link = telecaller_content.asset_link(asset) if asset and asset.active else None
    appointment_at = await db.scalar(select(Appointment.scheduled_at).where(
        Appointment.lead_id == lead.id, Appointment.status.in_(LEAD_APPOINTMENT_OPEN)).order_by(Appointment.scheduled_at).limit(1))
    values = {"name": lead.name, "product": product.name if product else "", "brochure_link": link["url"] if link else "",
              "appointment_time": when_text(appointment_at) if appointment_at else ""}
    return {
        "template": {"id": template.id, "name": template.name, "channel": template.channel, "kind": template.kind},
        "subject": telecaller_content.render(template.subject, values) if template.subject is not None else None,
        "body": telecaller_content.render(template.body, values), "brochure_link": link,
        "product_mismatch": bool(lead.product_id and template.product_id and lead.product_id != template.product_id),
    }


def can_delete(user: User, lead: Enquiry, message: LeadMessage, now: datetime) -> bool:
    return (message.channel == "whatsapp" and user.role == "telecaller" and message.sender_user_id == user.id and not telecaller_leads.read_only(user, lead)
            and today_ist(message.sent_at) == today_ist(now))


def out(user: User, lead: Enquiry, message: LeadMessage, sender: User, now: datetime) -> dict:
    return {
        "id": message.id, "lead_id": message.lead_id, "channel": message.channel,
        "template": {"id": message.template_id, "name": message.template_name} if message.template_id else None,
        "subject": message.subject, "body": message.body, "delivery_status": message.delivery_status, "sent_at": message.sent_at, "sender": {"id": sender.id, "full_name": sender.full_name},
        "can_delete": can_delete(user, lead, message, now),
    }


async def lead_page(db: AsyncSession, user: User, lead: Enquiry, now: datetime, limit: int, offset: int) -> dict:
    """The lead's messages, newest first."""
    where = LeadMessage.lead_id == lead.id
    total = await db.scalar(select(func.count()).select_from(LeadMessage).where(where))
    stmt = select(LeadMessage, User).join(User, User.id == LeadMessage.sender_user_id).where(where)
    rows = (await db.execute(stmt.order_by(LeadMessage.sent_at.desc(), LeadMessage.created_at.desc()).limit(limit).offset(offset))).all()
    return {"items": [out(user, lead, message, sender, now) for message, sender in rows], "total": total or 0, "limit": limit, "offset": offset}


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


async def create(db: AsyncSession, user: User, lead: Enquiry, payload: LeadWhatsAppCreate | LeadEmailCreate, now: datetime) -> LeadMessage:
    """The caller locked the lead and checked role and handover. WA2 closed -> 409. WhatsApp: D2 no number -> 409; D4 the template; D8 cap
    409. Email: E3 SMTP unset -> 503; E2 no address -> 409; E8 the template; EM3 cap 429. An email is stored `queued` (E5)."""
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    is_email = payload.channel == "email"
    if is_email and not smtp_configured():
        raise HTTPException(503, EMAIL_NOT_CONFIGURED)
    if is_email and not lead.email:
        raise HTTPException(409, NO_EMAIL)
    if not is_email and telecaller_leads.whatsapp_to(lead) is None:
        raise HTTPException(409, NO_NUMBER)
    template = await db.get(TelMessageTemplate, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not template.active or template.channel != payload.channel):
        raise invalid("template_id", EMAIL_TEMPLATE_UNUSABLE if is_email else TEMPLATE_UNUSABLE, str(payload.template_id))
    start, end = day_range(today_ist(now))
    count = await db.scalar(select(func.count()).select_from(LeadMessage).where(
        LeadMessage.sender_user_id == user.id, LeadMessage.channel == payload.channel, LeadMessage.sent_at >= start, LeadMessage.sent_at < end))
    cap, status, detail = (EMAIL_DAILY_CAP, 429, EMAIL_CAP_REACHED) if is_email else (DAILY_CAP, 409, CAP_REACHED)
    if (count or 0) >= cap:
        raise HTTPException(status, detail)
    message = LeadMessage(lead_id=lead.id, sender_user_id=user.id, channel=payload.channel, template_id=payload.template_id,
                          template_name=template.name if template else None, subject=payload.subject if is_email else None, body=payload.body,
                          delivery_status="queued" if is_email else None, sent_at=now)
    db.add(message)
    await db.flush()
    audit(db, user, "create", message.id, {"lead_id": str(lead.id), "channel": message.channel,
                                           "template_id": str(template.id) if template else None})
    return message


async def load_for_delete(db: AsyncSession, user: User, message_id: UUID, scope: list, now: datetime) -> LeadMessage:
    """In scope (404) -> lead lock -> telecaller and the sender (403) -> handover (403) -> an email (409, EM2) -> its IST day (409)."""
    lead_id = await db.scalar(select(LeadMessage.lead_id).join(Enquiry, Enquiry.id == LeadMessage.lead_id).where(LeadMessage.id == message_id, *scope))
    if lead_id is None:
        raise HTTPException(404, NOT_FOUND)
    lead = await lead_pipeline.locked_lead(db, lead_id, *scope)
    message = await db.scalar(select(LeadMessage).where(LeadMessage.id == message_id).with_for_update().execution_options(populate_existing=True))
    if message is None:  # deleted while we waited for the lead lock
        raise HTTPException(404, NOT_FOUND)
    if user.role != "telecaller" or message.sender_user_id != user.id:
        raise HTTPException(403, SENDER_ONLY)
    telecaller_leads.require_writable(user, lead)
    if message.channel == "email":
        raise HTTPException(409, EMAIL_NO_DELETE)
    if today_ist(message.sent_at) != today_ist(now):
        raise HTTPException(409, NOT_TODAY)
    return message


async def one(db: AsyncSession, user: User, message_id: UUID, now: datetime) -> dict:
    message, lead, sender = (await db.execute(
        select(LeadMessage, Enquiry, User).join(Enquiry, Enquiry.id == LeadMessage.lead_id).join(User, User.id == LeadMessage.sender_user_id)
        .where(LeadMessage.id == message_id)
    )).one()
    return out(user, lead, message, sender, now)


def audit(db: AsyncSession, user: User, action: str, message_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"lead_message.{action}", entity_type="lead_message", entity_id=str(message_id), metadata_json=metadata))


def log(event: str, user: User, message_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "message_id": str(message_id), **extra}})
