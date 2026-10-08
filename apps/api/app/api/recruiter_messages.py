"""rec-026 (DEC-SCOPE-134, spec §3): the recruiter message templates (the placement manager's global library, MS3) and messages to a company
contact or a candidate -- render, send (WhatsApp logged on confirm, email queued for the worker) and the company's and candidate's lists.

Template bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-012 idiom); the
role check runs before the body is read. Every write is one transaction -- role, scope and lock, rules, change, audit, one commit here, then
(an email) the publish and the log line."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT, _locked, _page
from app.core.database import get_db
from app.models import RecruiterMessage, RecruiterMessageTemplate, User
from app.notifications.dispatch import enqueue_recruiter_email
from app.schemas import TEL_CONTENT_FIELD_LABELS, RecMessageCreate, RecTemplateCreate, RecTemplateUpdate
from app.services import candidates
from app.services import recruiter_companies as companies
from app.services import recruiter_messages as svc
from app.services.bdm_appointments import db_now
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, audit, flush_unique

router = APIRouter(prefix="/recruiter", tags=["recruiter-messages"])
T = RecruiterMessageTemplate
# WhatsApp before email, then the source's kind order (§19), then name.
KIND_ORDER = case(*((T.kind == kind, index) for index, kind in enumerate(dict.fromkeys(svc.REC_WHATSAPP_KINDS + svc.REC_EMAIL_KINDS))), else_=99)


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CONTENT_FIELD_LABELS)


def _taken(channel: str, name: str) -> str:
    return f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} template named “{name}” already exists"  # QA-01


# --- templates (MS1-MS3) --------------------------------------------------------------------------------------------------------
@router.get("/templates")
async def list_templates(
    channel: Literal["whatsapp", "email"] | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recruiters always get the active templates only, whatever they ask; the manager and super_admin see every row."""
    svc.require_template_reader(user)
    filters = [] if active is None else [T.active.is_(active)]
    if not svc.sees_inactive(user):
        filters.append(T.active.is_(True))
    if channel:
        filters.append(T.channel == channel)
    stmt = select(T).where(*filters, *_matching(like_pattern(q), T.name))
    return await _page(db, stmt, (T.channel.desc(), KIND_ORDER, func.lower(T.name), T.id), limit, offset, svc.template_out)


@router.post("/templates", status_code=201)
async def create_template(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_template_writer(user)
    data = _body(RecTemplateCreate, payload)
    svc.check_template(data.channel, data.kind, data.subject, data.body)
    template = T(**data.model_dump(), active=True)
    db.add(template)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(data.channel, data.name))
    audit(db, user, "recruiter_template.create", "recruiter_message_template", template.id, sorted(data.model_dump()))
    out = svc.template_out(template)
    await db.commit()
    svc.log("recruiter_template_created", user, template.id, channel=template.channel, kind=template.kind)
    return out


@router.patch("/templates/{template_id}")
async def update_template(template_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rule is re-checked on the merged row; the channel is fixed."""
    svc.require_template_writer(user)
    template = await _locked(db, T, template_id, "Template")
    changes = _body(RecTemplateUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("channel", template.channel) != template.channel:
        raise HTTPException(422, "Channel cannot be changed")
    merged = {key: changes.get(key, getattr(template, key)) for key in ("kind", "subject", "body")}
    svc.check_template(template.channel, merged["kind"], merged["subject"], merged["body"])
    fields = apply_changes(template, changes)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(template.channel, template.name))
    if fields:
        audit(db, user, "recruiter_template.update", "recruiter_message_template", template.id, fields)
    out = svc.template_out(template)
    await db.commit()
    if fields:
        svc.log("recruiter_template_updated", user, template_id, fields=fields)
    return out


@router.get("/templates/{template_id}/preview")
async def preview_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Sample recipient values and the caller's own name; an inactive template is 404 to a recruiter."""
    svc.require_template_reader(user)
    template = await db.get(T, template_id)
    if template is None or not (template.active or svc.sees_inactive(user)):
        raise HTTPException(404, svc.TEMPLATE_NOT_FOUND)
    return svc.rendered(template, {**svc.SAMPLE_VALUES, "recruiter": user.full_name})


# --- messages (MS4-MS10) --------------------------------------------------------------------------------------------------------
@router.get("/messages/render")
async def render_message(
    template_id: UUID,
    contact_id: UUID | None = None,
    candidate_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MS2: the template with the party's values -- the party's scope first (404), then an active template (404)."""
    company, contact, candidate = await svc.load_party(db, user, contact_id, candidate_id)
    template = await svc.active_template(db, template_id)
    return {"template": {"id": template.id, "name": template.name, "channel": template.channel, "kind": template.kind}, **svc.rendered(template, svc.party_values(user, company, contact, candidate))}


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


@router.get("/companies/{company_id}/messages")
async def company_messages(company_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every contact message of the company, newest first -- whoever has the company in scope (a manager and the assigned BDM read)."""
    await companies.load_scoped(db, user, company_id)
    return await svc.page(db, RecruiterMessage.company_id == company_id, limit, offset)


@router.get("/candidates/{candidate_id}/messages")
async def candidate_messages(candidate_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_reader(user)
    await candidates.load(db, candidate_id)
    return await svc.page(db, RecruiterMessage.candidate_id == candidate_id, limit, offset)
