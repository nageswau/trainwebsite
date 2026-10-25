"""ccrm-019 (DEC-SCOPE-257) -- an application's document checklist: made from the matching admission template (version and gate mode
frozen, the student's documents auto-linked by type) or empty; counselor items, marks and links; the view and summary; the
`documents_completed_on` date; and the Ready-for-Submission gate. Functions only; never commits (the routes and jobs do)."""

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_checklists import GATE_BLOCKED, GATE_NEEDS_REASON, NO_TEMPLATE_GATE_MODE, READY_FOR_SUBMISSION, item_status, status_label, summary
from app.document_checklists import STANDARD_STATUSES, STATUS_LABELS, type_sensitivity
from app.models import (
    ApplicationChecklist,
    ApplicationChecklistItem,
    ApplicationChecklistItemDocument,
    DocumentChecklistTemplateItem,
    DocumentRequest,
    OverseasApplication,
    StudentDocument,
    User,
)
from app.schemas import ChecklistTemplateItemIn
from app.services import document_checklists as templates
from app.services.document_access import sensitivities

INDIA = ZoneInfo("Asia/Kolkata")
KIND = "admission"  # AC3
EXISTS = "This application already has a checklist"
NO_CHECKLIST = "Create the checklist first"
ITEM_NOT_FOUND = "Checklist item not found"
TEMPLATE_ITEM = "A template item cannot be removed -- mark it Not required instead"
MARK_NOT_ALLOWED = "That status is not allowed for this item"
NOT_THE_STUDENTS = "Choose a current document of this application's student"


def _today() -> date:
    return datetime.now(UTC).astimezone(INDIA).date()


def _documents_of(app: OverseasApplication):
    """The application's student's current documents: unattached or attached to this application (never another one's)."""
    owners = []
    if app.student_id:
        owners.append(StudentDocument.student_id == app.student_id)
    if app.agent_student_id:
        owners.append(StudentDocument.agent_student_id == app.agent_student_id)
    return select(StudentDocument).where(
        or_(*owners) if owners else StudentDocument.id.is_(None),
        StudentDocument.archived_at.is_(None),
        or_(StudentDocument.application_id.is_(None), StudentDocument.application_id == app.id),
    )


def _name(item: ApplicationChecklistItem) -> str:
    return item.label or item.document_type


def _document_view(d: StudentDocument, sensitivity: str) -> dict:
    return {
        "id": d.id,
        "document_type": d.document_type,
        "document_label": d.document_label,
        "original_filename": d.original_filename,
        "verification_status": d.verification_status,
        "status_label": STATUS_LABELS.get(d.verification_status, d.verification_status),
        "created_at": d.created_at,
        "sensitivity": sensitivity,  # ccrm-022 SD2
    }


async def get(db: AsyncSession, application_id: UUID) -> ApplicationChecklist | None:
    return await db.get(ApplicationChecklist, application_id, populate_existing=True)


async def _items(db: AsyncSession, application_id: UUID) -> list[tuple[ApplicationChecklistItem, list[StudentDocument]]]:
    items = list((await db.scalars(select(ApplicationChecklistItem).where(ApplicationChecklistItem.application_id == application_id).order_by(ApplicationChecklistItem.position))).all())
    linked: dict[UUID, list[StudentDocument]] = {i.id: [] for i in items}
    if items:
        rows = await db.execute(
            select(ApplicationChecklistItemDocument.item_id, StudentDocument)
            .join(StudentDocument, StudentDocument.id == ApplicationChecklistItemDocument.document_id)
            .where(ApplicationChecklistItemDocument.item_id.in_(linked), StudentDocument.archived_at.is_(None))
            .order_by(StudentDocument.created_at)
        )
        for item_id, document in rows:
            linked[item_id].append(document)
    return [(i, linked[i.id]) for i in items]


def _status(item: ApplicationChecklistItem, documents: list[StudentDocument]) -> str:
    return item_status(item.mark, [d.verification_status for d in documents])


async def _summary(db: AsyncSession, application_id: UUID) -> dict:
    rows = await _items(db, application_id)
    return summary([{"id": i.id, "name": _name(i), "required": i.required, "status": _status(i, docs)} for i, docs in rows])


