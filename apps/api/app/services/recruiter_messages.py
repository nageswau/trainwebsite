"""rec-026 (DEC-SCOPE-134, spec §1-§3): the recruiter message engine -- the template library rules (MS1-MS3), rendering with a party's values
(MS2), and messages to a company contact or a candidate (MS4-MS10). The tel-012/013/014 engine copied, not shared: `lead_messages` is bound
to `enquiries`.

A contact message belongs to its company: reads and writes go through rec-003's scope (`load_scoped`, `can_edit`), so another recruiter's
contact is the same 404 as a missing one. A candidate message follows the pool (rec-009, R11). Writes lock the party first, so the daily cap
is counted exactly. Functions only; nothing here commits. Logs and audit carry ids, the channel and the template id -- never the text, a
subject or an address (MS9)."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import REC_EMAIL_KINDS, REC_WHATSAPP_KINDS, AuditLog, Candidate, Company, CompanyContact, RecruiterMessage, RecruiterMessageTemplate, User
from app.notifications.phone import wa_number
from app.schemas import RecEmailCreate, RecWhatsAppCreate
from app.services import candidates, mailer
from app.services import recruiter_companies as companies
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.telecaller_content import _TOKEN

logger = logging.getLogger("app.recruiter")

# --- the template library (MS1-MS3) ---------------------------------------------------------------------------------------------
KINDS_BY_CHANNEL = {"whatsapp": REC_WHATSAPP_KINDS, "email": REC_EMAIL_KINDS}
TEMPLATE_READERS = frozenset({ROLE, MANAGER_ROLE, "super_admin"})
TEMPLATE_WRITERS = frozenset({MANAGER_ROLE, "super_admin"})
TEMPLATE_NAME_INDEX = "uq_recruiter_message_templates_channel_name"
BODY_LIMIT = {"whatsapp": 1000, "email": 5000}
PLACEHOLDERS = ("name", "company", "recruiter")
_UNKNOWN = "Unknown placeholder {%s}. Use {name}, {company} or {recruiter}"
SAMPLE_VALUES = {"name": "Priya Sharma", "company": "Acme Technologies"}  # the preview's stand-in recipient; {recruiter} is the caller

# --- messages (MS4-MS10) --------------------------------------------------------------------------------------------------------
DAILY_CAP = 300  # MS8: WhatsApp sends per sender per IST day -- an abuse bound (tel-013 D8)
EMAIL_DAILY_CAP = 100  # MS8: emails per sender per IST day; also guards the shared SMTP account (tel-014 EM3)
TEMPLATE_NOT_FOUND = "Template not found"
CONTACT_NOT_FOUND = "Contact not found"
CONTACT_INACTIVE = "This contact is inactive. Reactivate it before sending a message"
CANDIDATE_ARCHIVED = "Restore this candidate before sending a message"
PARTY_REQUIRED = "Choose a contact or a candidate"
NO_NUMBER = {"contact": "This contact has no mobile number", "candidate": "This candidate has no mobile number"}
NO_EMAIL = {"contact": "This contact has no email address", "candidate": "This candidate has no email address"}
TEMPLATE_UNUSABLE = {"whatsapp": "Choose an active WhatsApp template", "email": "Choose an active email template"}
CAP_REACHED = f"You've sent {DAILY_CAP} WhatsApp messages today"
EMAIL_CAP_REACHED = f"You've sent {EMAIL_DAILY_CAP} emails today"
EMAIL_NOT_CONFIGURED = "Email is not set up. Ask an administrator to configure SMTP."

RM = RecruiterMessage
NOT_FAILED = ~and_(RM.channel == "email", RM.delivery_status == "failed")


def require_template_reader(user: User) -> None:
    if user.role not in TEMPLATE_READERS:
        raise HTTPException(403, "Your role cannot view the recruiter message templates")


def require_template_writer(user: User) -> None:
    if user.role not in TEMPLATE_WRITERS:
        raise HTTPException(403, "Only a placement manager can change message templates")


def sees_inactive(user: User) -> bool:
    return user.role in TEMPLATE_WRITERS


def check_placeholders(*texts: str | None) -> set[str]:
    """MS2: every `{...}` must be one of the placeholders, spelled exactly; returns the ones used. A lone brace is plain text."""
    used: set[str] = set()
    for text in texts:
        for token in _TOKEN.findall(text or ""):
            if token not in PLACEHOLDERS:
                raise HTTPException(422, _UNKNOWN % token)
            used.add(token)
    return used


def render(text: str, values: dict[str, str]) -> str:
    """One pass, so a value that looks like a placeholder is never expanded again; a missing value renders empty. Plain text out -- the
    sink escapes (wa.me URL-encoding, the mailer's HTML)."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), "") if m.group(1) in PLACEHOLDERS else m.group(0), text)


def check_template(channel: str, kind: str, subject: str | None, body: str) -> None:
    """The template rules, on the merged row (create, or a row plus a PATCH)."""
    if kind not in KINDS_BY_CHANNEL[channel]:
        raise HTTPException(422, f"Choose {'a WhatsApp' if channel == 'whatsapp' else 'an email'} template kind")
    if channel == "whatsapp" and subject is not None:
        raise HTTPException(422, "Only email templates have a subject")
    if channel == "email" and subject is None:
        raise HTTPException(422, "Subject is required")
    if len(body) > BODY_LIMIT[channel]:
        raise HTTPException(422, f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} message must be at most {BODY_LIMIT[channel]} characters")
    check_placeholders(subject, body)


def template_out(template: RecruiterMessageTemplate) -> dict:
    return {k: getattr(template, k) for k in ("id", "channel", "kind", "name", "subject", "body", "active")}


def rendered(template: RecruiterMessageTemplate, values: dict[str, str]) -> dict:
    """QA-02: `missing` names the placeholders the template uses that had no value (e.g. {company} for a candidate), so the composer can
    ask the recruiter to check the text."""
    used = check_placeholders(template.subject, template.body)
    return {
        "subject": render(template.subject, values) if template.subject is not None else None,
        "body": render(template.body, values),
        "missing": [p for p in PLACEHOLDERS if p in used and not values.get(p)],
    }


# --- the party (MS4, MS5) -------------------------------------------------------------------------------------------------------
async def load_party(db: AsyncSession, user: User, contact_id: UUID | None, candidate_id: UUID | None, *, write: bool = False):
    """(company, contact, candidate) -- the contact's company is read from the contact, never from the client. Reads check scope (404);
    a write also locks the party, then needs the right (403) and an active party (409)."""
    if (contact_id is None) == (candidate_id is None):
        raise HTTPException(422, PARTY_REQUIRED)
    if candidate_id is not None:
        (candidates.require_writer if write else candidates.require_reader)(user)
        candidate = await candidates.load(db, candidate_id, lock=write)
        if write and candidate.archived_at is not None:
            raise HTTPException(409, CANDIDATE_ARCHIVED)
        return None, None, candidate
    company_id = await db.scalar(select(CompanyContact.company_id).where(CompanyContact.id == contact_id))
    if company_id is None:
        await companies.caller_scope(db, user)  # the role check (403) comes before "not found"
        raise HTTPException(404, CONTACT_NOT_FOUND)
    try:
        company = await companies.load_scoped(db, user, company_id, lock=write)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, CONTACT_NOT_FOUND) from None
        raise
    contact = await db.get(CompanyContact, contact_id, populate_existing=write)
    if write:
        companies.require(user, company, "can_edit", "message_send")
        if not contact.active:
            raise HTTPException(409, CONTACT_INACTIVE)
    return company, contact, None


