"""csc-002 (DEC-SCOPE-227) -- an overseas counselor's walk-in students: create a login (the student sets their own password from the
emailed ENH-003 link) and list the students linked to the counselor (csc-001). API_CONTRACT.md §12EM; RBAC_MATRIX.md §2.149.
csc-003 (DEC-SCOPE-228) -- while such an account is pending: resend the link, or fix name/phone/email. API §12EN; RBAC §2.150.
csc-005 (DEC-SCOPE-230) -- the Overseas Admin moves a student to another counselor. API §12EP; RBAC §2.152.
ccrm-010 (DEC-SCOPE-241) -- internal notes on a student (the counselling history), counselor and Overseas Admin. API §12ET; RBAC §2.156.
ccrm-009 (DEC-SCOPE-253) -- the student 360's read-only tabs (overview, documents, activities, history), counselor and Overseas Admin.
API §12FF; RBAC §2.168."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import CounselorStudentCreate, CounselorStudentUpdate, OverseasApplicationCounselorAssign, StudentNoteCreate
from app.services import counselor_student_360, counselor_students, student_notes, student_profiles

logger = logging.getLogger("app.counselor_students")
router = APIRouter(prefix="/counselor/students", tags=["counselor-students"])
admin_router = APIRouter(prefix="/admin/users", tags=["counselor-students"])


@router.get("")
async def list_students(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    return await counselor_students.page(db, user, limit, offset)


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
    result = await counselor_students.assign_counselor(db, user, user_id, payload.counselor_id)
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


@router.get("/{student_id}/activities")
async def student_activities(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.activities(db, user, student)


@router.get("/{student_id}/history")
async def student_history(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return await counselor_student_360.history(db, student)
