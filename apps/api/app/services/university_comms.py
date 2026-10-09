"""upc-012 (DEC-SCOPE-138, spec §1-§3): calls, WhatsApp and email stored against the university (§12, U10) -- the partnership template
library (UC4, UC5), the contact as the party (UC3), calls (UC1), messages (UC6-UC9) and a contact's last interaction (UC10). The rec-025 /
rec-026 engine, copied: those tables are bound to companies and candidates.

Reads follow upc-006's full contact view (CONTACT_ROLES); writes lock the university, then need `can_edit_contacts` on it and read the
contact under that lock, so a concurrent contact delete is a clean 404. Functions only; nothing here commits. Logs and audit carry ids, the
channel, the outcome and the template id -- never notes, text, a subject, a number or an address (UC9)."""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, PartnershipMessageTemplate, University, UniversityCall, UniversityContact, UniversityMessage, User
from app.schemas import UniversityCallCreate, UniversityEmailCreate, UniversityWhatsAppCreate
from app.services import mailer
from app.services import partnership_universities as unis
from app.services import university_contacts as contacts
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_calls import check_time
from app.services.recruiter_calls import CONNECTED, OUTCOMES
from app.services.telecaller_content import _TOKEN

logger = logging.getLogger("app.partnership")

READERS = unis.CONTACT_ROLES  # UC3: partnership roles and super_admin; overseas_admin and everyone else -> 403
TEMPLATE_WRITERS = frozenset({"partnership_head", "super_admin"})  # UC4 (U10)
TEMPLATE_NAME_INDEX = "uq_partnership_message_templates_channel_name"
BODY_LIMIT = {"whatsapp": 1000, "email": 5000}
PLACEHOLDERS = ("name", "university", "manager")
_UNKNOWN = "Unknown placeholder {%s}. Use {name}, {university} or {manager}"
SAMPLE_VALUES = {"name": "Priya Sharma", "university": "University of Example"}  # the preview's stand-in; {manager} is the caller

CALL_DAILY_CAP = 300  # UC1 (rec-025 CA9): an abuse bound
DAILY_CAP = 300  # UC8: WhatsApp sends per sender per IST day
EMAIL_DAILY_CAP = 100  # UC8: emails per sender per IST day; also guards the shared SMTP account
FOLLOW_UP_DAYS = 365
TEMPLATE_NOT_FOUND = "Template not found"
NO_NUMBER = "This contact has no usable WhatsApp or phone number"
NO_EMAIL = "This contact has no email address"
TEMPLATE_UNUSABLE = {"whatsapp": "Choose an active WhatsApp template", "email": "Choose an active email template"}
CALL_CAP_REACHED = f"You've logged {CALL_DAILY_CAP} calls for this day"
CAP_REACHED = f"You've sent {DAILY_CAP} WhatsApp messages today"
EMAIL_CAP_REACHED = f"You've sent {EMAIL_DAILY_CAP} emails today"
EMAIL_NOT_CONFIGURED = "Email is not set up. Ask an administrator to configure SMTP."

T, Call, Msg = PartnershipMessageTemplate, UniversityCall, UniversityMessage
NOT_FAILED = ~and_(Msg.channel == "email", Msg.delivery_status == "failed")


# --- access (UC3) ---------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    await unis.require_reader(db, user)  # 403 for other roles; a manager needs a profile
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view university communications")


def require_template_writer(user: User) -> None:
    if user.role not in TEMPLATE_WRITERS:
        raise HTTPException(403, "Only the partnership head can change message templates")


def sees_inactive(user: User) -> bool:
    return user.role in TEMPLATE_WRITERS


async def readable_contact(db: AsyncSession, user: User, contact_id: UUID) -> tuple[University, UniversityContact]:
    await require_reader(db, user)
    contact = await db.get(UniversityContact, contact_id)
    if contact is None:
        raise HTTPException(404, contacts.NOT_FOUND)
    return await unis.load(db, contact.university_id), contact


async def writable_contact(db: AsyncSession, user: User, contact_id: UUID, route: str) -> tuple[University, UniversityContact]:
    """Lock the university (as upc-006's writes do), then the edit scope (403) and an active university (409), then the contact."""
    await require_reader(db, user)
    uni = await unis.load(db, await contacts.university_of(db, contact_id), lock=True)
    unis.require(user, uni, await unis.team_of(db, user), "can_edit_contacts", route)
    return uni, await contacts.load(db, contact_id)


# --- templates (UC4, UC5) -------------------------------------------------------------------------------------------------------
def check_placeholders(*texts: str | None) -> set[str]:
    """Every `{...}` must be one of the placeholders, spelled exactly; returns the ones used. A lone brace is plain text."""
    used: set[str] = set()
    for text in texts:
        for token in _TOKEN.findall(text or ""):
            if token not in PLACEHOLDERS:
                raise HTTPException(422, _UNKNOWN % token)
            used.add(token)
    return used


