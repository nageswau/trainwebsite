"""csc-002 (DEC-SCOPE-227) -- an overseas counselor's walk-in students: create a login (the student sets their own password from the
emailed ENH-003 link) and list the students linked to the counselor (csc-001). API_CONTRACT.md §12EM; RBAC_MATRIX.md §2.149.
csc-003 (DEC-SCOPE-228) -- while such an account is pending: resend the link, or fix name/phone/email. API §12EN; RBAC §2.150.
csc-005 (DEC-SCOPE-230) -- the Overseas Admin moves a student to another counselor. API §12EP; RBAC §2.152.
ccrm-010 (DEC-SCOPE-241) -- internal notes on a student (the counselling history), counselor and Overseas Admin. API §12ET; RBAC §2.156.
ccrm-009 (DEC-SCOPE-253) -- the student 360's read-only tabs (overview, documents, activities, history), counselor and Overseas Admin.
API §12FF; RBAC §2.168.
ccrm-040 (DEC-SCOPE-276) -- archive instead of delete: the student's counselor or the Overseas Admin archives, the Admin restores, both
list archived students. API §12GC; RBAC §2.190.
ccrm-045 (DEC-SCOPE-318) -- the 360's Documents tab uploads a document for the student, with or without an application. API §12HP;
RBAC §2.224."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_documents import APPLICATION_MISMATCH, OFFER_LETTER_NEEDS_APPLICATION
from app.api.deps import get_current_user
from app.api.workflows import _audit
from app.core.database import get_db
from app.models import OverseasApplication, StudentDocument, User
from app.schemas import AgentUploadDocumentType, CounselorStudentCreate, CounselorStudentUpdate, OverseasApplicationCounselorAssign, StudentArchiveCreate, StudentNoteCreate
from app.services import agent_documents as documents
from app.services import application_outcomes as outcomes
from app.services import counselor_student_360, counselor_students, student_archive, student_notes, student_profiles

APPLICATION_NOT_YOURS = "Choose one of your own applications for this student"

logger = logging.getLogger("app.counselor_students")
router = APIRouter(prefix="/counselor/students", tags=["counselor-students"])
admin_router = APIRouter(prefix="/admin/users", tags=["counselor-students"])
StudentSource = Literal["walk_in", "lead_conversion", "self_registered", "agency"]  # ccrm-043: the list's Source filter


@router.get("")
async def list_students(
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), source: StudentSource | None = None, q: str | None = Query(None, max_length=100),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):  # fmt: skip
    """ccrm-043 (DEC-SCOPE-317): all the counselor's students; `source` and `q` narrow the list (API §12HO)."""
    counselor_students.require_overseas_counselor(user)
    return await counselor_students.page(db, user, limit, offset, source, q)


@router.get("/archived")
async def list_archived(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await student_archive.page(db, user, limit, offset)


@router.post("/{student_id}/archive")
async def archive_student(student_id: UUID, payload: StudentArchiveCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    archived = await student_archive.archive(db, user, student_id, payload.reason)
    await db.commit()
    logger.info("student_archived", extra={"extra_fields": {"actor_id": str(user.id), "actor_role": user.role, "student_id": str(student_id)}})
    return archived


@router.post("/{student_id}/restore")
async def restore_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    restored = await student_archive.restore(db, user, student_id)
    await db.commit()
    logger.info("student_restored", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id)}})
    return restored


@router.post("", status_code=201)
async def create_student(payload: CounselorStudentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    student, issued = await counselor_students.create_student(db, user, payload)
    out = counselor_students.student_out(student, "pending_setup")
    await db.commit()
    logger.info("counselor_student_created", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(out["id"])}})
    return {"student": out, **await counselor_students.deliver_link(student, issued, user)}


@router.post("/{student_id}/welcome-links", status_code=201)
async def resend_link(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    student, issued = await counselor_students.resend_link(db, user, student_id)
    out = counselor_students.student_out(student, "pending_setup")
    await db.commit()
    logger.info("counselor_student_link_resent", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id)}})
    return {"student": out, **await counselor_students.deliver_link(student, issued, user)}