def party_values(user: User, company: Company | None, contact: CompanyContact | None, candidate: Candidate | None) -> dict[str, str]:
    """MS2: the recipient's name, the contact's company (empty for a candidate) and the sender's name."""
    return {"name": (contact or candidate).name, "company": company.name if company else "", "recruiter": user.full_name}


async def active_template(db: AsyncSession, template_id: UUID) -> RecruiterMessageTemplate:
    template = await db.get(RecruiterMessageTemplate, template_id)
    if template is None or not template.active:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


# --- send and read --------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, payload: RecWhatsAppCreate | RecEmailCreate, now: datetime) -> RecruiterMessage:
    """The error order of spec §3: role and scope, the party lock, the right and state; SMTP unset 503; no number / address 409; the
    template 422; the cap 409 / 429. An email is stored `queued`; the route publishes it after the commit (MS7)."""
    company, contact, candidate = await load_party(db, user, payload.contact_id, payload.candidate_id, write=True)
    party, kind = (contact, "contact") if contact else (candidate, "candidate")
    is_email = isinstance(payload, RecEmailCreate)
    if is_email and not mailer.smtp_configured():
        raise HTTPException(503, EMAIL_NOT_CONFIGURED)
    if is_email and not party.email:
        raise HTTPException(409, NO_EMAIL[kind])
    if not is_email and wa_number(party.mobile) is None:
        raise HTTPException(409, NO_NUMBER[kind])
    template = await db.get(RecruiterMessageTemplate, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not template.active or template.channel != payload.channel):
        raise HTTPException(422, TEMPLATE_UNUSABLE[payload.channel])
    start, end = day_range(today_ist(now))
    count = await db.scalar(select(func.count()).select_from(RM).where(RM.sender_user_id == user.id, RM.channel == payload.channel, RM.sent_at >= start, RM.sent_at < end))
    cap, status, detail = (EMAIL_DAILY_CAP, 429, EMAIL_CAP_REACHED) if is_email else (DAILY_CAP, 409, CAP_REACHED)
    if (count or 0) >= cap:
        raise HTTPException(status, detail)
    message = RM(
        company_id=company.id if company else None,
        contact_id=contact.id if contact else None,
        candidate_id=candidate.id if candidate else None,
        sender_user_id=user.id,
        channel=payload.channel,
        template_id=payload.template_id,
        template_name=template.name if template else None,
        subject=payload.subject if is_email else None,
        body=payload.body,
        delivery_status="queued" if is_email else None,
        sent_at=now,
    )
    db.add(message)
    await db.flush()
    audit(db, user, message.id, {"kind": kind, "party_id": str(party.id), "channel": message.channel, "template_id": str(template.id) if template else None})
    return message


