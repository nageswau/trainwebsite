"""rec-026 (DEC-SCOPE-135, spec §1-§3): the recruiter message engine -- the template library rules (MS1-MS3), rendering with a party's values
(MS2), and messages to a company contact or a candidate (MS4-MS10). The tel-012/013/014 engine copied, not shared: `lead_messages` is bound
to `enquiries`.

A contact message belongs to its company: reads and writes go through rec-003's scope (`load_scoped`, `can_edit`), so another recruiter's
contact is the same 404 as a missing one. A candidate message follows the pool (rec-009, R11). Writes lock the party first, so the daily cap
is counted exactly. Functions only; nothing here commits. Logs and audit carry ids, the channel and the template id -- never the text, a
subject or an address (MS9).

pob-023 (DEC-SCOPE-408 G1-G12): the governed library.
- LinkedIn and calling-script channels; categories and metadata.
- Draft -> Approved -> Archived; personal templates are private to their author.
- Versions, the placeholder allow-list filled from an optional requirement or interview, and copy mode for LinkedIn and calls."""

import logging
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    REC_EMAIL_KINDS,
    REC_TEMPLATE_CATEGORIES,
    REC_WHATSAPP_KINDS,
    AuditLog,
    Candidate,
    Company,
    CompanyContact,
    Interview,
    Job,
    RecruiterFollowUp,
    RecruiterMessage,
    RecruiterMessageTemplate,
    RecruiterTemplateVersion,
    User,
)
from app.notifications.phone import wa_number
from app.schemas import RecEmailCreate, RecFollowUpCreate, RecLinkedInCreate, RecMessageOutcome, RecTemplateCopy, RecWhatsAppCreate
from app.services import applications, candidates, contact_status, mailer, recruiter_contracts
from app.services import recruiter_companies as companies
from app.services import recruiter_follow_ups as follow_ups
from app.services import recruiter_requirements as requirements
from app.services.bdm_activities import BACKDATE_DAYS, CLOCK_TOLERANCE, day_range
from app.services.bdm_appointments import today_ist
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.telecaller_content import _TOKEN

logger = logging.getLogger("app.recruiter")

