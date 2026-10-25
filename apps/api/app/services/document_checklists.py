"""ccrm-018 (DEC-SCOPE-248) -- document checklist templates: views, scope checks, item replacement and resolution. Functions only;
never commits (the router does)."""

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_checklists import STANDARD_STATUSES, course_level_key, type_sensitivity
from app.models import Country, DocumentChecklistTemplate, DocumentChecklistTemplateItem, OverseasApplication, OverseasCourse, University
from app.schemas import ChecklistTemplateIn

SCOPE_TAKEN = "An active template already covers this kind and scope; edit that one or deactivate it first"
# Resolution weights: a university match outranks a course level and an intake together, and a level outranks an intake.
UNIVERSITY_WEIGHT, LEVEL_WEIGHT, INTAKE_WEIGHT = 4, 2, 1


def item_view(item: DocumentChecklistTemplateItem) -> dict:
    return {
        "id": item.id,
        "position": item.position,
        "document_type": item.document_type,
        "label": item.label,
        "required": item.required,
        "allowed_statuses": item.allowed_statuses,
        "notes": item.notes,
        "sensitivity": item.sensitivity,
    }


async def view(db: AsyncSession, template: DocumentChecklistTemplate) -> dict:
    items = await db.scalars(select(DocumentChecklistTemplateItem).where(DocumentChecklistTemplateItem.template_id == template.id).order_by(DocumentChecklistTemplateItem.position))
    country = await db.get(Country, template.country_id)
    university = await db.get(University, template.university_id) if template.university_id else None
    return {
        "id": template.id,
        "name": template.name,
        "kind": template.kind,
        "country_id": template.country_id,
        "country_name": country.name if country else None,
        "university_id": template.university_id,
        "university_name": university.name if university else None,
        "course_level": template.course_level,
        "intake": template.intake,
        "gate_mode": template.gate_mode,
        "notes": template.notes,
        "version": template.version,
        "active": template.active,
        "updated_at": template.updated_at,
        "items": [item_view(i) for i in items],
    }


async def check_scope(db: AsyncSession, payload: ChecklistTemplateIn) -> None:
    """422 for an unknown country, or a university that is unknown or in another country."""
    if await db.get(Country, payload.country_id) is None:
        raise HTTPException(422, "Country not found")
    if payload.university_id is not None:
        university = await db.get(University, payload.university_id)
        if university is None:
            raise HTTPException(422, "University not found")
        if university.country_id != payload.country_id:
            raise HTTPException(422, "The university is not in the chosen country")


def apply(template: DocumentChecklistTemplate, payload: ChecklistTemplateIn) -> None:
    for field in ("name", "kind", "country_id", "university_id", "course_level", "intake", "gate_mode", "notes"):
        setattr(template, field, getattr(payload, field))


async def replace_items(db: AsyncSession, template: DocumentChecklistTemplate, payload: ChecklistTemplateIn) -> None:
    await db.execute(delete(DocumentChecklistTemplateItem).where(DocumentChecklistTemplateItem.template_id == template.id))
    for position, item in enumerate(payload.items, start=1):
        db.add(
            DocumentChecklistTemplateItem(
                template_id=template.id,
                position=position,
                document_type=item.document_type,
                label=item.label,
                required=item.required,
                allowed_statuses=list(item.allowed_statuses or STANDARD_STATUSES),
                notes=item.notes,
                sensitivity=item.sensitivity or type_sensitivity(item.document_type, item.label),
            )
        )


async def resolve(db: AsyncSession, application: OverseasApplication, kind: str) -> DocumentChecklistTemplate | None:
    """The most specific active template of `kind` matching the application's country, university, course level and intake."""
    country_id = await db.scalar(select(University.country_id).where(University.id == application.university_id))
    level = None
    if application.course_id is not None:
        level = course_level_key(await db.scalar(select(OverseasCourse.level).where(OverseasCourse.id == application.course_id)))
    t = DocumentChecklistTemplate
    intake = (application.intake or "").strip().lower()
    rows = await db.scalars(
        select(t).where(
            t.active.is_(True),
            t.kind == kind,
            t.country_id == country_id,
            or_(t.university_id.is_(None), t.university_id == application.university_id),
            or_(t.course_level.is_(None), t.course_level == level) if level else t.course_level.is_(None),
            or_(t.intake.is_(None), func.lower(t.intake) == intake),
        )
    )

    def rank(template: DocumentChecklistTemplate) -> int:
        return UNIVERSITY_WEIGHT * (template.university_id is not None) + LEVEL_WEIGHT * (template.course_level is not None) + INTAKE_WEIGHT * (template.intake is not None)

    return max(rows, key=rank, default=None)
