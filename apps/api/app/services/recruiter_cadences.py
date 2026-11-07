"""pob-008 (DEC-SCOPE-423 B1-B10): recruiter follow-up reminders and outreach cadences -- the reminder sweep (once per follow-up, to the
company's current owner), the Team Lead's cadence library, a contact's run of a cadence started on an outreach message, the cadence sweep
that turns "no reply yet" into the next step's follow-up, and the first-outreach follow-up of a new company or contact.

Each sweep takes a bounded batch with `FOR UPDATE SKIP LOCKED` and writes its marker in the transaction of its notice or follow-up: both or
neither, so a rerun adds nothing (pob-022's pattern). A follow-up's edit holds its lock, and a reply / status change ends the run in its own
transaction (contact_status.end_cadences), so neither races a sweep over the same row. Logs and audit carry ids and counts only."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    Company,
    CompanyContact,
    RecruiterCadence,
    RecruiterContactCadence,
    RecruiterFollowUp,
    RecruiterMessage,
    RecruiterMessageTemplate,
    User,
)
from app.notifications.events import notify
from app.schemas import RecCadenceCreate, RecCadenceUpdate
from app.services import contact_status
from app.services import recruiter_companies as companies
from app.services import recruiter_messages as messages
from app.services.recruiter import MANAGER_ROLE
from app.services.recruiter_follow_ups import OPEN_CAP

logger = logging.getLogger("app.recruiter")

FU, RUN = RecruiterFollowUp, RecruiterContactCadence
EDITORS = frozenset({MANAGER_ROLE, "super_admin"})  # pob-001: the Team Lead is the placement manager
DUE_EVENT = "it.recruiter.follow_up_due"
FOLLOW_UPS_URL = "/recruiter/follow-ups"
REMIND_LEAD = timedelta(minutes=30)  # B1: a follow-up without its own reminder time is reminded 30 minutes before it is due
FIRST_OUTREACH_AFTER = timedelta(hours=24)  # B10
SWEEP_LIMIT = 200
CHANNEL_LABELS = {"email": "Email", "whatsapp": "WhatsApp", "linkedin": "LinkedIn", "call": "Call"}
REPLIED = ("replied", "meeting_scheduled")

NOT_ALLOWED = "Only a Team Lead can change outreach cadences"
NOT_FOUND = "Cadence not found"
NAME_TAKEN = "A cadence with this name already exists"
TEMPLATE_INVALID = "Step {n}: choose an approved shared {channel} template"
CADENCE_INVALID = "Choose an active cadence"
CONTACT_ONLY = "Only a message to a company contact can start a cadence"
CONTACT_INACTIVE = "This contact is inactive"
NOT_INTERESTED = "This contact is not interested"
ALREADY_REPLIED = "This contact has already replied"
ALREADY_RUNNING = "This contact already follows a cadence"
NOT_RUNNING = "No cadence is running on this message"


# --- B2 the owner -----------------------------------------------------------------------------------------------------------------------
async def _owner(db: AsyncSession, company: Company, fallback_id: UUID | None) -> User | None:
    """The company's assigned recruiter when active (a reassignment moves reminders and cadences with it), else `fallback_id` when active."""
    for user_id in (company.assigned_recruiter_user_id, fallback_id):
        user = await db.get(User, user_id) if user_id else None
        if user is not None and user.active:
            return user
    return None