def check_template(channel: str, subject: str | None, body: str) -> None:
    """The template rules, on the merged row (create, or a row plus a PATCH)."""
    if channel == "whatsapp" and subject is not None:
        raise HTTPException(422, "Only email templates have a subject")
    if channel == "email" and subject is None:
        raise HTTPException(422, "Subject is required")
    if len(body) > BODY_LIMIT[channel]:
        raise HTTPException(422, f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} message must be at most {BODY_LIMIT[channel]} characters")
    check_placeholders(subject, body)


def template_out(template: PartnershipMessageTemplate) -> dict:
    return {k: getattr(template, k) for k in ("id", "channel", "name", "subject", "body", "active")}


def _render(text: str, values: dict[str, str]) -> str:
    """One pass, so a value that looks like a placeholder is never expanded again. Plain text out -- the sink escapes."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), "") if m.group(1) in PLACEHOLDERS else m.group(0), text)


def rendered(template: PartnershipMessageTemplate, values: dict[str, str]) -> dict:
    """`missing` names the placeholders the template uses that had no value, so the composer can ask the manager to check the text."""
    used = check_placeholders(template.subject, template.body)
    return {
        "subject": _render(template.subject, values) if template.subject is not None else None,
        "body": _render(template.body, values),
        "missing": [p for p in PLACEHOLDERS if p in used and not values.get(p)],
    }


def contact_values(user: User, uni: University, contact: UniversityContact) -> dict[str, str]:
    return {"name": contact.name, "university": uni.name, "manager": user.full_name}


async def active_template(db: AsyncSession, template_id: UUID) -> PartnershipMessageTemplate:
    template = await db.get(T, template_id)
    if template is None or not template.active:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


# --- calls (UC1) ----------------------------------------------------------------------------------------------------------------
def _invalid(field: str, msg: str, value) -> RequestValidationError:
    """On the field (the validation-error shape), so the form can place it."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_follow_up(day: date | None, now: datetime) -> None:
    today = today_ist(now)
    if day is not None and not today <= day <= today + timedelta(days=FOLLOW_UP_DAYS):
        raise _invalid("next_follow_up_on", f"Choose a follow-up date from today to {FOLLOW_UP_DAYS} days ahead", day.isoformat())


async def _count_today(db: AsyncSession, column, user_column, user: User, now: datetime, *where) -> int:
    start, end = day_range(today_ist(now))
    return await db.scalar(select(func.count()).where(user_column == user.id, column >= start, column < end, *where)) or 0


async def create_call(db: AsyncSession, user: User, payload: UniversityCallCreate, now: datetime) -> UniversityCall:
    """The error order of spec §3: role, the contact (404), the university lock, scope (403) and state (409), the time and follow-up
    (422), the cap (409)."""
    uni, contact = await writable_contact(db, user, payload.contact_id, "call_create")
    occurred_at = check_time(payload.occurred_at or now, now)
    check_follow_up(payload.next_follow_up_on, now)
    if await _count_today(db, Call.occurred_at, Call.caller_user_id, user, occurred_at) >= CALL_DAILY_CAP:
        raise HTTPException(409, CALL_CAP_REACHED)
    call = Call(
        university_id=uni.id,
        contact_id=contact.id,
        caller_user_id=user.id,
        occurred_at=occurred_at,
        duration_seconds=payload.duration_seconds,
        direction=payload.direction,
        outcome=payload.outcome,
        notes=payload.notes,
        next_follow_up_on=payload.next_follow_up_on,
    )
    db.add(call)
    await db.flush()
    audit(db, user, "university_call.create", "university_call", call.id, {"university_id": str(uni.id), "contact_id": str(contact.id), "outcome": call.outcome})
    return call


def call_out(call: UniversityCall, caller: User, contact: UniversityContact | None) -> dict:
    return {
        "id": call.id,
        "university_id": call.university_id,
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "occurred_at": call.occurred_at,
        "duration_seconds": call.duration_seconds,
        "direction": call.direction,
        "outcome": call.outcome,
        "outcome_label": OUTCOMES[call.outcome],
        "connected": call.outcome in CONNECTED,
        "notes": call.notes,
        "next_follow_up_on": call.next_follow_up_on,
        "caller": {"id": caller.id, "full_name": caller.full_name},
        "created_at": call.created_at,
    }


