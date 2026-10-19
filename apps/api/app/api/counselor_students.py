"""csc-002 (DEC-SCOPE-227) -- an overseas counselor's walk-in students: create a login (the student sets their own password from the
emailed ENH-003 link) and list the students linked to the counselor (csc-001). API_CONTRACT.md §12EM; RBAC_MATRIX.md §2.149."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import CounselorStudentCreate
from app.services import counselor_students
from app.services.provisioning import deliver_welcome_link

logger = logging.getLogger("app.counselor_students")
router = APIRouter(prefix="/counselor/students", tags=["counselor-students"])


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
    delivery = await deliver_welcome_link(user=student, issued=issued, issued_by=user)
    delivery.pop("development_welcome_token", None)  # AGN-001/002 S3: only an admin may see the link token, so a counselor never can
    return {"student": out, **delivery}
