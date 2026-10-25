"""ccrm-020 (DEC-SCOPE-265) -- document requests to a direct student. API_CONTRACT.md §12FR; RBAC_MATRIX.md §2.179.

Staff (counselor in csc-001 scope, Overseas Admin; ccrm-007's `staff_student` gate -- another student is a 404) list, create and cancel
under the student; a checklist / application request takes the checklist writers' entry (`application_offers._writable`: scope, row lock,
closed refusals). The student lists their own requests and uploads against an open one with the AGN-009 file rules (bytes decide the type,
server-generated key, the stored object deleted again if the commit fails). Every write audits and commits once; notices go to the
student (create / cancel, never the note) and to the requester (upload). Spec: docs/superpowers/specs/2026-10-25-ccrm-020-document-requests-design.md.
"""

import logging
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.application_offers import _writable
from app.api.deps import get_current_user
from app.api.workflows import _audit, _notify_user
from app.core.database import get_db
from app.models import StudentDocument, User
from app.schemas import StudentDocumentRequestCreate
from app.services import agent_documents as files
from app.services import student_document_requests as svc
from app.services.student_profiles import require_student, staff_student

logger = logging.getLogger("app.student_document_requests")

router = APIRouter(prefix="/counselor/students", tags=["student-document-requests"])
me_router = APIRouter(prefix="/overseas/me", tags=["student-document-requests"])

STUDENT_URL = "/overseas/student/documents"


def _staff_url(student_id: UUID) -> str:
    return f"/overseas/counselor/students/{student_id}?tab=documents"


@router.get("/{student_id}/document-requests")
async def list_requests(
    student_id: UUID,
    status: Literal["open", "all"] = "all",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    student = await staff_student(db, user, student_id)
    return await svc.page(db, student.id, status=status, limit=limit, offset=offset)


@router.post("/{student_id}/document-requests", status_code=201)
async def create_request(student_id: UUID, payload: StudentDocumentRequestCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await staff_student(db, user, student_id)
    await svc.lock_student(db, student)
    application = await _writable(db, user, payload.application_id, moves_stage=False) if payload.application_id else None
    request = await svc.create(db, user, student, payload, application)
    await _notify_user(db, student, "Document requested", f"{svc.name(request)}: please upload it by {request.due_date:%d %b %Y}.", STUDENT_URL)
    await _audit(db, user, "document_request.create", "document_request", request.id, {"student_id": str(student.id), "document_type": request.document_type})
    await db.commit()
    logger.info("student_document_requested", extra={"extra_fields": {"request_id": str(request.id), "student_id": str(student.id), "actor_id": str(user.id)}})
    return {"request": await svc.view(db, request.id)}


@router.post("/{student_id}/document-requests/{request_id}/cancel")
async def cancel_request(student_id: UUID, request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await staff_student(db, user, student_id)
    request = await svc.cancel(db, user, request_id, student.id)
    await _notify_user(db, student, "Document request cancelled", f"{svc.name(request)}: you no longer need to upload it.", STUDENT_URL)
    await _audit(db, user, "document_request.cancel", "document_request", request.id, {"student_id": str(student.id)})
    await db.commit()
    logger.info("student_document_request_cancelled", extra={"extra_fields": {"request_id": str(request.id), "actor_id": str(user.id)}})
    return {"request": await svc.view(db, request.id)}


@me_router.get("/document-requests")
async def my_requests(
    status: Literal["open", "all"] = "open",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_student(user)
    return await svc.page(db, user.id, status=status, limit=limit, offset=offset)


@me_router.post("/document-requests/{request_id}/upload", status_code=201)
async def upload_against_request(
    request_id: UUID,
    file: UploadFile = File(...),
    expiry_date: date | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_student(user)
    data, content_type, filename = await files.read_upload(file)
    request = await svc.open_request(db, request_id, user.id)
    key = files.store(data, content_type)
    try:
        document = StudentDocument(
            student_id=user.id,
            application_id=request.application_id,
            document_type=request.document_type,
            document_label=request.document_label,
            file_url=key,
            verification_status="pending",
            original_filename=filename,
            content_type=content_type,
            file_size=len(data),
            uploaded_by_user_id=user.id,
            fulfils_request_id=request.id,
            expiry_date=expiry_date,
        )
        db.add(document)
        await db.flush()
        files.add_event(db, event="uploaded", actor=user, document=document, to_status="pending")
        await svc.fulfil(db, user, request, document)
        requester = await db.get(User, request.requested_by_user_id) if request.requested_by_user_id else None
        if requester is not None and requester.active:
            await _notify_user(db, requester, "Document uploaded", f"{user.full_name} uploaded {svc.name(request)}.", _staff_url(user.id))
        await _audit(db, user, "document.upload", "student_document", document.id, {"request_id": str(request.id)})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too (AGN-009's order)
        await db.rollback()
        files.discard(key)
        raise
    logger.info("student_document_request_fulfilled", extra={"extra_fields": {"request_id": str(request_id), "document_id": str(document.id), "actor_id": str(user.id)}})
    return {"request": await svc.view(db, request_id), "document_id": document.id}
