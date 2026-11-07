"""rec-026 (DEC-SCOPE-135, spec §3): the recruiter message templates (the placement manager's global library, MS3) and messages to a company
contact or a candidate -- render, send (WhatsApp logged on confirm, email queued for the worker) and the company's and candidate's lists.

Template bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-012 idiom); the
role check runs before the body is read. Every write is one transaction -- role, scope and lock, rules, change, audit, one commit here, then
(an email) the publish and the log line."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import RecruiterMessage, RecruiterMessageTemplate, RecruiterTemplateVersion, User
from app.notifications.dispatch import enqueue_recruiter_email
from app.schemas import (
    TEL_CONTENT_FIELD_LABELS,
    RecLinkedInCreate,
    RecMessageCreate,
    RecMessageOutcome,
    RecMessageReply,
    RecTemplateChannel,
    RecTemplateCopy,
    RecTemplateCreate,
    RecTemplateUpdate,
)
from app.services import candidates, recruiter_cadences
from app.services import recruiter_companies as companies
from app.services import recruiter_messages as svc
from app.services.bdm_appointments import db_now
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, audit

router = APIRouter(prefix="/recruiter", tags=["recruiter-messages"])
T = RecruiterMessageTemplate
# WhatsApp before email, then the source's kind order (§19), then name.
KIND_ORDER = case(*((T.kind == kind, index) for index, kind in enumerate(dict.fromkeys(svc.REC_WHATSAPP_KINDS + svc.REC_EMAIL_KINDS))), else_=99)


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CONTENT_FIELD_LABELS)


def _taken(channel: str, name: str) -> str:
    return f"{svc.CHANNEL_NOUN[channel]} template named “{name}” already exists"  # QA-01


# --- templates (MS1-MS3; pob-023 G1-G7) -----------------------------------------------------------------------------------------
async def _flush_name(db: AsyncSession, template) -> None:
    """The unique indexes decide a duplicate name (shared per channel, personal per author and channel), even under a race."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if svc.TEMPLATE_NAME_INDEX in str(exc.orig) or svc.OWNER_NAME_INDEX in str(exc.orig):
            raise HTTPException(409, _taken(template.channel, template.name)) from None
        raise


async def _one_out(db: AsyncSession, user: User, template) -> dict:
    """After the commit: reload the row (its `updated_at` is set by the database)."""
    await db.refresh(template)
    return (await svc.templates_out(db, user, [template]))[0]


@router.get("/templates")
async def list_templates(
    channel: RecTemplateChannel | None = None,
    active: bool | None = None,
    category: str | None = None,
    status: Literal["draft", "approved", "archived"] | None = None,
    language: str | None = Query(None, max_length=40),
    mine: bool = False,
    usable: bool = False,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """pob-023 G5/G6: the caller sees their own personal templates and the shared ones they may (a recruiter: approved, or their own
    draft; an approver: all). `usable` is what a composer may offer them; `mine` is what they wrote. `q` matches the name or purpose."""
    svc.require_template_reader(user)
    filters = [svc.visible(user)]
    if active is not None:
        filters.append(T.active.is_(active))
    if usable:
        filters.append(svc.usable_where(user))
    if mine:
        filters.append(or_(T.created_by_user_id == user.id, T.owner_user_id == user.id))
    for column, value in ((T.channel, channel), (T.category, category), (T.status, status)):
        if value:
            filters.append(column == value)
    if language:
        filters.append(func.lower(T.language) == language.strip().lower())
    stmt = select(T).where(*filters, *_matching(like_pattern(q), T.name, T.purpose))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(T.channel.desc(), KIND_ORDER, func.lower(T.name), T.id).limit(limit).offset(offset))).all()
    return {"items": await svc.templates_out(db, user, list(rows)), "total": total or 0, "limit": limit, "offset": offset}