def _rows():
    """One query: the message, its sender, and the contact or candidate -- no N+1."""
    return (
        select(RM, User, CompanyContact, Candidate)
        .join(User, User.id == RM.sender_user_id)
        .outerjoin(CompanyContact, CompanyContact.id == RM.contact_id)
        .outerjoin(Candidate, Candidate.id == RM.candidate_id)
    )


def out(message: RecruiterMessage, sender: User, contact: CompanyContact | None, candidate: Candidate | None) -> dict:
    return {
        "id": message.id,
        "kind": "contact" if contact else "candidate",
        "company_id": message.company_id,
        "contact": {"id": contact.id, "name": contact.name} if contact else None,
        "candidate": {"id": candidate.id, "name": candidate.name, "code": candidate.candidate_code} if candidate else None,
        "channel": message.channel,
        "template": {"id": message.template_id, "name": message.template_name} if message.template_id else None,
        "subject": message.subject,
        "body": message.body,
        "delivery_status": message.delivery_status,
        "sent_at": message.sent_at,
        "sender": {"id": sender.id, "full_name": sender.full_name},
    }


async def page(db: AsyncSession, where, limit: int, offset: int) -> dict:
    """Newest first."""
    total = await db.scalar(select(func.count()).select_from(RM).where(where))
    rows = (await db.execute(_rows().where(where).order_by(RM.sent_at.desc(), RM.created_at.desc()).limit(limit).offset(offset))).all()
    return {"items": [out(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, message_id: UUID) -> dict:
    return out(*(await db.execute(_rows().where(RM.id == message_id))).one())


async def contact_last(db: AsyncSession, company_id: UUID) -> dict[UUID, datetime]:
    """MS10: each contact's latest message (a failed email never reached them) -- one query for the company's contact list."""
    rows = await db.execute(select(RM.contact_id, func.max(RM.sent_at)).where(RM.company_id == company_id, NOT_FAILED).group_by(RM.contact_id))
    return dict(rows.all())


def audit(db: AsyncSession, user: User, message_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action="recruiter_message.create", entity_type="recruiter_message", entity_id=str(message_id), metadata_json=metadata))


def log(event: str, user: User, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entity_id": str(entity_id), **extra}})