# --- B1/B3 reminders (AC1) --------------------------------------------------------------------------------------------------------------
async def run_follow_up_reminders(now: datetime | None = None) -> dict[str, int]:
    """An open follow-up of an open company, not yet reminded, whose reminder time has come (its own `remind_at`, else 30 minutes before
    it is due -- an overdue one too) gets one notice to its owner. Soonest first; one with no owner waits for a later run."""
    now = now or datetime.now(UTC)
    reminded = 0
    async with SessionLocal() as db:
        due = (await db.execute(
            select(FU, Company)
            .join(Company, Company.id == FU.company_id)
            .where(FU.status == "open", FU.reminded_at.is_(None), Company.archived_at.is_(None), Company.merged_into_id.is_(None),
                   or_(FU.remind_at <= now, and_(FU.remind_at.is_(None), FU.due_at <= now + REMIND_LEAD)))
            .order_by(FU.due_at, FU.id)
            .limit(SWEEP_LIMIT)
            .with_for_update(of=FU, skip_locked=True)
        )).all()  # fmt: skip
        for fu, company in due:
            owner = await _owner(db, company, fu.created_by_user_id)
            if owner is None:
                continue
            await notify(db, [owner], DUE_EVENT, fu.id, action_url=FOLLOW_UPS_URL)
            fu.reminded_at = now
            reminded += 1
        await db.commit()
    counts = {"reminded": reminded}
    logger.info("recruiter_follow_up_reminder_sweep", extra={"extra_fields": counts})
    return counts


# --- B5 the library -----------------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    """Every recruiter-CRM role reads the library (the outreach picker); anyone else is 403 (rec-003's role check)."""
    await companies.caller_scope(db, user)


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, NOT_ALLOWED)


def _steps_error(msg: str) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", "steps"), "msg": msg, "input": None}])


async def _check_templates(db: AsyncSession, steps: list[dict]) -> None:
    """Each chosen template is an approved shared template of its step's channel (pob-023 G4/G5), else 422 on `steps`."""
    ids = {s["template_id"] for s in steps if s["template_id"]}
    found = {t.id: t for t in (await db.scalars(select(RecruiterMessageTemplate).where(RecruiterMessageTemplate.id.in_(ids)))).all()} if ids else {}
    for n, step in enumerate(steps, start=1):
        if step["template_id"] is None:
            continue
        t = found.get(step["template_id"])
        if t is None or t.owner_user_id is not None or t.status != "approved" or t.channel != step["channel"]:
            raise _steps_error(TEMPLATE_INVALID.format(n=n, channel=CHANNEL_LABELS[step["channel"]]))


def _stored(steps) -> list[dict]:
    return [{"day": s.day, "channel": s.channel, "template_id": str(s.template_id) if s.template_id else None} for s in steps]


async def _template_names(db: AsyncSession, cadences: list[RecruiterCadence]) -> dict[str, str]:
    ids = {UUID(s["template_id"]) for c in cadences for s in c.steps if s.get("template_id")}
    if not ids:
        return {}
    rows = await db.execute(select(RecruiterMessageTemplate.id, RecruiterMessageTemplate.name).where(RecruiterMessageTemplate.id.in_(ids)))
    return {str(i): name for i, name in rows.tuples().all()}


def cadence_out(cadence: RecruiterCadence, names: dict[str, str], user: User) -> dict:
    return {
        "id": cadence.id, "name": cadence.name, "description": cadence.description, "active": cadence.active,
        "steps": [{"day": s["day"], "channel": s["channel"],
                   "template": {"id": s["template_id"], "name": names.get(s["template_id"], "")} if s.get("template_id") else None} for s in cadence.steps],
        "updated_at": cadence.updated_at, "can_edit": user.role in EDITORS,
    }  # fmt: skip


async def list_out(db: AsyncSession, user: User, include_inactive: bool) -> dict:
    query = select(RecruiterCadence).order_by(func.lower(RecruiterCadence.name), RecruiterCadence.id)
    if not include_inactive:
        query = query.where(RecruiterCadence.active)
    rows = list((await db.scalars(query)).all())
    names = await _template_names(db, rows)
    return {"items": [cadence_out(c, names, user) for c in rows], "can_edit": user.role in EDITORS}


async def one_out(db: AsyncSession, user: User, cadence: RecruiterCadence) -> dict:
    await db.refresh(cadence)
    return cadence_out(cadence, await _template_names(db, [cadence]), user)


