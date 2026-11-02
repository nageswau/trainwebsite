"""itc-012 (DEC-SCOPE-345) -- the IT student record: the student on /it/me/profile, their itc-003 counselor on
/counselor/it/students/{id}/..., the IT Admin on /admin/it/students/{id}/.... PATCH changes only the fields sent. API_CONTRACT.md §12IQ;
RBAC_MATRIX.md §2.245. Logs carry ids only (the profile is personal data)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import ItEnrollmentOverridePatch, ItStudentProfilePatch
from app.services import it_student_profiles as profiles

logger = logging.getLogger("app.it_student_profiles")
me_router = APIRouter(prefix="/it/me", tags=["it-student-profiles"])
counselor_router = APIRouter(prefix="/counselor/it/students", tags=["it-student-profiles"])
admin_router = APIRouter(prefix="/admin/it/students", tags=["it-student-profiles"])


def _log(event: str, actor: User, student_id: UUID) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), "actor_role": actor.role, "student_id": str(student_id)}})


@me_router.get("/profile")
async def get_my_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await profiles.read(db, profiles.require_student(user))


@me_router.patch("/profile")
async def save_my_profile(payload: ItStudentProfilePatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out = await profiles.save(db, user, profiles.require_student(user), payload)
    _log("it_student_profile_saved", user, user.id)
    return out


def _staff_routes(router: APIRouter, portal: str) -> None:
    @router.get("/{student_id}/profile")
    async def get_profile(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        return await profiles.read(db, await profiles.staff_student(db, user, student_id, portal=portal))

    @router.patch("/{student_id}/profile")
    async def save_profile(student_id: UUID, payload: ItStudentProfilePatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        out = await profiles.save(db, user, await profiles.staff_student(db, user, student_id, portal=portal), payload)
        _log("it_student_profile_saved", user, student_id)
        return out

    @router.patch("/{student_id}/enrollments/{enrollment_id}")
    async def save_enrollment(student_id: UUID, enrollment_id: UUID, payload: ItEnrollmentOverridePatch, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):  # fmt: skip
        out = await profiles.save_enrollment(db, user, await profiles.staff_student(db, user, student_id, portal=portal), enrollment_id, payload)
        _log("it_enrollment_dates_saved", user, student_id)
        return out


_staff_routes(counselor_router, "counselor")
_staff_routes(admin_router, "admin")
