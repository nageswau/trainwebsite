"""ccrm-037 (DEC-SCOPE-271, API §12FX, RBAC §2.185): the Overseas Admin's message templates for counselors (MT1) and the student message log
-- render, send (WhatsApp logged on confirm, email queued for the worker), record a reply by hand (MT7) and the student's log (MT9).

Template bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-012 idiom); the
role check runs before the body is read. Every write is one transaction -- role, scope, rules, change, audit, one commit here, then (an
email) the publish and the log line."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT, _locked, _page
from app.core.database import get_db
from app.models import CounselorMessageTemplate, User
from app.notifications.dispatch import enqueue_student_email
from app.schemas import TEL_CONTENT_FIELD_LABELS, CounselorTemplateCreate, CounselorTemplateUpdate, StudentMessageCreate, StudentReplyCreate
from app.services import counselor_messages as svc
from app.services.bdm_appointments import db_now
from app.services.student_profiles import staff_student
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, audit, flush_unique

router = APIRouter(prefix="/counselor", tags=["counselor-messages"])
T = CounselorMessageTemplate


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CONTENT_FIELD_LABELS)


def _taken(channel: str, name: str) -> str:
    return f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} template named “{name}” already exists"


# --- templates (MT1, MT2) -------------------------------------------------------------------------------------------------------
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
    """Counselors always get the active templates only, whatever they ask; the Overseas Admin and super_admin see every row."""
    svc.require_template_reader(user)
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
    data = _body(CounselorTemplateCreate, payload)
    svc.check_template(data.channel, data.subject, data.body)
    template = T(**data.model_dump(), active=True)
    db.add(template)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(data.channel, data.name))
    audit(db, user, "counselor_template.create", "counselor_message_template", template.id, sorted(data.model_dump()))
    out = svc.template_out(template)
    await db.commit()
    svc.log("counselor_template_created", user, template.id, channel=template.channel)
    return out


@router.patch("/templates/{template_id}")
async def update_template(template_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rule is re-checked on the merged row; the channel is fixed."""
    svc.require_template_writer(user)
    template = await _locked(db, T, template_id, "Template")
    changes = _body(CounselorTemplateUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("channel", template.channel) != template.channel:
        raise HTTPException(422, "Channel cannot be changed")
    merged = {key: changes.get(key, getattr(template, key)) for key in ("subject", "body")}
    svc.check_template(template.channel, merged["subject"], merged["body"])
    fields = apply_changes(template, changes)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _taken(template.channel, template.name))
    if fields:
        audit(db, user, "counselor_template.update", "counselor_message_template", template.id, fields)
    out = svc.template_out(template)
    await db.commit()
    if fields:
        svc.log("counselor_template_updated", user, template_id, fields=fields)
    return out


@router.get("/templates/{template_id}/preview")
async def preview_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Sample values and the caller's own name; an inactive template is 404 to a counselor."""
    svc.require_template_reader(user)
    template = await db.get(T, template_id)
    if template is None or not (template.active or svc.sees_inactive(user)):
        raise HTTPException(404, svc.TEMPLATE_NOT_FOUND)
    return svc.rendered(template, {**svc.SAMPLE_VALUES, "counselor": user.full_name})


# --- the student's messages (MT3-MT9) -------------------------------------------------------------------------------------------
@router.get("/students/{student_id}/messages")
async def student_messages(
    student_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    student = await staff_student(db, user, student_id)
    return await svc.page(db, user, student, limit, offset)


@router.get("/students/{student_id}/messages/render")
async def render_message(student_id: UUID, template_id: UUID, application_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MT2: the template with the student's and the application's values -- scope (404) and the sender's role (403), the application
    (422), then an active template (404)."""
    student = await svc.sender_student(db, user, student_id)
    application = await svc.own_application(db, user, student.id, application_id)
    template = await svc.active_template(db, template_id)
    return {"template": {"id": template.id, "name": template.name, "channel": template.channel}, **svc.rendered(template, svc.values(user, student, application))}


@router.post("/students/{student_id}/messages", status_code=201)
async def send_message(student_id: UUID, payload: StudentMessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry sends again; the daily cap bounds it). A WhatsApp row is written only when the counselor confirms the send;
    an email is stored `queued` and published after the commit, so the request never waits on SMTP (MT6)."""
    message = await svc.create_message(db, user, student_id, payload, await db_now(db))
    await db.commit()
    if message.channel == "email":
        enqueue_student_email(message.id)
    svc.log("student_message_sent", user, message.id, channel=message.channel, template_id=str(message.template_id) if message.template_id else None)
    return await svc.one(db, message.id)


@router.post("/students/{student_id}/replies", status_code=201)
async def record_reply(student_id: UUID, payload: StudentReplyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MT7: a reply the counselor received outside the platform, recorded by hand. Not idempotent."""
    message = await svc.create_reply(db, user, student_id, payload, await db_now(db))
    await db.commit()
    svc.log("student_reply_recorded", user, message.id, channel=message.channel)
    return await svc.one(db, message.id)
