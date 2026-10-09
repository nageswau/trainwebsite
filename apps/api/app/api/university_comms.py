"""upc-012 (DEC-SCOPE-139, spec §3): the partnership message templates (the head's global library, UC4) and the calls and messages kept
on a university -- render, send (WhatsApp logged on confirm, email queued for the worker), log a call, and the university's lists.

Template bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-012 idiom); the
role check runs before the body is read. Every write is one transaction -- role, the university lock and scope, rules, change, audit, one
commit here, then (an email) the publish and the log line."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT, _locked, _page
from app.core.database import get_db
from app.models import PartnershipMessageTemplate, User
from app.notifications.dispatch import enqueue_university_email
from app.schemas import TEL_CONTENT_FIELD_LABELS, PartnershipTemplateCreate, PartnershipTemplateUpdate, UniversityCallCreate, UniversityMessageCreate
from app.services import partnership_universities as unis
from app.services import university_comms as svc
from app.services.bdm_appointments import db_now
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, flush_unique

router = APIRouter(prefix="/partnership", tags=["partnership-communications"])
T = PartnershipMessageTemplate


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CONTENT_FIELD_LABELS)


def _taken(channel: str, name: str) -> str:
    return f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} template named “{name}” already exists"


# --- templates (UC4, UC5) -------------------------------------------------------------------------------------------------------
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
    """Managers always get the active templates only, whatever they ask; the head and super_admin see every row."""
    await svc.require_reader(db, user)
    filters: list = [] if active is None else [T.active.is_(active)]
    if not svc.sees_inactive(user):
        filters.append(T.active.is_(True))
    if channel:
        filters.append(T.channel == channel)
    stmt = select(T).where(*filters, *_matching(like_pattern(q), T.name))
    return await _page(db, stmt, (T.channel.desc(), func.lower(T.name), T.id), limit, offset, svc.template_out)


@router.post("/templates", status_code=201)
async def create_template(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_template_writer(user)
    data = _body(PartnershipTemplateCreate, payload)
    svc.check_template(data.channel, data.subject, data.body)
    template = T(**data.model_dump(), active=True)
    db.add(template)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(data.channel, data.name))
    svc.audit(db, user, "partnership_template.create", "partnership_message_template", template.id, {"fields": sorted(data.model_dump())})
    out = svc.template_out(template)
    await db.commit()
    svc.log("partnership_template_created", user, template.id, channel=template.channel)
    return out


@router.patch("/templates/{template_id}")
async def update_template(template_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rule is re-checked on the merged row; the channel is fixed."""
    svc.require_template_writer(user)
    template = await _locked(db, T, template_id, "Template")
    changes = _body(PartnershipTemplateUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("channel", template.channel) != template.channel:
        raise HTTPException(422, "Channel cannot be changed")
    merged = {key: changes.get(key, getattr(template, key)) for key in ("subject", "body")}
    svc.check_template(template.channel, merged["subject"], merged["body"])
    fields = apply_changes(template, changes)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(template.channel, template.name))
    if fields:
        svc.audit(db, user, "partnership_template.update", "partnership_message_template", template.id, {"fields": fields})
    out = svc.template_out(template)
    await db.commit()
    if fields:
        svc.log("partnership_template_updated", user, template_id, fields=fields)
    return out


@router.get("/templates/{template_id}/preview")
async def preview_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Sample values and the caller's own name; an inactive template is 404 to a manager."""
    await svc.require_reader(db, user)
    template = await db.get(T, template_id)
    if template is None or not (template.active or svc.sees_inactive(user)):
        raise HTTPException(404, svc.TEMPLATE_NOT_FOUND)
    return svc.rendered(template, {**svc.SAMPLE_VALUES, "manager": user.full_name})


# --- messages (UC6-UC9) ---------------------------------------------------------------------------------------------------------
@router.get("/messages/render")
async def render_message(template_id: UUID, contact_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UC5: the template with the contact's values -- the contact first (404), then an active template (404)."""
    uni, contact = await svc.readable_contact(db, user, contact_id)
    template = await svc.active_template(db, template_id)
    return {"template": {"id": template.id, "name": template.name, "channel": template.channel}, **svc.rendered(template, svc.contact_values(user, uni, contact))}


@router.post("/messages", status_code=201)
async def send_message(payload: UniversityMessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry sends again; the daily cap bounds it). AC2: a WhatsApp row is written only when the manager confirms the
    send. AC1: an email is stored `queued` and published after the commit, so the request never waits on SMTP."""
    message = await svc.create_message(db, user, payload, await db_now(db))
    await db.commit()
    if message.channel == "email":
        enqueue_university_email(message.id)
    svc.log("university_message_sent", user, message.id, channel=message.channel, template_id=str(message.template_id) if message.template_id else None)
    return await svc.one(db, "messages", message.id)


@router.post("/calls", status_code=201)
async def log_call(payload: UniversityCallCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UC1 / AC3: not idempotent; the call becomes the contact's last interaction."""
    call = await svc.create_call(db, user, payload, await db_now(db))
    await db.commit()
    svc.log("university_call_logged", user, call.id, outcome=call.outcome)
    return await svc.one(db, "calls", call.id)


async def _history(db: AsyncSession, user: User, kind: str, university_id: UUID, limit: int, offset: int) -> dict:
    """The university's calls or messages, newest first -- every partnership role reads them (UC3)."""
    await svc.require_reader(db, user)
    await unis.load(db, university_id)
    return await svc.page(db, kind, university_id, limit, offset)


@router.get("/universities/{university_id}/calls")
async def university_calls(university_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _history(db, user, "calls", university_id, limit, offset)


@router.get("/universities/{university_id}/messages")
async def university_messages(university_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _history(db, user, "messages", university_id, limit, offset)