async def _flush_named(db: AsyncSession) -> None:
    """The case-insensitive unique name index is the one check: a clash (or a concurrent save of the same name) is 409."""
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, NAME_TAKEN) from None


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


async def create(db: AsyncSession, user: User, payload: RecCadenceCreate) -> RecruiterCadence:
    require_editor(user)
    steps = [s.model_dump() for s in payload.steps]
    await _check_templates(db, steps)
    cadence =RecruiterCadence(name=payload.name, description=payload.description, steps=_stored(payload.steps), created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(cadence)
    await _flush_named(db)
    _audit(db, user, "recruiter_cadence.create", "recruiter_cadence", cadence.id, {"steps": len(steps)})
    return cadence


async def update(db: AsyncSession, user: User, cadence_id: UUID, payload: RecCadenceUpdate) -> RecruiterCadence:
    """Only the keys sent; values equal to the stored ones are not changes (no audit). A run in progress keeps its snapshot (B6)."""
    require_editor(user)
    cadence = await db.get(RecruiterCadence, cadence_id, with_for_update=True, populate_existing=True)
    if cadence is None:
        raise HTTPException(404, NOT_FOUND)
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k == "description"}
    if "steps" in changes:
        await _check_templates(db, changes["steps"])
        changes["steps"] = _stored(payload.steps)
    changed = sorted(k for k, v in changes.items() if getattr(cadence, k) != v)
    for key in changed:
        setattr(cadence, key, changes[key])
    if changed:
        cadence.updated_by_user_id = user.id
        await _flush_named(db)
        _audit(db, user, "recruiter_cadence.update", "recruiter_cadence", cadence.id, {"fields": changed})
    return cadence


# --- B6/B9 a run on an outreach message ---------------------------------------------------------------------------------------------------
async def _contact_message(db: AsyncSession, user: User, message_id: UUID, route: str) -> tuple[Company, CompanyContact, RecruiterMessage]:
    """pob-005 log_reply's order: role 403 -> 404 -> candidate 422 -> the company lock -> right 403 / archived 409 -> the message lock."""
    contact_id = await db.scalar(select(RecruiterMessage.contact_id).where(RecruiterMessage.id == message_id))
    if contact_id is None:
        if await db.scalar(select(RecruiterMessage.id).where(RecruiterMessage.id == message_id)) is None:
            await companies.caller_scope(db, user)
            raise HTTPException(404, messages.MESSAGE_NOT_FOUND)
        raise HTTPException(422, CONTACT_ONLY)
    try:
        company, contact, _ = await messages.load_party(db, user, contact_id, None)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, messages.MESSAGE_NOT_FOUND) from None
        raise
    company = await companies.load_scoped(db, user, company.id, lock=True)
    companies.require(user, company, "can_edit", route)
    message = await db.scalar(select(RecruiterMessage).where(RecruiterMessage.id == message_id).with_for_update().execution_options(populate_existing=True))
    contact = await db.get(CompanyContact, contact.id, populate_existing=True)
    return company, contact, message


async def start(db: AsyncSession, user: User, message_id: UUID, cadence_id: UUID) -> RUN:
    """The message is step 1 (day 0); the run keeps a snapshot of the cadence. One active run per contact (409)."""
    company, contact, message = await _contact_message(db, user, message_id, "cadence_start")
    cadence = await db.get(RecruiterCadence, cadence_id)
    if cadence is None or not cadence.active:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "cadence_id"), "msg": CADENCE_INVALID, "input": str(cadence_id)}])
    contact_status.refuse_do_not_contact(contact)
    if not contact.active:
        raise HTTPException(409, CONTACT_INACTIVE)
    if contact.status == "not_interested":
        raise HTTPException(409, NOT_INTERESTED)
    if message.replied_at is not None or contact.status in REPLIED:
        raise HTTPException(409, ALREADY_REPLIED)
    if await db.scalar(select(RUN.id).where(RUN.contact_id == contact.id, RUN.status == "active")) is not None:
        raise HTTPException(409, ALREADY_RUNNING)
    steps = list(cadence.steps)
    run = RUN(cadence_id=cadence.id, contact_id=contact.id, company_id=company.id, message_id=message.id, name=cadence.name, steps=steps, step=1,
              started_at=message.sent_at, started_by_user_id=user.id, next_step_at=message.sent_at + timedelta(days=steps[1]["day"]))  # fmt: skip
    db.add(run)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:  # the partial unique index: a concurrent start won (the company lock makes this rare)
        raise HTTPException(409, ALREADY_RUNNING) from None
    _audit(db, user, "recruiter_cadence.start", "recruiter_contact_cadence", run.id,
           {"cadence_id": str(cadence.id), "contact_id": str(contact.id), "message_id": str(message.id)})  # fmt: skip
    return run


