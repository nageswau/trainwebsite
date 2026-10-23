"""ccrm-018 (DEC-SCOPE-248) -- document checklist templates. The Overseas Admin writes; the counselor reads (and resolves the template
for one of their applications). Super Admin passes `_require` as everywhere. One active template per kind and scope (unique index, 409);
an edit is a full replace guarded by the version the editor loaded. Spec:
docs/superpowers/specs/2026-10-23-ccrm-018-document-checklist-templates-design.md."""

import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import _assigned_application, _audit, _require
from app.core.database import get_db
from app.document_checklists import CHECKLIST_KINDS
from app.models import Country, DocumentChecklistTemplate, DocumentChecklistTemplateItem, University, User
from app.schemas import ChecklistTemplateIn, ChecklistTemplateUpdate
from app.services import document_checklists as svc

logger = logging.getLogger("app.document_checklists")

router = APIRouter(prefix="/overseas-admin/checklists", tags=["document-checklists"])

WRITERS = {"overseas_admin"}
READERS = WRITERS | {"counselor"}
STALE = "Someone else saved this template since you opened it; reload to see their changes"


async def _get(db: AsyncSession, template_id: UUID, *, lock: bool = False) -> DocumentChecklistTemplate:
    stmt = select(DocumentChecklistTemplate).where(DocumentChecklistTemplate.id == template_id)
    template = await db.scalar(stmt.with_for_update() if lock else stmt)
    if template is None:
        raise HTTPException(404, "Checklist template not found")
    return template


@asynccontextmanager
async def _scope_guard(db: AsyncSession):
    """Wraps a write through its commit. The scope index is the authority on duplicates (an autoflush may hit it before the commit),
    including two admins saving the same scope at once."""
    try:
        yield
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_document_checklist_templates_scope" in str(exc.orig):
            raise HTTPException(409, svc.SCOPE_TAKEN) from None
        raise


@router.get("")
async def list_templates(
    kind: Literal[CHECKLIST_KINDS] | None = None,
    country_id: UUID | None = None,
    status: Literal["active", "inactive", "all"] = "active",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every template matching the filters, by country, kind, then the least specific scope first."""
    _require(user, READERS, "overseas")
    t = DocumentChecklistTemplate
    count = select(func.count()).where(DocumentChecklistTemplateItem.template_id == t.id).scalar_subquery()
    stmt = (
        select(t, Country.name, University.name, count)
        .join(Country, Country.id == t.country_id)
        .outerjoin(University, University.id == t.university_id)
        .order_by(Country.name, t.kind, University.name.nulls_first(), t.course_level.nulls_first(), t.intake.nulls_first(), t.id)
    )
    if kind is not None:
        stmt = stmt.where(t.kind == kind)
    if country_id is not None:
        stmt = stmt.where(t.country_id == country_id)
    if status != "all":
        stmt = stmt.where(t.active.is_(status == "active"))
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "kind": row.kind,
                "country_id": row.country_id,
                "country_name": country,
                "university_id": row.university_id,
                "university_name": university,
                "course_level": row.course_level,
                "intake": row.intake,
                "gate_mode": row.gate_mode,
                "version": row.version,
                "active": row.active,
                "item_count": items,
                "updated_at": row.updated_at,
            }
            for row, country, university, items in rows
        ]
    }


@router.get("/resolve")
async def resolve_template(application_id: UUID, kind: Literal[CHECKLIST_KINDS], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The template that applies to one application (the most specific match), or null. A counselor only for their own applications."""
    _require(user, READERS, "overseas")
    application = await _assigned_application(db, user, application_id)
    template = await svc.resolve(db, application, kind)
    return {"template": await svc.view(db, template) if template else None}


@router.get("/{template_id}")
async def get_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, READERS, "overseas")
    return await svc.view(db, await _get(db, template_id))


@router.post("", status_code=201)
async def create_template(payload: ChecklistTemplateIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, WRITERS, "overseas")
    await svc.check_scope(db, payload)
    template_id = uuid4()
    async with _scope_guard(db):
        template = DocumentChecklistTemplate(id=template_id, created_by_id=user.id, updated_by_id=user.id, version=1, active=True)
        svc.apply(template, payload)
        db.add(template)
        await db.flush()
        await svc.replace_items(db, template, payload)
        await _audit(db, user, "checklist_template.create", "document_checklist_template", template_id, {"kind": payload.kind, "version": 1})
    logger.info("checklist template %s created by %s", template_id, user.id)
    return await svc.view(db, await _get(db, template_id))


@router.put("/{template_id}")
async def update_template(template_id: UUID, payload: ChecklistTemplateUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, WRITERS, "overseas")
    template = await _get(db, template_id, lock=True)
    if payload.version != template.version:
        raise HTTPException(409, STALE)
    await svc.check_scope(db, payload)
    version = template.version + 1
    async with _scope_guard(db):
        svc.apply(template, payload)
        template.active = payload.active
        template.version = version
        template.updated_by_id = user.id
        await svc.replace_items(db, template, payload)
        await _audit(db, user, "checklist_template.update", "document_checklist_template", template_id, {"kind": payload.kind, "version": version, "active": payload.active})
    logger.info("checklist template %s updated to v%s by %s", template_id, version, user.id)
    return await svc.view(db, await _get(db, template_id))
