"""mgmt-028 (spec MT1-MT14): the management to-do. `router` is the operational tier's (partner, super_admin; M13); `me_router` is each
staff member's own "Management tasks" (MT9). Every write locks its row, adds a management audit row and commits once here; a log line
follows the commit (ids and field names only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import ManagementTask, User
from app.schemas import DiscussionOptions, MyTaskOut, MyTaskPage, MyTaskStatusIn, TaskBand, TaskCreate, TaskOut, TaskPage, TaskUpdate
from app.services import management_audit
from app.services import management_discussions as discussions
from app.services import management_tasks as svc
from app.services.bdm_travel import india_today

router = APIRouter(prefix="/management/tasks", tags=["management-tasks"])
me_router = APIRouter(prefix="/me/management-tasks", tags=["management-tasks"])


def _owner_filter(user: User, owner: str | None) -> list:
    """`me` or one user id; anything else is a 422."""
    if owner is None:
        return []
    if owner == "me":
        return [ManagementTask.owner_user_id == user.id]
    try:
        return [ManagementTask.owner_user_id == UUID(owner)]
    except ValueError:
        raise HTTPException(422, "owner must be me or a user id") from None


@router.get("", response_model=TaskPage)
async def list_tasks(
    owner: str | None = None,
    band: TaskBand | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MT3/MT4: without `band`, every band but cancelled (completed for the last 7 days), as the §28 list shows them."""
    discussions.require_operational(user)
    return await svc.page(db, where=_owner_filter(user, owner), band=band, limit=limit, offset=offset)


@router.get("/options", response_model=DiscussionOptions)
async def task_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The form's owners: active staff users (MT6)."""
    discussions.require_operational(user)
    return await discussions.options(db)


@router.post("", status_code=201, response_model=TaskOut)
async def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    state = payload.model_dump()
    await svc.check(db, state)
    status = state.pop("status")
    task = ManagementTask(**state, status="open", created_by_user_id=user.id, updated_by_user_id=user.id)
    svc.set_status(task, status)  # a task recorded as already completed gets its completed_at
    db.add(task)
    await db.flush()
    management_audit.record(db, user, "mgmt.task", "create", str(task.id), fields=list(svc.FIELDS))
    await svc.notify_after_write(db, user, task, list(svc.FIELDS), None)
    await db.commit()
    svc.log("task_created", user, task.id)
    return await svc.one(db, task.id)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    return await svc.one(db, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
async def change_task(task_id: UUID, payload: TaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A partial change; nothing changed = nothing recorded. The owner hears about a new assignment or a changed task."""
    discussions.require_operational(user)
    task = await svc.load(db, task_id)
    before = {f: getattr(task, f) for f in svc.FIELDS}
    state = {**before, **payload.model_dump(exclude_unset=True)}
    await svc.check(db, state, before)
    changed = [f for f in svc.FIELDS if state[f] != before[f]]
    if changed:
        for field in changed:
            if field != "status":
                setattr(task, field, state[field])
        svc.set_status(task, state["status"])
        task.updated_by_user_id = user.id
        svc.audit(db, user, task, changed, before["status"])
        await svc.notify_after_write(db, user, task, changed, before["owner_user_id"])
        await db.commit()
        svc.log("task_changed", user, task.id, changed=changed)
    return await svc.one(db, task.id)


# --- the owner's slice (MT9) ---------------------------------------------------------------------------------------------------
@me_router.get("", response_model=MyTaskPage)
async def my_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.mine(db, user)


@me_router.patch("/{task_id}", response_model=MyTaskOut)
async def update_my_task(task_id: UUID, payload: MyTaskStatusIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    task = await svc.load(db, task_id, owner=user)
    if task.status == "cancelled":
        raise HTTPException(409, svc.CANCELLED)
    if task.status != payload.status:
        previous = task.status
        svc.set_status(task, payload.status)
        task.updated_by_user_id = user.id
        svc.audit(db, user, task, ["status"], previous)
        await db.commit()
        await db.refresh(task)
        svc.log("my_task_status_changed", user, task.id, from_status=previous, to_status=payload.status)
    return svc.my_out(task, india_today())
