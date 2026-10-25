"""ccrm-019 (DEC-SCOPE-257) -- an application's document checklist: read (counselor, Overseas Admin, the agency, the student), create,
counselor items, marks and document links.

Writes use the offer routes' entry (api/application_offers.py `_writable`: role, `_assigned_application` scope, the row lock, the
swapped-counselor re-check, closed and archived-agency refusals; on hold is allowed -- documents keep coming in), then refresh
`documents_completed_on`, audit and commit once. The Ready-for-Submission gate lives on the sub-status routes
(services/application_checklists.ready_gate). Spec: docs/superpowers/specs/2026-10-24-ccrm-019-application-checklist-design.md.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.application_offers import WRITERS, _writable
from app.api.deps import get_current_user
from app.api.workflows import _assigned_application, _audit, _require
from app.core.database import get_db
from app.models import OverseasApplication, User
from app.schemas import ApplicationChecklistMark, ChecklistTemplateItemIn
from app.services import application_checklists as svc
from app.services import document_checklists as templates

logger = logging.getLogger("app.application_checklists")

router = APIRouter(prefix="/workflows/overseas/applications", tags=["application-checklists"])

READERS = WRITERS | {"overseas_student", "agent"}
STAFF = WRITERS | {"super_admin"}


async def _response(db: AsyncSession, user: User, item: OverseasApplication) -> dict:
    """The checklist; the template it would use and the documents to link go to the writers only (AC7)."""
    staff = user.role in STAFF
    checklist = await svc.get(db, item.id)
    template = await templates.resolve(db, item, svc.KIND) if staff and checklist is None else None
    return {
        "checklist": await svc.view(db, item, checklist),
        "template": {"id": template.id, "name": template.name, "version": template.version, "gate_mode": template.gate_mode} if template else None,
        "documents": await svc.linkable(db, item) if staff else [],
        "student_id": item.student_id if staff else None,  # ccrm-020: the writers request a missing item from this student's login
    }


async def _saved(db: AsyncSession, user: User, item: OverseasApplication, action: str, metadata: dict) -> dict:
    await svc.sync_completion(db, item)
    await _audit(db, user, f"overseas.application.checklist.{action}", "overseas_application", item.id, metadata)
    await db.commit()
    logger.info("application_checklist_changed", extra={"extra_fields": {"application_id": str(item.id), "action": action, "actor_id": str(user.id)}})
    return await _response(db, user, item)


@router.get("/{application_id}/checklist")
async def get_checklist(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, READERS, "overseas")
    return await _response(db, user, await _assigned_application(db, user, application_id))


@router.post("/{application_id}/checklist", status_code=201)
async def create_checklist(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """From the matching admission template (version and gate mode frozen) or empty in warn mode (AC4/AC5); 409 when it exists."""
    item = await _writable(db, user, application_id, moves_stage=False)
    if await svc.get(db, item.id) is not None:
        raise HTTPException(409, svc.EXISTS)
    checklist = await svc.create(db, user, item)
    return await _saved(db, user, item, "create", {"template_id": str(checklist.template_id) if checklist.template_id else None, "template_version": checklist.template_version})


@router.post("/{application_id}/checklist/items", status_code=201)
async def add_checklist_item(application_id: UUID, payload: ChecklistTemplateItemIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _writable(db, user, application_id, moves_stage=False)
    added = await svc.add_item(db, user, item, payload)
    return await _saved(db, user, item, "item_add", {"item_id": str(added.id), "document_type": added.document_type, "required": added.required})


@router.patch("/{application_id}/checklist/items/{item_id}")
async def mark_checklist_item(application_id: UUID, item_id: UUID, payload: ApplicationChecklistMark, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _writable(db, user, application_id, moves_stage=False)
    await svc.set_mark(db, user, item, item_id, payload.mark)
    return await _saved(db, user, item, "item_mark", {"item_id": str(item_id), "mark": payload.mark})


@router.delete("/{application_id}/checklist/items/{item_id}")
async def remove_checklist_item(application_id: UUID, item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC8: counselor-added items only."""
    item = await _writable(db, user, application_id, moves_stage=False)
    removed = await svc.remove_item(db, item, item_id)
    return await _saved(db, user, item, "item_remove", {"item_id": str(item_id), "document_type": removed.document_type})


@router.put("/{application_id}/checklist/items/{item_id}/documents/{document_id}")
async def link_checklist_document(application_id: UUID, item_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _writable(db, user, application_id, moves_stage=False)
    await svc.link(db, user, item, item_id, document_id)
    return await _saved(db, user, item, "link", {"item_id": str(item_id), "document_id": str(document_id)})


@router.delete("/{application_id}/checklist/items/{item_id}/documents/{document_id}")
async def unlink_checklist_document(application_id: UUID, item_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await _writable(db, user, application_id, moves_stage=False)
    await svc.unlink(db, item, item_id, document_id)
    return await _saved(db, user, item, "unlink", {"item_id": str(item_id), "document_id": str(document_id)})
