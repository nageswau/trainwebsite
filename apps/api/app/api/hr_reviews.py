"""itc-027 (DEC-SCOPE-354) -- the HR resume-review task: HR's own queue and task (/hr/review-tasks, /hr/students/{id}/review), the IT
Admin's task list, reassignment and programme rules (/admin/it/hr-review-tasks, /admin/it/hr-assignment-rules), the read-only card on the
counselor / IT Admin student record (/counselor|admin/it/students/{id}/hr-review) and the student's safe status (/it/me/hr-review).
API_CONTRACT.md §12IZ; RBAC_MATRIX.md §2.254."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import HR_REVIEW_STAGES, User
from app.schemas import HrAssignmentRuleIn, HrReviewOwnerIn, HrReviewPatch
from app.services import hr_reviews as svc

hr_router = APIRouter(prefix="/hr", tags=["hr-reviews"])
admin_router = APIRouter(prefix="/admin/it", tags=["hr-reviews"])
counselor_router = APIRouter(prefix="/counselor/it/students", tags=["hr-reviews"])
me_router = APIRouter(prefix="/it/me/hr-review", tags=["hr-reviews"])

Stage = Literal[HR_REVIEW_STAGES]


@hr_router.get("/review-tasks")
async def my_queue(stage: Stage | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    return await svc.queue(db, user, stage, limit, offset)


@hr_router.get("/students/{student_id}/review")
async def my_task(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.read(db, user, student_id)


@hr_router.patch("/students/{student_id}/review")
async def save_my_task(student_id: UUID, payload: HrReviewPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.save(db, user, student_id, payload)


@admin_router.get("/hr-review-tasks")
async def all_tasks(stage: Stage | None = None, unassigned: bool = False, limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
                    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    return await svc.admin_tasks(db, user, stage, unassigned, limit, offset)


@admin_router.put("/hr-review-tasks/{task_id}/owner")
async def reassign(task_id: UUID, payload: HrReviewOwnerIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.assign(db, user, task_id, payload.hr_user_id)


@admin_router.get("/hr-assignment-rules")
async def assignment_rules(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.rules(db, user)


@admin_router.put("/hr-assignment-rules/{program_id}")
async def save_assignment_rule(program_id: UUID, payload: HrAssignmentRuleIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.save_rule(db, user, program_id, payload.hr_user_id)


@admin_router.get("/students/{student_id}/hr-review")
async def admin_student_review(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.staff_view(db, user, student_id, "admin")


@counselor_router.get("/{student_id}/hr-review")
async def counselor_student_review(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.staff_view(db, user, student_id, "counselor")


@me_router.get("")
async def my_review(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.student_view(db, user)
