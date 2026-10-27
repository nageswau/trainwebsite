"""nehn-039 -- a school's read of its students' overseas document statuses (spec
docs/superpowers/specs/2026-10-27-nehn-039-school-document-statuses-design.md, D1-D7, `NEEDS_CONFIRMATION`).

Statuses only, from the ccrm-019 checklist of each School-bridged application: never files, document ids, notes or the
financial class (D3). Scope is the existing school reader rule (`_load_readable_student`); anything outside it is a 404 (D4)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import SCHOOL_ROLES, _load_readable_student
from app.application_checklists import status_label
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import ApplicationChecklist, AuditLog, OverseasApplication, SchoolStudent, University, User
from app.schemas import SchoolDocumentStatusesOut
from app.services import application_checklists

router = APIRouter(prefix="/school", tags=["school-documents"])
logger = get_logger("app.school.documents")

HIDDEN_SENSITIVITY = "financial"  # D3
NOT_FOUND = "Student not found"
VIEW_ACTION = "school.document_statuses_view"


async def _student_in_scope(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """D4: a wrong role is 403; a student outside the reader's scope is indistinguishable from a missing one (404)."""
    if user.role not in SCHOOL_ROLES:
        raise HTTPException(403, "School role required")
    try:
        return await _load_readable_student(db, user, student_id)
    except HTTPException as exc:
        if exc.status_code not in (403, 404):
            raise
        logger.warning("school_document_statuses_refused", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "student_id": str(student_id), "reason": exc.detail}})
        raise HTTPException(404, NOT_FOUND) from None


@router.get("/students/{student_id}/document-statuses", response_model=SchoolDocumentStatusesOut)
async def student_document_statuses(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _student_in_scope(db, user, student_id)
    rows = (
        await db.execute(
            select(OverseasApplication.id, University.name)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.school_student_id == student.id)
            .order_by(OverseasApplication.created_at.desc(), OverseasApplication.id)
        )
    ).all()
    with_checklist = set((await db.scalars(select(ApplicationChecklist.application_id).where(ApplicationChecklist.application_id.in_([a for a, _ in rows])))).all()) if rows else set()
    applications, item_count = [], 0
    for application_id, university_name in rows:
        items = [
            {"name": i["name"], "required": i["required"], "status": i["status"], "status_label": status_label(i["status"])}
            for i in (await application_checklists.item_statuses(db, application_id) if application_id in with_checklist else [])
            if i["sensitivity"] != HIDDEN_SENSITIVITY
        ]
        applications.append({"application_id": application_id, "university_name": university_name, "has_checklist": application_id in with_checklist, "items": items})
        item_count += len(items)

    db.add(
        AuditLog(
            user_id=user.id,
            action=VIEW_ACTION,
            entity_type="school_student",
            entity_id=str(student.id),
            metadata_json={"school_id": str(student.school_id), "applications": len(applications), "items": item_count},
        )
    )
    await db.commit()
    logger.info(
        "school_document_statuses_view", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "student_id": str(student.id), "applications": len(applications), "items": item_count}}
    )
    return {"student_id": student.id, "applications": applications}