# --- the template library (MS1-MS3) ---------------------------------------------------------------------------------------------
KINDS_BY_CHANNEL = {"whatsapp": REC_WHATSAPP_KINDS, "email": REC_EMAIL_KINDS, "linkedin": (), "call": ()}
TEMPLATE_READERS = frozenset({ROLE, MANAGER_ROLE, "super_admin"})
TEMPLATE_WRITERS = TEMPLATE_READERS  # pob-023 G6: everyone in the library adds and edits; approval is the Team Lead's
APPROVERS = frozenset({MANAGER_ROLE, "super_admin"})
TEMPLATE_NAME_INDEX = "uq_recruiter_message_templates_channel_name"
OWNER_NAME_INDEX = "uq_recruiter_message_templates_owner_name"
BODY_LIMIT = {"whatsapp": 1000, "email": 5000, "linkedin": 2000, "call": 5000}
STEPS_MAX = 20
CHANNEL_NOUN = {"whatsapp": "A WhatsApp", "email": "An email", "linkedin": "A LinkedIn", "call": "A calling-script"}
# pob-023 G8: the allow-list -- a name maps to one value the server computes; no field access
PLACEHOLDERS = (
    "name", "company", "recruiter", "designation", "job_title", "job_location", "package_range", "candidate", "interview_date",
    "interview_time", "interview_mode", "interview_link",
)  # fmt: skip
_UNKNOWN = "Unknown placeholder {%s}. Use one of the placeholders listed under the message"
SAMPLE_VALUES = {  # the preview's stand-in recipient and context; {recruiter} is the caller
    "name": "Priya Sharma", "company": "Acme Technologies", "designation": "HR Manager", "job_title": "Java Developer", "job_location": "Pune",
    "package_range": "INR 600,000 – 900,000 a year", "candidate": "Rahul Verma", "interview_date": "15 Jan 2030", "interview_time": "10:30 AM",
    "interview_mode": "Online", "interview_link": "https://meet.example.com/abc",
}  # fmt: skip
VERSIONED = ("name", "kind", "category", "subject", "body", "steps", "purpose", "language", "department", "industry", "role_type")
# G2: a template created without a category gets its channel's (email by kind: what goes to a candidate, else a company)
CANDIDATE_EMAIL_KINDS = ("interview_confirmation", "offer_follow_up", "joining_confirmation")
CONTEXT_BOTH = "Choose a requirement or an interview, not both"

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
TEMPLATE_UNUSABLE = {
    "whatsapp": "Choose an active WhatsApp template", "email": "Choose an active email template",
    "linkedin": "Choose an active LinkedIn template", "call": "Choose an active calling script",
}  # fmt: skip
CAP_REACHED = f"You've sent {DAILY_CAP} WhatsApp messages today"
EMAIL_CAP_REACHED = f"You've sent {EMAIL_DAILY_CAP} emails today"
EMAIL_NOT_CONFIGURED = "Email is not set up. Ask an administrator to configure SMTP."
# pob-005 D7: logging a reply
MESSAGE_NOT_FOUND = "Message not found"
REPLY_CONTACT_ONLY = "Only a message to a company contact can be marked as replied"
REPLY_FUTURE = "The reply time can't be in the future"
REPLY_BEFORE_SENT = "The reply can't be earlier than the message"
# pob-007 (DEC-SCOPE-422 A1/A3): LinkedIn logging and a message's outcome
LINKEDIN_CAP_REACHED = f"You've logged {DAILY_CAP} LinkedIn messages today"
LINKEDIN_BODY_MISSING = "Write the message you sent"
FOLLOW_UP_CANDIDATE = "Follow-ups belong to a company: add one on a contact's message"
OUTCOME_CONTACT_ONLY = "Only a message to a company contact can have an outcome and a follow-up"
OUTCOME_RECORDED = "This message's outcome is already recorded"
SENT_FUTURE = "The time sent can't be in the future"
SENT_TOO_OLD = f"LinkedIn activity can be logged up to {BACKDATE_DAYS} days back"

RM = RecruiterMessage
NOT_FAILED = ~and_(RM.channel == "email", RM.delivery_status == "failed")


def require_template_reader(user: User) -> None:
    if user.role not in TEMPLATE_READERS:
        raise HTTPException(403, "Your role cannot view the recruiter message templates")


def require_template_writer(user: User) -> None:
    if user.role not in TEMPLATE_WRITERS:
        raise HTTPException(403, "Your role cannot change the recruiter message templates")


# --- governance (pob-023 G4-G6) -------------------------------------------------------------------------------------------------
T = RecruiterMessageTemplate


def visible(user: User):
    """G5/G6: what the caller sees -- their own personal templates; shared ones that are approved, that they wrote, or (an approver) all."""
    shared = T.owner_user_id.is_(None) if user.role in APPROVERS else and_(T.owner_user_id.is_(None), or_(T.status == "approved", T.created_by_user_id == user.id))
    return or_(shared, T.owner_user_id == user.id)


def usable_where(user: User):
    """What a composer may offer the caller: approved shared templates and their own personal ones that are not archived."""
    return or_(and_(T.owner_user_id.is_(None), T.status == "approved"), and_(T.owner_user_id == user.id, T.status != "archived"))


def is_usable(user: User, template: RecruiterMessageTemplate) -> bool:
    if template.owner_user_id is None:
        return template.status == "approved"
    return template.owner_user_id == user.id and template.status != "archived"


def manages(user: User, template: RecruiterMessageTemplate) -> bool:
    """G6: the author of a personal template; for a shared one an approver, or its author while it is not approved."""
    if template.owner_user_id is not None:
        return template.owner_user_id == user.id
    return user.role in APPROVERS or (template.created_by_user_id == user.id and template.status != "approved")


