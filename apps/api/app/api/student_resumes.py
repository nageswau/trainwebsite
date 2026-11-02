"""itc-026 (DEC-SCOPE-350) -- the IT student's resume versions: the student on /it/me/resumes, their itc-003 counselor on
/counselor/it/students/{id}/resumes, the IT Admin on /admin/it/students/{id}/resumes (all three upload), HR on /hr/students/{id}/resumes
(read only, `hr` versions), and the IT Admin's limit on /admin/it/resume-settings. API_CONTRACT.md §12IV; RBAC_MATRIX.md §2.250."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi import Path as PathParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import StudentResumeSettingsIn
from app.services import student_resumes as svc

me_router = APIRouter(prefix="/it/me/resumes", tags=["it-student-resumes"])
counselor_router = APIRouter(prefix="/counselor/it/students", tags=["it-student-resumes"])
admin_router = APIRouter(prefix="/admin/it/students", tags=["it-student-resumes"])
hr_router = APIRouter(prefix="/hr/students", tags=["it-student-resumes"])
settings_router = APIRouter(prefix="/admin/it/resume-settings", tags=["it-student-resumes"])

VERSION = PathParam(ge=1, le=100_000)


@me_router.get("")
async def my_resumes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.listing(db, await svc.student_for(db, user, None, "me"))


@me_router.post("", status_code=201)
async def upload_my_resume(file: UploadFile = File(...), visibility: str = Form("hr"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.upload(db, user, await svc.student_for(db, user, None, "me"), file, visibility)


@me_router.get("/{version}/file")
async def download_my_resume(version: int = VERSION, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.download(db, user, await svc.student_for(db, user, None, "me"), version)


def _staff_routes(router: APIRouter, portal: str) -> None:
    @router.get("/{student_id}/resumes")
    async def resumes(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        return await svc.listing(db, await svc.student_for(db, user, student_id, portal))

    @router.post("/{student_id}/resumes", status_code=201)
    async def upload_resume(student_id: UUID, file: UploadFile = File(...), visibility: str = Form("hr"), user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):  # fmt: skip
        return await svc.upload(db, user, await svc.student_for(db, user, student_id, portal), file, visibility)

    @router.get("/{student_id}/resumes/{version}/file")
    async def download_resume(student_id: UUID, version: int = VERSION, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        return await svc.download(db, user, await svc.student_for(db, user, student_id, portal), version)


_staff_routes(counselor_router, "counselor")
_staff_routes(admin_router, "admin")


@hr_router.get("/{student_id}/resumes")
async def hr_resumes(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.listing(db, await svc.student_for(db, user, student_id, "hr"), hr_only=True)


@hr_router.get("/{student_id}/resumes/{version}/file")
async def hr_download_resume(student_id: UUID, version: int = VERSION, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.download(db, user, await svc.hr_download_student(db, user, student_id), version, hr_only=True)


@settings_router.get("")
async def resume_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_admin(user)
    return svc.settings_out(await svc.max_bytes(db))


@settings_router.put("")
async def save_resume_settings(payload: StudentResumeSettingsIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.save_settings(db, user, payload.max_mb)