@router.post("/templates", status_code=201)
async def create_template(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """G4/G5: a manager's shared template is approved at once; a recruiter's starts as a draft; a personal one is always a draft."""
    svc.require_template_writer(user)
    data = _body(RecTemplateCreate, payload)
    category = data.category or svc.default_category(data.channel, data.kind)
    svc.check_template(data.channel, data.kind, data.subject, data.body, category, data.steps)
    personal = data.visibility == "personal"
    fields = data.model_dump(exclude={"visibility", "category", "language"})
    template = T(
        **fields, category=category, language=data.language or "English", owner_user_id=user.id if personal else None,
        status="approved" if not personal and user.role in svc.APPROVERS else "draft", version=1, created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )  # fmt: skip
    db.add(template)
    await _flush_name(db, template)
    svc.add_version(db, template, user)
    audit(db, user, "recruiter_template.create", "recruiter_message_template", template.id, sorted(data.model_dump(exclude_unset=True)))
    await db.commit()
    svc.log("recruiter_template_created", user, template.id, channel=template.channel, kind=template.kind, status=template.status)
    return await _one_out(db, user, template)


@router.patch("/templates/{template_id}")
async def update_template(template_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rule is re-checked on the merged row; the channel and visibility are fixed. A content change is a new version (G7); rec-026's
    `active` approves (true) or archives (false) -- an approver's, on a shared template."""
    svc.require_template_writer(user)
    template = await svc.load_visible(db, user, template_id, lock=True)
    changes = _body(RecTemplateUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("channel", template.channel) != template.channel:
        raise HTTPException(422, "Channel cannot be changed")
    if changes.pop("visibility", None) not in (None, "personal" if template.owner_user_id else "shared"):
        raise HTTPException(422, "Visibility cannot be changed")
    active = changes.pop("active", None)
    if "language" in changes:
        changes["language"] = changes["language"] or "English"  # G3: blank is the default, as on create
    if changes:
        svc.require_right(user, template, "can_edit")
    if active is not None and active != template.active:
        if template.owner_user_id is not None:
            raise HTTPException(422, "A personal template is never shared, so it cannot be approved")
        if user.role not in svc.APPROVERS:
            raise HTTPException(403, "Only a placement manager can approve or archive a shared template")
    merged = {key: changes.get(key, getattr(template, key)) for key in ("kind", "subject", "body", "category", "steps")}
    svc.check_template(template.channel, merged["kind"], merged["subject"], merged["body"], merged["category"], merged["steps"])
    fields = apply_changes(template, changes)
    if fields:
        template.version += 1
        template.updated_by_user_id = user.id
        svc.add_version(db, template, user)
    if active is not None and active != template.active:
        template.active = active
        fields = sorted([*fields, "active"])
    await _flush_name(db, template)
    if fields:
        audit(db, user, "recruiter_template.update", "recruiter_message_template", template.id, fields)
    await db.commit()
    if fields:
        svc.log("recruiter_template_updated", user, template_id, fields=fields)
    return await _one_out(db, user, template)


async def _transition(db: AsyncSession, user: User, template_id: UUID, right: str, status: str, action: str) -> dict:
    """G4: approve (draft -> approved), archive (-> archived), restore (archived -> draft). Not a version (G7)."""
    svc.require_template_writer(user)
    template = await svc.load_visible(db, user, template_id, lock=True)
    svc.require_right(user, template, right)
    template.status = status
    audit(db, user, f"recruiter_template.{action}", "recruiter_message_template", template.id, ["status"])
    await db.commit()
    svc.log(f"recruiter_template_{action}", user, template_id)
    return await _one_out(db, user, template)


@router.post("/templates/{template_id}/approve")
async def approve_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _transition(db, user, template_id, "can_approve", "approved", "approve")


@router.post("/templates/{template_id}/archive")
async def archive_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _transition(db, user, template_id, "can_archive", "archived", "archive")


@router.post("/templates/{template_id}/restore")
async def restore_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _transition(db, user, template_id, "can_restore", "draft", "restore")


@router.get("/templates/{template_id}/versions")
async def template_versions(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """G7: every saved content, newest first, with who saved it -- for whoever sees the template."""
    svc.require_template_reader(user)
    await svc.load_visible(db, user, template_id)
    V = RecruiterTemplateVersion
    rows = (await db.execute(select(V, User).outerjoin(User, User.id == V.edited_by_user_id).where(V.template_id == template_id).order_by(V.version.desc()))).all()
    items = [
        {"version": v.version, "created_at": v.created_at, "edited_by": {"id": u.id, "full_name": u.full_name} if u else None, **v.content}
        for v, u in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/templates/{template_id}/preview")
async def preview_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Sample recipient and context values and the caller's own name -- for any template the caller sees (G5)."""
    svc.require_template_reader(user)
    template = await svc.load_visible(db, user, template_id)
    return svc.rendered(template, {**svc.SAMPLE_VALUES, "recruiter": user.full_name})


# --- messages (MS4-MS10) --------------------------------------------------------------------------------------------------------
@router.get("/messages/render")
async def render_message(
    template_id: UUID,
    contact_id: UUID | None = None,
    candidate_id: UUID | None = None,
    job_id: UUID | None = None,
    interview_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MS2: the template with the party's values -- the template reader's role first (403; rec-038 RM6: the assigned BDM and hr_team read a
    party's messages but never a template, §2.61), then the party's scope (404), then a usable template (404). pob-023 G8/G9: an
    optional requirement or interview adds its values, each in its own scope and only for this party (404)."""
    svc.require_template_reader(user)
    company, contact, candidate = await svc.load_party(db, user, contact_id, candidate_id)
    template = await svc.usable_template(db, user, template_id)
    values = svc.party_values(user, company, contact, candidate) | await svc.context_values(db, user, company, candidate, job_id, interview_id)
    return {"template": {"id": template.id, "name": template.name, "channel": template.channel, "kind": template.kind}, **svc.rendered(template, values)}


@router.post("/messages/copies", status_code=201)
async def copy_message(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """pob-023 G10: a LinkedIn message or calling script copied to the clipboard -- logged (ids only), never sent."""
    svc.require_template_reader(user)
    data = _body(RecTemplateCopy, payload)
    out = await svc.copy(db, user, data, await db_now(db))
    await db.commit()
    svc.log("recruiter_template_copied", user, data.template_id, channel=data.channel)
    return out


@router.post("/messages", status_code=201)
async def send_message(payload: RecMessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry sends again; the daily cap bounds it). AC3: a WhatsApp row is written only when the recruiter confirms the
    send. AC2: an email is stored `queued` and published after the commit, so the request never waits on SMTP."""
    message = await svc.create(db, user, payload, await db_now(db))
    await db.commit()
    if message.channel == "email":
        enqueue_recruiter_email(message.id)
    svc.log("recruiter_message_sent", user, message.id, channel=message.channel, template_id=str(message.template_id) if message.template_id else None)
    return await svc.one(db, message.id)


@router.post("/messages/{message_id}/reply")
async def log_reply(message_id: UUID, payload: RecMessageReply, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """pob-005 D7: record that the contact replied to this message (set once; a repeat returns it unchanged). Moves the contact to Replied."""
    reply_id = await svc.log_reply(db, user, message_id, payload.replied_at, await db_now(db))
    await db.commit()
    svc.log("recruiter_message_reply_logged", user, reply_id)
    return await svc.one(db, reply_id)


@router.post("/messages/linkedin", status_code=201)
async def log_linkedin(payload: RecLinkedInCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """pob-007 A1: LinkedIn outreach done by hand (there is no LinkedIn API). Not idempotent (a retry logs it twice; the daily cap bounds it)."""
    message = await svc.log_linkedin(db, user, payload, await db_now(db))
    await db.commit()
    svc.log("recruiter_linkedin_logged", user, message.id, action=payload.action, follow_up=message.follow_up_id is not None)
    return await svc.one(db, message.id)


@router.post("/messages/{message_id}/outcome")
async def record_outcome(message_id: UUID, payload: RecMessageOutcome, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """pob-007 A3: what came of a contact message, with an optional next follow-up. Set once: a second is 409."""
    out_id = await svc.record_outcome(db, user, message_id, payload, await db_now(db))
    await db.commit()
    svc.log("recruiter_message_outcome_recorded", user, out_id)
    return await svc.one(db, out_id)


@router.get("/companies/{company_id}/messages")
async def company_messages(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every contact message of the company, newest first -- whoever has the company in scope (a manager and the assigned BDM read)."""
    company = await companies.load_scoped(db, user, company_id)
    out = await svc.page(db, RecruiterMessage.company_id == company_id, limit, offset)
    await recruiter_cadences.attach(db, user, company, out["items"])  # pob-008 B6: the run started on each message
    return out


@router.get("/candidates/{candidate_id}/messages")
async def candidate_messages(candidate_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_reader(user)
    await candidates.load(db, candidate_id)
    return await svc.page(db, RecruiterMessage.candidate_id == candidate_id, limit, offset)
