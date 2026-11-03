"""itc-022 (DEC-SCOPE-365) -- progress plans (the IT Admin), topic completion (trainer / IT Admin), remediation plans and the student's
progress view. API_CONTRACT.md §12JK; RBAC_MATRIX.md §2.265. The override lives on the existing PATCH progress route (workflows.py)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import ProgressPlanIn, RemediationPlanIn, RemediationPlanPatch, TopicCompletionIn
from app.services import it_at_risk, it_progress

admin_router = APIRouter(prefix="/admin/it/progress-plans", tags=["it-progress"])
router = APIRouter(prefix="/it", tags=["it-progress"])


@admin_router.get("")
async def read_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    it_at_risk.require_admin(user)
    return await it_progress.list_plans(db)


@admin_router.get("/{program_id}")
async def read_plan(program_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    it_at_risk.require_admin(user)
    return await it_progress.read_plan(db, program_id)


@admin_router.put("/{program_id}")
async def save_plan(program_id: UUID, payload: ProgressPlanIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    it_at_risk.require_admin(user)
    return await it_progress.save_plan(db, user, program_id, payload)


@router.get("/batches/{batch_id}/topics")
async def read_batch_topics(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.batch_topics(db, user, batch_id)


@router.put("/batches/{batch_id}/topics/{topic_id}/completions")
async def save_completions(batch_id: UUID, topic_id: UUID, payload: TopicCompletionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.set_completions(db, user, batch_id, topic_id, payload)


@router.get("/students/{student_id}/remediation-plans")
async def read_remediation_plans(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.student_plans(db, user, student_id)


@router.post("/enrollments/{enrollment_id}/remediation-plans", status_code=201)
async def create_remediation_plan(enrollment_id: UUID, payload: RemediationPlanIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.create_plan(db, user, enrollment_id, payload)


@router.patch("/remediation-plans/{plan_id}")
async def update_remediation_plan(plan_id: UUID, payload: RemediationPlanPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.update_plan(db, user, plan_id, payload)


@router.get("/me/progress")
async def read_my_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await it_progress.my_progress(db, user)