@router.patch("/{student_id}")
async def update_student(student_id: UUID, payload: CounselorStudentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    student, setup, issued = await counselor_students.update_student(db, user, student_id, payload.model_dump(exclude_unset=True))
    out = counselor_students.student_out(student, setup)
    await db.commit()
    if issued is None:
        return {"student": out}
    logger.info("counselor_student_email_changed", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id)}})
    return {"student": out, **await counselor_students.deliver_link(student, issued, user)}


@router.get("/{student_id}/notes")
async def list_notes(student_id: UUID, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await student_notes.page(db, user, student_id, limit, offset)


@router.post("/{student_id}/notes", status_code=201)
async def add_note(student_id: UUID, payload: StudentNoteCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    note = await student_notes.create(db, user, student_id, payload)
    logger.info("student_note_created", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id), "note_id": str(note["id"])}})
    return note


@admin_router.put("/{user_id}/counselor")
async def assign_student_counselor(user_id: UUID, payload: OverseasApplicationCounselorAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """csc-005: AGN-023's assign body (swap only); the same counselor is `changed: false`."""
    result = await counselor_students.assign_counselor(db, user, user_id, payload.counselor_id, payload.reason)
    if result["changed"]:
        await db.commit()
        logger.info("student_counselor_assigned", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(user_id), "counselor_id": str(result["counselor_id"])}})
    return result


# ccrm-009 (DEC-SCOPE-253): ccrm-007's gate -- csc-001 scope or the Overseas Admin; another student is a 404, another role a 403.
@router.get("/{student_id}/overview")
async def student_overview(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.overview(db, user, student)


@router.get("/{student_id}/documents")
async def student_documents(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.documents(db, user, student)


@router.post("/{student_id}/documents", status_code=201)
async def upload_student_document(
    student_id: UUID,
    document_type: AgentUploadDocumentType = Form(...),
    document_label: str | None = Form(None, max_length=200),
    application_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ccrm-045: the tab's gate first (another student 404, another role 403), then the archive, the type and the application rules,
    and only then the file (AGN-009 G7/G8: sniffed type, 20 MB, server key). Always visible to the student; pending until reviewed."""
    student = await student_profiles.staff_student(db, user, student_id)
    if await student_archive.is_archived(db, student.id):
        raise HTTPException(409, student_archive.NO_NEW_APPLICATION)
    label = documents.clean_label(document_type, document_label)
    if document_type == documents.OFFER_LETTER and application_id is None:
        raise HTTPException(422, OFFER_LETTER_NEEDS_APPLICATION)
    if application_id is not None:
        application = await db.get(OverseasApplication, application_id)
        if application is None or application.student_id != student.id:
            raise HTTPException(422, APPLICATION_MISMATCH)
        if user.role == "counselor" and application.counselor_id != user.id:  # the Overseas Admin any of the student's
            raise HTTPException(403, APPLICATION_NOT_YOURS)
        outcomes.refuse_closed(application)
    data, content_type, filename = await documents.read_upload(file)
    key = documents.store(data, content_type)
    try:
        item = StudentDocument(
            student_id=student.id,
            application_id=application_id,
            document_type=document_type,
            document_label=label,
            file_url=key,
            verification_status="pending",
            original_filename=filename,
            content_type=content_type,
            file_size=len(data),
            uploaded_by_user_id=user.id,
        )
        db.add(item)
        await db.flush()
        documents.add_event(db, event="uploaded", actor=user, document=item, to_status="pending")
        await _audit(db, user, "document.upload", "student_document", item.id, {"document_type": document_type, "application_id": str(application_id) if application_id else None})
        await db.commit()
    except Exception:  # nothing was written: the stored object goes too
        await db.rollback()
        documents.discard(key)
        raise
    logger.info("counselor_document_uploaded", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "document_id": str(item.id), "document_type": document_type}})
    return {
        "document": {
            "id": item.id, "name": label or filename or document_type, "document_type": document_type, "application_id": application_id,
            "status": item.verification_status,
        }
    }  # fmt: skip


# ccrm-039 (DEC-SCOPE-275): the finance tab -- read-only, the same gate.
@router.get("/{student_id}/finance")
async def student_finance(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.finance(db, user, student)


@router.get("/{student_id}/activities")
async def student_activities(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.activities(db, user, student)


@router.get("/{student_id}/history")
async def student_history(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.history(db, student)
