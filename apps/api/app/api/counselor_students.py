"""csc-002 (DEC-SCOPE-227) -- an overseas counselor's walk-in students: create a login (the student sets their own password from the
emailed ENH-003 link) and list the students linked to the counselor (csc-001). API_CONTRACT.md §12EM; RBAC_MATRIX.md §2.149.
csc-003 (DEC-SCOPE-228) -- while such an account is pending: resend the link, or fix name/phone/email. API §12EN; RBAC §2.150."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import CounselorStudentCreate, CounselorStudentUpdate
from app.services import counselor_students
from app.services.provisioning import IssuedWelcome, deliver_welcome_link

logger = logging.getLogger("app.counselor_students")
router = APIRouter(prefix="/counselor/students", tags=["counselor-students"])


async def _deliver(student: User, issued: IssuedWelcome, counselor: User) -> dict:
    """After the commit. AGN-001/002 S3: only an admin may see the link token, so a counselor never can."""
    delivery = await deliver_welcome_link(user=student, issued=issued, issued_by=counselor)
    delivery.pop("development_welcome_token", None)
    return delivery


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
    return {"student": out, **await _deliver(student, issued, user)}


@router.post("/{student_id}/welcome-links", status_code=201)
async def resend_link(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    student, issued = await counselor_students.resend_link(db, user, student_id)
    out = counselor_students.student_out(student, "pending_setup")
    await db.commit()
    logger.info("counselor_student_link_resent", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id)}})
    return {"student": out, **await _deliver(student, issued, user)}


@router.patch("/{student_id}")
async def update_student(student_id: UUID, payload: CounselorStudentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    counselor_students.require_overseas_counselor(user)
    student, setup, issued = await counselor_students.update_student(db, user, student_id, payload.model_dump(exclude_unset=True))
    out = counselor_students.student_out(student, setup)
    await db.commit()
    if issued is None:
        return {"student": out}
    logger.info("counselor_student_email_changed", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student_id)}})
    return {"student": out, **await _deliver(student, issued, user)}