def rights(user: User, template: RecruiterMessageTemplate) -> dict[str, bool]:
    live = template.status != "archived"
    return {
        "can_edit": live and manages(user, template),
        "can_archive": live and manages(user, template),
        "can_restore": not live and manages(user, template),
        "can_approve": user.role in APPROVERS and template.owner_user_id is None and template.status == "draft",
    }


async def load_visible(db: AsyncSession, user: User, template_id: UUID, *, lock: bool = False) -> RecruiterMessageTemplate:
    """A template the caller cannot see is the same 404 as a missing one (personal templates are private)."""
    stmt = select(T).where(T.id == template_id, visible(user))
    template = await db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
    if template is None:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


def require_right(user: User, template: RecruiterMessageTemplate, right: str) -> None:
    """403 when the caller may never do it, 409 when the state is wrong (archived, or approve on a non-draft)."""
    if rights(user, template)[right]:
        return
    if right == "can_approve":
        if user.role not in APPROVERS:
            raise HTTPException(403, "Only a placement manager can approve a template")
        if template.owner_user_id is not None:
            raise HTTPException(422, "A personal template is never shared, so it cannot be approved")
        raise HTTPException(409, "Only a draft can be approved")
    if not manages(user, template):
        raise HTTPException(403, "Only a placement manager can change an approved template")
    raise HTTPException(409, "Restore this template before changing it" if template.status == "archived" else "This template is not archived")


def default_category(channel: str, kind: str | None) -> str:
    if channel in ("whatsapp", "linkedin"):
        return channel
    if channel == "call":
        return "calling"
    return "candidate" if kind in CANDIDATE_EMAIL_KINDS else "company"


def snapshot(template: RecruiterMessageTemplate) -> dict:
    return {key: getattr(template, key) for key in VERSIONED}


def add_version(db: AsyncSession, template: RecruiterMessageTemplate, user: User) -> None:
    """G7: the saved content as version `template.version`."""
    db.add(RecruiterTemplateVersion(template_id=template.id, version=template.version, content=snapshot(template), edited_by_user_id=user.id))


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


def check_template(channel: str, kind: str | None, subject: str | None, body: str, category: str | None = None, steps: list[str] | None = None) -> None:
    """The template rules, on the merged row (create, or a row plus a PATCH)."""
    if channel in ("linkedin", "call"):
        if kind is not None:
            raise HTTPException(422, f"{'LinkedIn templates' if channel == 'linkedin' else 'Calling scripts'} have no kind")
    elif kind not in KINDS_BY_CHANNEL[channel]:
        raise HTTPException(422, f"Choose {'a WhatsApp' if channel == 'whatsapp' else 'an email'} template kind")
    if category is not None and category not in REC_TEMPLATE_CATEGORIES:
        raise HTTPException(422, "Choose a category: company, LinkedIn, WhatsApp, calling, College/TPO or candidate")
    if channel != "email" and subject is not None:
        raise HTTPException(422, "Only email templates have a subject")
    if channel == "email" and subject is None:
        raise HTTPException(422, "Subject is required")
    if channel == "call" and not steps:
        raise HTTPException(422, "A calling script needs at least one step")
    if channel != "call" and steps is not None:
        raise HTTPException(422, "Only calling scripts have steps")
    if steps and len(steps) > STEPS_MAX:
        raise HTTPException(422, f"A calling script has at most {STEPS_MAX} steps")
    if len(body) > BODY_LIMIT[channel]:
        raise HTTPException(422, f"{CHANNEL_NOUN[channel]} message must be at most {BODY_LIMIT[channel]} characters")
    check_placeholders(subject, body, *(steps or ()))


def _person(users: dict, user_id) -> dict | None:
    person = users.get(user_id)
    return {"id": person.id, "full_name": person.full_name} if person else None


def template_out(template: RecruiterMessageTemplate, user: User, users: dict) -> dict:
    """rec-026's fields plus pob-023's; `users` maps the authors' ids to rows (one query per page, see `templates_out`)."""
    out = {k: getattr(template, k) for k in ("id", "channel", "kind", "name", "subject", "body", "active", "category", "purpose", "language")}
    out |= {k: getattr(template, k) for k in ("department", "industry", "role_type", "status", "steps", "version", "created_at", "updated_at", "last_used_at")}
    out |= {
        "visibility": "personal" if template.owner_user_id else "shared",
        "created_by": _person(users, template.created_by_user_id),
        "updated_by": _person(users, template.updated_by_user_id),
    }
    return out | rights(user, template)