def _end(run: RUN, status: str, reason: str, now: datetime) -> None:
    run.status, run.end_reason, run.ended_at, run.next_step_at = status, reason, now, None


async def stop(db: AsyncSession, user: User, message_id: UUID, now: datetime) -> RUN:
    """B9: a stop by hand (`manual`); 409 when no run on this message is active."""
    await _contact_message(db, user, message_id, "cadence_stop")
    run = await db.scalar(select(RUN).where(RUN.message_id == message_id, RUN.status == "active").with_for_update().execution_options(populate_existing=True))
    if run is None:
        raise HTTPException(409, NOT_RUNNING)
    _end(run, "stopped", "manual", now)
    _audit(db, user, "recruiter_cadence.stop", "recruiter_contact_cadence", run.id, {"contact_id": str(run.contact_id)})
    return run


def run_out(run: RUN | None, can_edit: bool) -> dict | None:
    if run is None:
        return None
    return {"id": run.id, "cadence_id": run.cadence_id, "name": run.name, "status": run.status, "step": run.step, "steps": len(run.steps),
            "next_step_at": run.next_step_at, "end_reason": run.end_reason, "ended_at": run.ended_at, "can_stop": run.status == "active" and can_edit}  # fmt: skip


async def attach(db: AsyncSession, user: User, company: Company | None, items: list[dict]) -> None:
    """Message output gains `cadence`: the run started on that message (the latest), else null -- one query for the page."""
    ids = [m["id"] for m in items]
    runs: dict = {}
    if company is not None and ids:
        for run in (await db.scalars(select(RUN).where(RUN.message_id.in_(ids)).order_by(RUN.created_at).execution_options(populate_existing=True))).all():
            runs[run.message_id] = run
    can_edit = company is not None and companies.permissions(user, company)["can_edit"]
    for item in items:
        item["cadence"] = run_out(runs.get(item["id"]), can_edit)


async def one_message(db: AsyncSession, user: User, company: Company, message_id: UUID) -> dict:
    out = await messages.one(db, message_id)
    await attach(db, user, company, [out])
    return out


# --- B8 the cadence sweep (AC2, AC3) ------------------------------------------------------------------------------------------------------
async def _end_reason(db: AsyncSession, run: RUN, contact: CompanyContact, company: Company) -> tuple[str, str] | None:
    if not contact.active:
        return "stopped", "inactive"
    if contact.status in ("do_not_contact", "not_interested"):
        return "stopped", contact.status
    replied = exists(select(RecruiterMessage.id).where(RecruiterMessage.contact_id == contact.id, RecruiterMessage.replied_at.is_not(None),
                                                       RecruiterMessage.sent_at >= run.started_at))  # fmt: skip
    if contact.status in REPLIED or await db.scalar(select(replied)):
        return "replied", "reply"
    if company.archived_at is not None or company.merged_into_id is not None:
        return "stopped", "archived"
    return None


