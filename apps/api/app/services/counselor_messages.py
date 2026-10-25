"""ccrm-037 (DEC-SCOPE-273, MT1-MT10): the Overseas Admin's message templates for counselors and the student message log -- the template
library rules (MT1, MT2), rendering with a student's and an application's values, sends (WhatsApp logged on confirm, email queued for the
worker), replies recorded by hand (no inbound provider, MT7) and the student's log. The upc-012 engine copied: its tables are bound to
universities.

Reads go through ccrm-009's gate (`staff_student`: the counselor's csc-001 scope or the Overseas Admin; anything else the same 404); only the
overseas counselor writes (MT4), and a message may be about one of the student's applications that is the counselor's own (ccrm-010 N3).
The caps are abuse bounds, counted without a lock -- a concurrent send may pass one over. Functions only; nothing here commits. Logs and
audit carry ids, the channel, the direction and the template id -- never the text, a subject, a number or an address (MT10)."""

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, CounselorMessageTemplate, NotificationPreference, OverseasApplication, OverseasCourse, StudentMessage, University, User
from app.notifications.phone import wa_number
from app.schemas import StudentEmailCreate, StudentEmailReply, StudentWhatsAppCreate, StudentWhatsAppReply
from app.services import mailer
from app.services.bdm_activities import BACKDATE_DAYS, day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_calls import check_time
from app.services.lead_messages import MONTHS
from app.services.student_notes import CHOOSE_APPLICATION, _applications, _label
from app.services.student_profiles import staff_student
from app.services.telecaller_content import _TOKEN

logger = logging.getLogger("app.counselor_messages")

TEMPLATE_NAME_INDEX = "uq_counselor_message_templates_channel_name"
BODY_LIMIT = {"whatsapp": 1000, "email": 5000}
PLACEHOLDERS = ("name", "university", "course", "intake", "application_deadline", "offer_deadline", "counselor")
_UNKNOWN = "Unknown placeholder {%s}. Use {name}, {university}, {course}, {intake}, {application_deadline}, {offer_deadline} or {counselor}"
SAMPLE_VALUES = {  # the preview's stand-in student and application; {counselor} is the caller
    "name": "Priya Sharma", "university": "University of Example", "course": "MSc Computer Science", "intake": "Sep 2027",
    "application_deadline": "14 Sept 2026", "offer_deadline": "1 Dec 2026",
}  # fmt: skip

DAILY_CAP = 300  # MT5: WhatsApp sends per sender per IST day (tel-013 D8)
EMAIL_DAILY_CAP = 100  # MT5: emails per sender per IST day; also guards the shared SMTP account (tel-014 EM3)
REPLY_DAILY_CAP = 300  # MT7: replies recorded per counselor per IST day
TEMPLATE_READERS_ONLY = "Only an overseas counselor or the Overseas Admin can view counselor message templates"
TEMPLATE_WRITERS_ONLY = "Only the Overseas Admin can change counselor message templates"
SENDER_ONLY = "Only the student's counselor can send messages"
TEMPLATE_NOT_FOUND = "Template not found"
DEACTIVATED = "This student's account is deactivated"
NO_NUMBER = "This student has no usable mobile number"
NOT_OPTED_IN = "This student has not opted in to WhatsApp messages"  # ccrm-040 (DEC-SCOPE-276 CN7)
TEMPLATE_UNUSABLE = {"whatsapp": "Choose an active WhatsApp template", "email": "Choose an active email template"}
CAP_REACHED = f"You've sent {DAILY_CAP} WhatsApp messages today"
EMAIL_CAP_REACHED = f"You've sent {EMAIL_DAILY_CAP} emails today"
REPLY_CAP_REACHED = f"You've recorded {REPLY_DAILY_CAP} replies today"
EMAIL_NOT_CONFIGURED = "Email is not set up. Ask an administrator to configure SMTP."
REPLY_FUTURE = "The reply time can't be in the future"
REPLY_TOO_OLD = f"Replies can be recorded up to {BACKDATE_DAYS} days back"

T, Msg = CounselorMessageTemplate, StudentMessage


# --- access (MT1, MT4) ----------------------------------------------------------------------------------------------------------
def is_counselor(user: User) -> bool:
    return user.role == "counselor" and user.division == "overseas"  # an IT counselor works leads only (tel-017)


def sees_inactive(user: User) -> bool:
    return user.role == "super_admin" or (user.role == "overseas_admin" and user.division == "overseas")


def require_template_reader(user: User) -> None:
    if not (is_counselor(user) or sees_inactive(user)):
        raise HTTPException(403, TEMPLATE_READERS_ONLY)