async def templates_out(db: AsyncSession, user: User, templates: list[RecruiterMessageTemplate]) -> list[dict]:
    ids = {i for t in templates for i in (t.created_by_user_id, t.updated_by_user_id) if i}
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}
    return [template_out(t, user, users) for t in templates]


def rendered(template: RecruiterMessageTemplate, values: dict[str, str]) -> dict:
    """QA-02: `missing` names the placeholders the template uses that had no value (e.g. {company} for a candidate), so the composer can
    ask the recruiter to check the text. pob-023 G1: a calling script's steps are rendered too."""
    used = check_placeholders(template.subject, template.body, *(template.steps or ()))
    return {
        "subject": render(template.subject, values) if template.subject is not None else None,
        "body": render(template.body, values),
        "steps": [render(step, values) for step in template.steps] if template.steps is not None else None,
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
    values = {"name": (contact or candidate).name, "company": company.name if company else "", "recruiter": user.full_name}
    values["designation"] = (contact.designation or "") if contact else ""  # pob-023 G8
    values["candidate"] = candidate.name if candidate else ""
    return values


def package_range(job: Job) -> str:
    """G8: the requirement's salary range, e.g. "INR 600,000 – 900,000 a year"; empty when it has none."""
    low, high = job.salary_min, job.salary_max
    if low is None and high is None:
        return ""
    money = lambda value: f"{value:,.0f}"  # noqa: E731
    amount = f"{money(low)} – {money(high)}" if low is not None and high is not None else (f"from {money(low)}" if high is None else f"up to {money(high)}")
    return f"{job.salary_currency or 'INR'} {amount} a {job.salary_period or 'year'}"


def interview_values(interview: Interview) -> dict[str, str]:
    """G8: an interview's placeholders, in the candidate's time zone (pob-022 reuses them for its confirmation, reminders and chase)."""
    local = interview.scheduled_at.astimezone(ZoneInfo(interview.time_zone or "Asia/Kolkata"))
    return {
        "interview_date": local.strftime("%d %b %Y"), "interview_time": local.strftime("%I:%M %p").lstrip("0"),
        "interview_mode": interview.mode or "", "interview_link": interview.meeting_url or interview.location or "",
    }  # fmt: skip


async def context_values(db: AsyncSession, user: User, company: Company | None, candidate: Candidate | None, job_id: UUID | None, interview_id: UUID | None) -> dict[str, str]:
    """G8/G9: the values of an optional requirement or interview -- each through its own scope (404), and only for the party it is about:
    a contact's requirement must be at the contact's company; an interview must be the candidate's, or at the contact's company."""
    if job_id and interview_id:
        raise HTTPException(422, CONTEXT_BOTH)
    values: dict[str, str] = {}
    if interview_id:
        application_id = await db.scalar(select(Interview.application_id).where(Interview.id == interview_id))
        try:
            application, job = await applications.load_scoped(db, user, application_id) if application_id else (None, None)
        except HTTPException:
            application = None
        if application is None or (candidate and application.candidate_id != candidate.id) or (company and job.company_id != company.id):
            raise HTTPException(404, "Interview not found")
        values |= interview_values(await db.get(Interview, interview_id))
        if candidate is None and application.candidate_id:
            values["candidate"] = await db.scalar(select(Candidate.name).where(Candidate.id == application.candidate_id)) or ""
    elif job_id:
        try:
            job = await requirements.load_scoped(db, user, job_id)
        except HTTPException:
            job = None
        if job is None or (company and job.company_id != company.id):
            raise HTTPException(404, requirements.NOT_FOUND)
    else:
        return values
    values |= {"job_title": job.title, "job_location": job.location or ""}
    values["package_range"] = package_range(job) if await recruiter_contracts.sees_commercials(db, user) else ""  # pob-001 grant
    return values


async def usable_template(db: AsyncSession, user: User, template_id: UUID) -> RecruiterMessageTemplate:
    """A template the caller may use in a composer (G5); anything else is 404."""
    template = await db.get(RecruiterMessageTemplate, template_id)
    if template is None or not is_usable(user, template):
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


async def mark_used(db: AsyncSession, template_id: UUID, now: datetime) -> None:
    """G7: the template's last-used time -- a use is not an edit, so `updated_at` keeps its value."""
    await db.execute(update(T).where(T.id == template_id).values(last_used_at=now, updated_at=T.updated_at))


async def copy(db: AsyncSession, user: User, payload: RecTemplateCopy, now: datetime) -> dict:
    """G10: a LinkedIn message or calling script copied for a party -- the send's party rules (scope 404, right 403, state 409, Do Not
    Contact 409), a usable template of that channel (422), then an audit row with ids only. Not a message: no last-contacted, no cap."""
    company, contact, candidate = await load_party(db, user, payload.contact_id, payload.candidate_id, write=True)
    if contact:
        contact_status.refuse_do_not_contact(contact)  # pob-005 D6
    template = await db.get(RecruiterMessageTemplate, payload.template_id)
    if template is None or not is_usable(user, template) or template.channel != payload.channel:
        raise HTTPException(422, TEMPLATE_UNUSABLE[payload.channel])
    party, kind = (contact, "contact") if contact else (candidate, "candidate")
    await mark_used(db, template.id, now)
    db.add(AuditLog(user_id=user.id, action="recruiter_template.copy", entity_type="recruiter_message_template", entity_id=str(template.id),
                    metadata_json={"channel": payload.channel, "kind": kind, "party_id": str(party.id)}))
    return {"template_id": template.id, "channel": payload.channel, "copied_at": now}


# --- send and read --------------------------------------------------------------------------------------------------------------
async def check_cap(db: AsyncSession, user: User, channel: str, now: datetime) -> None:
    """MS8: the sender's per-IST-day cap for the channel (409 WhatsApp / 429 email). rec-019's shares count too."""
    start, end = day_range(today_ist(now))
    count = await db.scalar(select(func.count()).select_from(RM).where(RM.sender_user_id == user.id, RM.channel == channel, RM.sent_at >= start, RM.sent_at < end))
    cap, status, detail = (EMAIL_DAILY_CAP, 429, EMAIL_CAP_REACHED) if channel == "email" else (DAILY_CAP, 409, LINKEDIN_CAP_REACHED if channel == "linkedin" else CAP_REACHED)
    if (count or 0) >= cap:
        raise HTTPException(status, detail)


async def create(db: AsyncSession, user: User, payload: RecWhatsAppCreate | RecEmailCreate, now: datetime) -> RecruiterMessage:
    """The error order of spec §3: role and scope, the party lock, the right and state; SMTP unset 503; no number / address 409; the
    template 422; the cap 409 / 429. An email is stored `queued`; the route publishes it after the commit (MS7)."""
    company, contact, candidate = await load_party(db, user, payload.contact_id, payload.candidate_id, write=True)
    if contact:
        contact_status.refuse_do_not_contact(contact)  # pob-005 D6
    party, kind = (contact, "contact") if contact else (candidate, "candidate")
    is_email = isinstance(payload, RecEmailCreate)
    if is_email and not mailer.smtp_configured():
        raise HTTPException(503, EMAIL_NOT_CONFIGURED)
    if is_email and not party.email:
        raise HTTPException(409, NO_EMAIL[kind])
    if not is_email and wa_number(party.mobile) is None:
        raise HTTPException(409, NO_NUMBER[kind])
    template = await db.get(RecruiterMessageTemplate, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not is_usable(user, template) or template.channel != payload.channel):
        raise HTTPException(422, TEMPLATE_UNUSABLE[payload.channel])
    await check_cap(db, user, payload.channel, now)
    if template:
        await mark_used(db, template.id, now)
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
    await companies.refresh_last_contact(db, message.company_id)  # pob-003 D4
    await contact_status.advance(db, user, [message.contact_id], "contacted", "message")  # pob-005 D4
    audit(db, user, message.id, {"kind": kind, "party_id": str(party.id), "channel": message.channel, "template_id": str(template.id) if template else None})
    return message


async def log_reply(db: AsyncSession, user: User, message_id: UUID, replied_at: datetime | None, now: datetime) -> UUID:
    """pob-005 D7: a reply the contact sent, recorded by hand on the message. Scope and write right are the contact's company's (404 / 403 /
    409 archived); a candidate message is 422. Set once: a repeat changes nothing (no audit). Moves the contact to Replied (D4); a Do Not
    Contact person's reply is still recorded."""
    contact_id = await db.scalar(select(RM.contact_id).where(RM.id == message_id))
    if contact_id is None:
        if await db.scalar(select(RM.id).where(RM.id == message_id)) is None:
            await companies.caller_scope(db, user)  # the role check (403) comes before "not found"
            raise HTTPException(404, MESSAGE_NOT_FOUND)
        raise HTTPException(422, REPLY_CONTACT_ONLY)
    try:
        company, contact, _ = await load_party(db, user, contact_id, None)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, MESSAGE_NOT_FOUND) from None
        raise
    await db.execute(select(Company.id).where(Company.id == company.id).with_for_update())
    companies.require(user, company, "can_edit", "message_reply")
    message = await db.scalar(select(RM).where(RM.id == message_id).with_for_update().execution_options(populate_existing=True))
    if message.replied_at is not None:
        return message.id
    at = replied_at or now
    if at > now + timedelta(minutes=1):
        raise HTTPException(422, REPLY_FUTURE)
    if at < message.sent_at:
        raise HTTPException(422, REPLY_BEFORE_SENT)
    message.replied_at = at
    await db.flush()
    await contact_status.advance(db, user, [contact.id], "replied", "reply")
    await contact_status.end_cadences(db, [contact.id], "replied", "reply")  # pob-008 B9 (AC3), also when the status had already moved
    db.add(AuditLog(user_id=user.id, action="recruiter_message.reply", entity_type="recruiter_message", entity_id=str(message.id), metadata_json={"contact_id": str(contact.id)}))
    return message.id


