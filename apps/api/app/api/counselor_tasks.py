"""ccrm-029 (DEC-SCOPE-250, T1-T8): counselor tasks. The overseas counselor works their own; the Overseas Admin (and Super Admin) works
everyone's (CC3). Every write locks its row, adds an audit row and commits once here; a log line follows the commit (ids and field
names only). Spec: docs/superpowers/specs/2026-10-24-ccrm-029-counselor-tasks-design.md."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CounselorTask, User
from app.schemas import CounselorTaskBand, CounselorTaskCreate, CounselorTaskUpdate
from app.services import counselor_tasks as svc

router = APIRouter(prefix="/counselor/tasks", tags=["counselor-tasks"])


@router.get("")
async def list_tasks(
    band: CounselorTaskBand | None = None,
    counselor_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T6: without `band`, overdue, today, upcoming and done in the last 7 days. `counselor_id` narrows the admin's list; a counselor
    always gets their own."""
    svc.require_access(user)
    where = svc.scope(user)
    if counselor_id is not None and svc.is_admin(user):
        where = [CounselorTask.counselor_user_id == counselor_id]
    return await svc.page(db, user, where=where, band=band, limit=limit, offset=offset)


@router.get("/options")
async def task_options(counselor_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_access(user)
    return await svc.options(db, user, counselor_id)


@router.post("", status_code=201)
async def create_task(payload: CounselorTaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry adds a second task)."""
    svc.require_access(user)
    task = await svc.create(db, user, payload.model_dump())
    await db.commit()
    svc.log("counselor_task_created", user, task.id)
    return await svc.one(db, user, task.id)


@router.get("/{task_id}")
async def get_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_access(user)
    return await svc.one(db, user, task_id)


@router.patch("/{task_id}")
async def change_task(task_id: UUID, payload: CounselorTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A partial change; nothing changed = nothing recorded. Cancelled is final (409)."""
    svc.require_access(user)
    task = await svc.load(db, user, task_id)
    changed = await svc.change(db, user, task, payload.model_dump(exclude_unset=True))
    await db.commit()
    if changed:
        svc.log("counselor_task_changed", user, task_id, changed=changed)
    return await svc.one(db, user, task_id)
