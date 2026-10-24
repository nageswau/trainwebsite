"""ccrm-007 (DEC-SCOPE-249) -- the structured overseas student profile: the counselor (csc-001 scope) and the Overseas Admin on
/counselor/students/{id}/profile, the student on /overseas/me/profile. A save replaces the whole profile. API_CONTRACT.md §12FB;
RBAC_MATRIX.md §2.164. The agency's read-only view is in api/agent_students.py."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import StudentProfileSave
from app.services import student_profiles

logger = logging.getLogger("app.student_profiles")
router = APIRouter(prefix="/counselor/students", tags=["student-profiles"])
me_router = APIRouter(prefix="/overseas/me", tags=["student-profiles"])


def _student_out(student: User) -> dict:
    return {"id": student.id, "full_name": student.full_name, "student_code": student.student_code}


def _log(actor: User, student_id: UUID) -> None:
    logger.info("student_profile_saved", extra={"extra_fields": {"actor_id": str(actor.id), "actor_role": actor.role, "student_id": str(student_id)}})


@router.get("/{student_id}/profile")
async def get_profile(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    return {"student": _student_out(student), "profile": await student_profiles.read(db, student.id)}


@router.put("/{student_id}/profile")
async def save_profile(student_id: UUID, payload: StudentProfileSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await student_profiles.staff_student(db, user, student_id)
    out = _student_out(student)
    profile = await student_profiles.save(db, user, student, payload)
    _log(user, student_id)
    return {"student": out, "profile": profile}


@me_router.get("/profile")
async def get_my_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = student_profiles.require_student(user)
    return {"student": _student_out(student), "profile": await student_profiles.read(db, student.id)}


@me_router.put("/profile")
async def save_my_profile(payload: StudentProfileSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = student_profiles.require_student(user)
    out = _student_out(student)
    profile = await student_profiles.save(db, user, student, payload)
    _log(user, user.id)
    return {"student": out, "profile": profile}