def _field(field: str, msg: str) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": None}])


async def log_linkedin(db: AsyncSession, user: User, payload: RecLinkedInCreate, now: datetime) -> RecruiterMessage:
    """pob-007 A1: LinkedIn outreach done by hand. The send's party rules (scope 404, right 403, state 409, Do Not Contact 409); the text
    (a message needs one, 422); the time (lead_calls' rule: not ahead, at most 7 days back); a usable LinkedIn template (422); the cap
    (409). It is outreach: last contacted, the contact's status and an optional next follow-up (rec-024's rules) move with it."""
    company, contact, candidate = await load_party(db, user, payload.contact_id, payload.candidate_id, write=True)
    if contact:
        contact_status.refuse_do_not_contact(contact)
    elif payload.next_follow_up is not None:
        raise _field("next_follow_up", FOLLOW_UP_CANDIDATE)
    if payload.action == "message" and not payload.body:
        raise _field("body", LINKEDIN_BODY_MISSING)
    sent_at = payload.sent_at or now  # the call form's rule (lead_calls.check_time), placed on `sent_at`
    if sent_at > now + CLOCK_TOLERANCE:
        raise _field("sent_at", SENT_FUTURE)
    if today_ist(sent_at) < today_ist(now) - timedelta(days=BACKDATE_DAYS):
        raise _field("sent_at", SENT_TOO_OLD)
    sent_at = min(sent_at, now)
    template = await db.get(RecruiterMessageTemplate, payload.template_id) if payload.template_id else None
    if payload.template_id and (template is None or not is_usable(user, template) or template.channel != "linkedin"):
        raise HTTPException(422, TEMPLATE_UNUSABLE["linkedin"])
    await check_cap(db, user, "linkedin", now)
    if template:
        await mark_used(db, template.id, now)
    party, kind = (contact, "contact") if contact else (candidate, "candidate")
    message = RM(
        company_id=company.id if company else None, contact_id=contact.id if contact else None, candidate_id=candidate.id if candidate else None,
        sender_user_id=user.id, channel="linkedin", linkedin_action=payload.action, template_id=payload.template_id,
        template_name=template.name if template else None, body=payload.body, sent_at=sent_at,
    )
    db.add(message)
    await db.flush()
    await companies.refresh_last_contact(db, message.company_id)  # pob-003 D4
    await contact_status.advance(db, user, [message.contact_id], "contacted", "message")  # pob-005 D4
    if payload.next_follow_up is not None:
        fu = await follow_ups.create(db, user, company, RecFollowUpCreate(**payload.next_follow_up.model_dump(), contact_id=contact.id), now)
        message.follow_up_id = fu.id
    audit(db, user, message.id, {"kind": kind, "party_id": str(party.id), "channel": "linkedin", "action": payload.action,
                                 "template_id": str(template.id) if template else None, "follow_up_id": str(message.follow_up_id) if message.follow_up_id else None})
    return message