def require_template_writer(user: User) -> None:
    if not sees_inactive(user):
        raise HTTPException(403, TEMPLATE_WRITERS_ONLY)


async def sender_student(db: AsyncSession, user: User, student_id: UUID) -> User:
    """ccrm-009's gate (other roles 403, out of scope 404), then the sender's role: the Overseas Admin reads but does not send (403)."""
    student = await staff_student(db, user, student_id)
    if not is_counselor(user):
        raise HTTPException(403, SENDER_ONLY)
    return student


# --- templates (MT1, MT2) -------------------------------------------------------------------------------------------------------
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


def template_out(template: CounselorMessageTemplate) -> dict:
    return {k: getattr(template, k) for k in ("id", "channel", "name", "subject", "body", "active")}


def _render(text: str, values: dict[str, str]) -> str:
    """One pass, so a value that looks like a placeholder is never expanded again. Plain text out -- the sink escapes."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), "") if m.group(1) in PLACEHOLDERS else m.group(0), text)


def rendered(template: CounselorMessageTemplate, values: dict[str, str]) -> dict:
    """`missing` names the placeholders the template uses that had no value, so the composer can ask the counselor to check the text."""
    used = check_placeholders(template.subject, template.body)
    return {
        "subject": _render(template.subject, values) if template.subject is not None else None,
        "body": _render(template.body, values),
        "missing": [p for p in PLACEHOLDERS if p in used and not values.get(p)],
    }


async def active_template(db: AsyncSession, template_id: UUID) -> CounselorMessageTemplate:
    template = await db.get(T, template_id)
    if template is None or not template.active:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


# --- the application a message is about (MT2, MT4) ------------------------------------------------------------------------------
def _day(value: date | None) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}" if value else ""  # "14 Sept 2026", tel-013's en-GB months


async def own_application(db: AsyncSession, user: User, student_id: UUID, application_id: UUID | None) -> tuple[OverseasApplication, str, str | None] | None:
    """The application, its university and course -- one of this student's and the counselor's own (422 otherwise)."""
    if application_id is None:
        return None
    row = (
        await db.execute(
            select(OverseasApplication, University.name, OverseasCourse.title)
            .join(University, University.id == OverseasApplication.university_id)
            .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
            .where(OverseasApplication.id == application_id, OverseasApplication.student_id == student_id, OverseasApplication.counselor_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(422, CHOOSE_APPLICATION)
    application, university, course = row
    return application, university, course


def values(user: User, student: User, application: tuple[OverseasApplication, str, str | None] | None) -> dict[str, str]:
    """MT2: the student's name, the application's university, course, intake and deadlines (empty without one) and the sender's name."""
    app, university, course = application or (None, "", None)
    return {
        "name": student.full_name, "university": university, "course": course or "", "intake": app.intake if app else "",
        "application_deadline": _day(app.application_deadline) if app else "", "offer_deadline": _day(app.offer_deadline) if app else "",
        "counselor": user.full_name,
    }  # fmt: skip


# --- send and record (MT5-MT7) --------------------------------------------------------------------------------------------------
async def _count_today(db: AsyncSession, user: User, now: datetime, *where) -> int:
    start, end = day_range(today_ist(now))
    return await db.scalar(select(func.count()).select_from(Msg).where(Msg.sender_user_id == user.id, Msg.sent_at >= start, Msg.sent_at < end, *where)) or 0


async def create_message(db: AsyncSession, user: User, student_id: UUID, payload: StudentWhatsAppCreate | StudentEmailCreate, now: datetime) -> StudentMessage:
    """The order: scope (404) and role (403); a deactivated student 409; SMTP unset 503; no number 409; the application and the template
    422; the cap 409 / 429. An email is stored `queued`; the route publishes it after the commit (MT6)."""
    student = await sender_student(db, user, student_id)
    is_email = isinstance(payload, StudentEmailCreate)
    if not student.active:
        raise HTTPException(409, DEACTIVATED)
    if is_email and not mailer.smtp_configured():
        raise HTTPException(503, EMAIL_NOT_CONFIGURED)
    if not is_email and wa_number(student.phone) is None:
        raise HTTPException(409, NO_NUMBER)
    if not is_email and not await whatsapp_opt_in(db, student.id):
        raise HTTPException(409, NOT_OPTED_IN)
    await own_application(db, user, student.id, payload.application_id)
    template = await db.get(T, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not template.active or template.channel != payload.channel):
        raise HTTPException(422, TEMPLATE_UNUSABLE[payload.channel])
    cap, status, detail = (EMAIL_DAILY_CAP, 429, EMAIL_CAP_REACHED) if is_email else (DAILY_CAP, 409, CAP_REACHED)
    if await _count_today(db, user, now, Msg.direction == "outbound", Msg.channel == payload.channel) >= cap:
        raise HTTPException(status, detail)
    message = Msg(
        student_user_id=student.id,
        application_id=payload.application_id,
        sender_user_id=user.id,
        direction="outbound",
        channel=payload.channel,
        template_id=payload.template_id,
        template_name=template.name if template else None,
        subject=payload.subject if isinstance(payload, StudentEmailCreate) else None,
        body=payload.body,
        delivery_status="queued" if is_email else None,
        sent_at=now,
    )
    db.add(message)
    await db.flush()
    audit(db, user, "student_message.create", message, template.id if template else None)
    return message