async def view(db: AsyncSession, app: OverseasApplication, checklist: ApplicationChecklist | None) -> dict | None:
    if checklist is None:
        return None
    rows = await _items(db, app.id)
    classes = await sensitivities(db, (d for _, documents in rows for d in documents))
    # ccrm-020 R2: an item's open request to the student (its due date shows beside the Requested status)
    requests = (
        {r.checklist_item_id: r for r in await db.scalars(select(DocumentRequest).where(DocumentRequest.checklist_item_id.in_([i.id for i, _ in rows]), DocumentRequest.status == "open"))}
        if rows
        else {}
    )
    items = []
    for item, documents in rows:
        status = _status(item, documents)
        items.append(
            {
                "id": item.id,
                "position": item.position,
                "document_type": item.document_type,
                "label": item.label,
                "name": _name(item),
                "required": item.required,
                "notes": item.notes,
                "allowed_statuses": item.allowed_statuses,
                "mark": item.mark,
                "status": status,
                "status_label": status_label(status),
                "removable": not item.from_template,
                "sensitivity": item.sensitivity,
                "documents": [_document_view(d, classes[d.id]) for d in documents],
                "open_request": {"id": r.id, "due_date": r.due_date} if (r := requests.get(item.id)) else None,
            }
        )
    return {
        "template_id": checklist.template_id,
        "template_version": checklist.template_version,
        "gate_mode": checklist.gate_mode,
        "documents_completed_on": app.documents_completed_on,
        "summary": summary(items),
        "items": items,
    }


async def linkable(db: AsyncSession, app: OverseasApplication) -> list[dict]:
    rows = list((await db.scalars(_documents_of(app).order_by(StudentDocument.document_type, StudentDocument.created_at.desc()))).all())
    classes = await sensitivities(db, rows)
    return [_document_view(d, classes[d.id]) for d in rows]


async def create(db: AsyncSession, user: User, app: OverseasApplication) -> ApplicationChecklist:
    """From the matching admission template (or empty, AC5); each item links the student's documents of its type (AC1)."""
    template = await templates.resolve(db, app, KIND)
    checklist = ApplicationChecklist(
        application_id=app.id,
        template_id=template.id if template else None,
        template_version=template.version if template else None,
        gate_mode=template.gate_mode if template else NO_TEMPLATE_GATE_MODE,
        created_by_id=user.id,
    )
    db.add(checklist)
    await db.flush()
    if template is None:
        return checklist
    documents = list((await db.scalars(_documents_of(app))).all())
    sources = await db.scalars(select(DocumentChecklistTemplateItem).where(DocumentChecklistTemplateItem.template_id == template.id).order_by(DocumentChecklistTemplateItem.position))
    for source in sources:
        item = ApplicationChecklistItem(
            application_id=app.id, from_template=True, position=source.position, document_type=source.document_type, label=source.label,
            required=source.required, allowed_statuses=list(source.allowed_statuses), notes=source.notes, created_by_id=checklist.created_by_id,
            sensitivity=source.sensitivity,
        )  # fmt: skip
        db.add(item)
        await db.flush()
        wanted = {source.document_type.lower(), *([source.label.lower()] if source.label else [])}
        for document in documents:
            if {document.document_type.lower(), (document.document_label or "").lower()} & wanted:
                db.add(ApplicationChecklistItemDocument(item_id=item.id, document_id=document.id, linked_by_id=checklist.created_by_id))
    await db.flush()
    return checklist


async def sync_completion(db: AsyncSession, app: OverseasApplication) -> None:
    """AC2: today when every required item is complete (and the date is empty); cleared when one is not."""
    s = await _summary(db, app.id)
    ready = s["ready"] and s["required_total"] > 0
    if ready and app.documents_completed_on is None:
        app.documents_completed_on = _today()
    elif not ready and app.documents_completed_on is not None:
        app.documents_completed_on = None


async def sync_for_documents(db: AsyncSession, document_ids: list[UUID]) -> None:
    """AC9: a document's status changed (a review, the expiry job, a replace) -- refresh each application whose checklist counts it."""
    if not document_ids:
        return
    ids = await db.scalars(
        select(ApplicationChecklistItem.application_id)
        .join(ApplicationChecklistItemDocument, ApplicationChecklistItemDocument.item_id == ApplicationChecklistItem.id)
        .where(ApplicationChecklistItemDocument.document_id.in_(document_ids))
        .distinct()
    )
    for app_id in list(ids):
        app = await db.get(OverseasApplication, app_id)
        await sync_completion(db, app)


async def move_links(db: AsyncSession, old_id: UUID, new_id: UUID) -> None:
    """AC9 / ccrm-021 S3: a replaced document's checklist links follow its new version."""
    await db.execute(update(ApplicationChecklistItemDocument).where(ApplicationChecklistItemDocument.document_id == old_id).values(document_id=new_id))