async def record_outcome(db: AsyncSession, user: User, message_id: UUID, payload: RecMessageOutcome, now: datetime) -> UUID:
    """pob-007 A3: what came of a contact message, once, with an optional next follow-up. The reply's scope and right (404 / 403 / 409
    archived); a candidate message is 422; a second outcome is 409 under the message lock."""
    contact_id = await db.scalar(select(RM.contact_id).where(RM.id == message_id))
    if contact_id is None:
        if await db.scalar(select(RM.id).where(RM.id == message_id)) is None:
            await companies.caller_scope(db, user)  # the role check (403) comes before "not found"
            raise HTTPException(404, MESSAGE_NOT_FOUND)
        raise HTTPException(422, OUTCOME_CONTACT_ONLY)
    try:
        company, contact, _ = await load_party(db, user, contact_id, None)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, MESSAGE_NOT_FOUND) from None
        raise
    company = await companies.load_scoped(db, user, company.id, lock=True)
    companies.require(user, company, "can_edit", "message_outcome")
    message = await db.scalar(select(RM).where(RM.id == message_id).with_for_update().execution_options(populate_existing=True))
    if message.outcome is not None:
        raise HTTPException(409, OUTCOME_RECORDED)
    if payload.next_follow_up is not None:
        values = payload.next_follow_up.model_dump() | {"contact_id": contact.id if contact.active else None}
        message.follow_up_id = (await follow_ups.create(db, user, company, RecFollowUpCreate(**values), now)).id
    message.outcome = payload.outcome
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="recruiter_message.outcome", entity_type="recruiter_message", entity_id=str(message.id),
                    metadata_json={"contact_id": str(contact.id), "follow_up_id": str(message.follow_up_id) if message.follow_up_id else None}))
    return message.id


def _rows():
    """One query: the message, its sender, the contact or candidate, and (pob-007) its follow-up -- no N+1."""
    return (
        select(RM, User, CompanyContact, Candidate, RecruiterFollowUp)
        .join(User, User.id == RM.sender_user_id)
        .outerjoin(CompanyContact, CompanyContact.id == RM.contact_id)
        .outerjoin(Candidate, Candidate.id == RM.candidate_id)
        .outerjoin(RecruiterFollowUp, RecruiterFollowUp.id == RM.follow_up_id)
    )


def out(message: RecruiterMessage, sender: User, contact: CompanyContact | None, candidate: Candidate | None, fu: RecruiterFollowUp | None = None) -> dict:
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
        "replied_at": message.replied_at,  # pob-005 D7
        # pob-007 A1/A3
        "linkedin_action": message.linkedin_action, "outcome": message.outcome,
        "follow_up": {"id": fu.id, "due_at": fu.due_at, "reason": fu.reason} if fu else None,
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