async def create_reply(db: AsyncSession, user: User, student_id: UUID, payload: StudentWhatsAppReply | StudentEmailReply, now: datetime) -> StudentMessage:
    """MT7: scope and role as a send; the application 422; the received time 422; the cap 409. A deactivated student's reply is still kept."""
    student = await sender_student(db, user, student_id)
    await own_application(db, user, student.id, payload.application_id)
    received_at = check_time(payload.received_at or now, now, REPLY_FUTURE, REPLY_TOO_OLD)
    if await _count_today(db, user, now, Msg.direction == "inbound") >= REPLY_DAILY_CAP:
        raise HTTPException(409, REPLY_CAP_REACHED)
    message = Msg(
        student_user_id=student.id,
        application_id=payload.application_id,
        sender_user_id=user.id,
        direction="inbound",
        channel=payload.channel,
        subject=payload.subject if isinstance(payload, StudentEmailReply) else None,
        body=payload.body,
        sent_at=received_at,
    )
    db.add(message)
    await db.flush()
    audit(db, user, "student_message.reply", message, None)
    return message


# --- read (MT9) -----------------------------------------------------------------------------------------------------------------
def _rows():
    """One query: the message, its sender and the application's university -- no N+1."""
    return (
        select(Msg, User, University.name, OverseasApplication.application_reference)
        .join(User, User.id == Msg.sender_user_id)
        .outerjoin(OverseasApplication, OverseasApplication.id == Msg.application_id)
        .outerjoin(University, University.id == OverseasApplication.university_id)
    )


def message_out(message: StudentMessage, sender: User, university: str | None, reference: str | None) -> dict:
    return {
        "id": message.id,
        "student_id": message.student_user_id,
        "application": {"id": message.application_id, "label": _label(university, reference)} if message.application_id else None,
        "direction": message.direction,
        "channel": message.channel,
        "template": {"id": message.template_id, "name": message.template_name} if message.template_id else None,
        "subject": message.subject,
        "body": message.body,
        "delivery_status": message.delivery_status,
        "sent_at": message.sent_at,
        "sender": {"id": sender.id, "full_name": sender.full_name},
    }


async def whatsapp_opt_in(db: AsyncSession, student_id: UUID) -> bool:
    """ccrm-040 (DEC-SCOPE-276 CN7): WhatsApp to a student honours their ENH-014 preference (no row = not opted in); email is always on."""
    pref = await db.get(NotificationPreference, student_id)
    return bool(pref and pref.whatsapp_opt_in)


async def page(db: AsyncSession, user: User, student: User, limit: int, offset: int) -> dict:
    """The student's whole log, newest first, whoever wrote it; the recipient and the applications a message may be about."""
    where = Msg.student_user_id == student.id
    total = await db.scalar(select(func.count()).select_from(Msg).where(where))
    rows = (await db.execute(_rows().where(where).order_by(Msg.sent_at.desc(), Msg.created_at.desc()).limit(limit).offset(offset))).all()
    opted_in = await whatsapp_opt_in(db, student.id)
    return {
        "items": [message_out(*row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "recipient": {"name": student.full_name, "email": student.email, "whatsapp_to": wa_number(student.phone), "whatsapp_opt_in": opted_in},
        "applications": await _applications(db, user, student.id),
    }


async def one(db: AsyncSession, message_id: UUID) -> dict:
    return message_out(*(await db.execute(_rows().where(Msg.id == message_id))).one())


def audit(db: AsyncSession, user: User, action: str, message: StudentMessage, template_id: UUID | None) -> None:
    metadata = {
        "student_id": str(message.student_user_id), "application_id": str(message.application_id) if message.application_id else None,
        "channel": message.channel, "direction": message.direction, "template_id": str(template_id) if template_id else None,
    }  # fmt: skip
    db.add(AuditLog(user_id=user.id, action=action, entity_type="student_message", entity_id=str(message.id), metadata_json=metadata))


def log(event: str, user: User, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entity_id": str(entity_id), **extra}})