async def _item(db: AsyncSession, app: OverseasApplication, item_id: UUID) -> ApplicationChecklistItem:
    item = await db.get(ApplicationChecklistItem, item_id)
    if item is None or item.application_id != app.id:
        raise HTTPException(404, ITEM_NOT_FOUND)
    return item


async def _require_checklist(db: AsyncSession, app: OverseasApplication) -> None:
    if await get(db, app.id) is None:
        raise HTTPException(409, NO_CHECKLIST)


async def add_item(db: AsyncSession, user: User, app: OverseasApplication, payload: ChecklistTemplateItemIn) -> ApplicationChecklistItem:
    await _require_checklist(db, app)
    position = (await db.scalar(select(func.max(ApplicationChecklistItem.position)).where(ApplicationChecklistItem.application_id == app.id)) or 0) + 1
    item = ApplicationChecklistItem(
        application_id=app.id, from_template=False, position=position, document_type=payload.document_type, label=payload.label,
        required=payload.required, allowed_statuses=list(payload.allowed_statuses or STANDARD_STATUSES), notes=payload.notes, created_by_id=user.id,
        sensitivity=payload.sensitivity or type_sensitivity(payload.document_type, payload.label),
    )  # fmt: skip
    db.add(item)
    await db.flush()
    return item


async def remove_item(db: AsyncSession, app: OverseasApplication, item_id: UUID) -> ApplicationChecklistItem:
    item = await _item(db, app, item_id)
    if item.from_template:
        raise HTTPException(409, TEMPLATE_ITEM)
    await db.delete(item)
    await db.flush()
    return item


async def set_mark(db: AsyncSession, user: User, app: OverseasApplication, item_id: UUID, mark: str | None) -> ApplicationChecklistItem:
    item = await _item(db, app, item_id)
    if mark is not None and item.allowed_statuses and mark not in item.allowed_statuses:
        raise HTTPException(422, MARK_NOT_ALLOWED)
    item.mark, item.marked_by_id, item.marked_at = mark, (user.id if mark else None), (datetime.now(UTC) if mark else None)
    await db.flush()
    return item


async def link(db: AsyncSession, user: User, app: OverseasApplication, item_id: UUID, document_id: UUID) -> ApplicationChecklistItem:
    """Idempotent; a link is a new document for the item, so it clears the item's mark (AC1)."""
    item = await _item(db, app, item_id)
    if await db.scalar(_documents_of(app).where(StudentDocument.id == document_id).with_only_columns(StudentDocument.id)) is None:
        raise HTTPException(422, NOT_THE_STUDENTS)
    await db.execute(insert(ApplicationChecklistItemDocument).values(item_id=item.id, document_id=document_id, linked_by_id=user.id).on_conflict_do_nothing())
    item.mark = item.marked_by_id = item.marked_at = None
    await db.flush()
    return item


async def unlink(db: AsyncSession, app: OverseasApplication, item_id: UUID, document_id: UUID) -> ApplicationChecklistItem:
    item = await _item(db, app, item_id)
    await db.execute(delete(ApplicationChecklistItemDocument).where(ApplicationChecklistItemDocument.item_id == item.id, ApplicationChecklistItemDocument.document_id == document_id))
    return item


async def ready_gate(db: AsyncSession, user: User, app: OverseasApplication, sub_status: str, override_reason: str | None) -> str | None:
    """AC 5 / CC10 on both sub-status routes, after the row lock: a move to Ready for Submission needs every required item complete.
    AC4: the checklist is made now when a template matches and none exists. Returns the override reason a warn-mode pass records. A
    refusal is a 409 listing the missing items; it commits first (the one exception here) so a checklist the gate made is kept."""
    if sub_status != READY_FOR_SUBMISSION or app.sub_status == READY_FOR_SUBMISSION:
        return None
    checklist = await get(db, app.id)
    if checklist is None:
        if await templates.resolve(db, app, KIND) is None:
            return None
        checklist = await create(db, user, app)
    s = await _summary(db, app.id)
    if s["ready"]:
        return None
    if checklist.gate_mode == "warn" and override_reason:
        return override_reason
    detail = {"message": GATE_BLOCKED if checklist.gate_mode == "block" else GATE_NEEDS_REASON, "gate_mode": checklist.gate_mode, "missing": [{**m, "id": str(m["id"])} for m in s["missing"]]}
    await db.commit()
    raise HTTPException(409, detail)