# --- messages (UC6-UC9) ---------------------------------------------------------------------------------------------------------
async def create_message(db: AsyncSession, user: User, payload: UniversityWhatsAppCreate | UniversityEmailCreate, now: datetime) -> UniversityMessage:
    """Spec §3's order: role, contact, lock, scope and state; SMTP unset 503; no number / address 409; the template 422; the cap 409 / 429.
    An email is stored `queued`; the route publishes it after the commit (UC7)."""
    uni, contact = await writable_contact(db, user, payload.contact_id, "message_send")
    is_email = isinstance(payload, UniversityEmailCreate)
    if is_email and not mailer.smtp_configured():
        raise HTTPException(503, EMAIL_NOT_CONFIGURED)
    if is_email and not contact.email:
        raise HTTPException(409, NO_EMAIL)
    if not is_email and contacts.whatsapp_to(contact) is None:
        raise HTTPException(409, NO_NUMBER)
    template = await db.get(T, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not template.active or template.channel != payload.channel):
        raise HTTPException(422, TEMPLATE_UNUSABLE[payload.channel])
    cap, status, detail = (EMAIL_DAILY_CAP, 429, EMAIL_CAP_REACHED) if is_email else (DAILY_CAP, 409, CAP_REACHED)
    if await _count_today(db, Msg.sent_at, Msg.sender_user_id, user, now, Msg.channel == payload.channel) >= cap:
        raise HTTPException(status, detail)
    message = Msg(
        university_id=uni.id,
        contact_id=contact.id,
        sender_user_id=user.id,
        channel=payload.channel,
        template_id=payload.template_id,
        template_name=template.name if template else None,
        subject=payload.subject if isinstance(payload, UniversityEmailCreate) else None,
        body=payload.body,
        delivery_status="queued" if is_email else None,
        sent_at=now,
    )
    db.add(message)
    await db.flush()
    metadata = {"university_id": str(uni.id), "contact_id": str(contact.id), "channel": message.channel, "template_id": str(template.id) if template else None}
    audit(db, user, "university_message.create", "university_message", message.id, metadata)
    return message


def message_out(message: UniversityMessage, sender: User, contact: UniversityContact | None) -> dict:
    return {
        "id": message.id,
        "university_id": message.university_id,
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "channel": message.channel,
        "template": {"id": message.template_id, "name": message.template_name} if message.template_id else None,
        "subject": message.subject,
        "body": message.body,
        "delivery_status": message.delivery_status,
        "sent_at": message.sent_at,
        "sender": {"id": sender.id, "full_name": sender.full_name},
    }


# --- lists and last interaction (UC10) ------------------------------------------------------------------------------------------
_SOURCES: dict[str, tuple[Any, Any, Any, Any]] = {"calls": (Call, Call.caller_user_id, Call.occurred_at, call_out), "messages": (Msg, Msg.sender_user_id, Msg.sent_at, message_out)}


async def page(db: AsyncSession, kind: str, university_id: UUID, limit: int, offset: int) -> dict:
    """Newest first; one query for the rows, their author and contact -- no N+1."""
    model, author, when, out = _SOURCES[kind]
    where = model.university_id == university_id
    total = await db.scalar(select(func.count()).select_from(model).where(where))
    stmt = (
        select(model, User, UniversityContact)
        .join(User, User.id == author)
        .outerjoin(UniversityContact, UniversityContact.id == model.contact_id)
        .where(where)
        .order_by(when.desc(), model.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return {"items": [out(*row) for row in (await db.execute(stmt)).all()], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, kind: str, row_id: UUID) -> dict:
    model, author, _, out = _SOURCES[kind]
    stmt = select(model, User, UniversityContact).join(User, User.id == author).outerjoin(UniversityContact, UniversityContact.id == model.contact_id)
    return out(*(await db.execute(stmt.where(model.id == row_id))).one())


async def last_interactions(db: AsyncSession, contact_ids: list[UUID]) -> dict[UUID, datetime]:
    """UC10: each contact's latest call or message (a failed email never reached them) -- two grouped queries."""
    latest: dict[UUID, datetime] = {}
    if not contact_ids:
        return latest
    queries = (
        select(Call.contact_id, func.max(Call.occurred_at)).where(Call.contact_id.in_(contact_ids)).group_by(Call.contact_id),
        select(Msg.contact_id, func.max(Msg.sent_at)).where(Msg.contact_id.in_(contact_ids), NOT_FAILED).group_by(Msg.contact_id),
    )
    for stmt in queries:
        for contact_id, when in (await db.execute(stmt)).all():
            if contact_id is not None:  # the IN filter excludes NULL; this narrows the type
                latest[contact_id] = max(when, latest.get(contact_id, when))
    return latest


def audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


def log(event: str, user: User, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entity_id": str(entity_id), **extra}})