async def _step_notes(db: AsyncSession, run: RUN, step: dict, owner: User, company: Company, contact: CompanyContact) -> str:
    """"‹cadence› — step k of n: ‹channel›", then the step's template (still approved) rendered for the contact (pob-023's renderer)."""
    notes = f"{run.name} — step {run.step + 1} of {len(run.steps)}: {CHANNEL_LABELS[step['channel']]}"
    template = await db.get(RecruiterMessageTemplate, UUID(step["template_id"])) if step.get("template_id") else None
    if template is None or template.status != "approved":
        return notes
    text = messages.rendered(template, messages.party_values(owner, company, contact, None))
    body = f"Subject: {text['subject']}\n\n{text['body']}" if text["subject"] else text["body"]
    if text["steps"]:
        body += "\n" + "\n".join(f"- {s}" for s in text["steps"])
    return f"{notes}\nTemplate: {template.name}\n\n{body}"


async def run_cadences(now: datetime | None = None) -> dict[str, int]:
    """An active run whose next step is due: ended first when the contact replied or left (the safety net behind B9), else the next step
    becomes a follow-up for the company's current owner; the last step completes the run. One step per run per sweep, earliest first."""
    now = now or datetime.now(UTC)
    stepped = ended = 0
    async with SessionLocal() as db:
        due = (await db.execute(
            select(RUN, CompanyContact, Company)
            .join(CompanyContact, CompanyContact.id == RUN.contact_id)
            .join(Company, Company.id == RUN.company_id)
            .where(RUN.status == "active", RUN.next_step_at <= now)
            .order_by(RUN.next_step_at, RUN.id)
            .limit(SWEEP_LIMIT)
            .with_for_update(of=RUN, skip_locked=True)
        )).all()  # fmt: skip
        for run, contact, company in due:
            if (end := await _end_reason(db, run, contact, company)) is not None:
                _end(run, *end, now)
                ended += 1
                continue
            owner = await _owner(db, company, run.started_by_user_id)
            if owner is None:  # nobody to act on it: left for a later run
                continue
            step = run.steps[run.step]
            fu = FU(company_id=company.id, contact_id=contact.id, reason="cadence_step", due_at=max(now, run.started_at + timedelta(days=step["day"])),
                    notes=await _step_notes(db, run, step, owner, company, contact), created_by_user_id=owner.id)  # fmt: skip
            db.add(fu)
            await db.flush()
            run.step += 1
            run.last_follow_up_id = fu.id
            stepped += 1
            if run.step >= len(run.steps):
                _end(run, "completed", "last_step", now)
                ended += 1
            else:
                run.next_step_at = run.started_at + timedelta(days=run.steps[run.step]["day"])
        await db.commit()
    counts = {"steps": stepped, "ended": ended}
    logger.info("recruiter_cadence_sweep", extra={"extra_fields": counts})
    return counts


# --- B10 first outreach -----------------------------------------------------------------------------------------------------------------
async def first_outreach(db: AsyncSession, user: User, company: Company, contact: CompanyContact | None, now: datetime) -> None:
    """§16 "New company/contact created → create a follow-up task": one open follow-up due in 24 hours, about the new contact when there is
    one. None for a contact who is inactive, Do Not Contact or Not interested, nor past the company's FU8 cap. The caller holds the company
    lock and owns the transaction."""
    if contact is not None and (not contact.active or contact.status in ("do_not_contact", "not_interested")):
        return
    if (await db.scalar(select(func.count()).select_from(FU).where(FU.company_id == company.id, FU.status == "open")) or 0) >= OPEN_CAP:
        return
    fu = FU(company_id=company.id, contact_id=contact.id if contact else None, reason="first_outreach", due_at=now + FIRST_OUTREACH_AFTER,
            created_by_user_id=user.id)  # fmt: skip
    db.add(fu)
    await db.flush()
    _audit(db, user, "recruiter_follow_up.create", "recruiter_follow_up", fu.id, {"company_id": str(company.id), "reason": "first_outreach", "automatic": True})


def log(event: str, user: User, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entity_id": str(entity_id), **extra}})
