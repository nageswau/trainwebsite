"""mgmt-026 (spec PN1-PN16): the next month plan and its target vs actual, for the operational tier (partner, super_admin; M13). Every
write locks the plan row, adds a management audit row and commits once here; a log line follows the commit (ids and field names only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import ManagementPlan, ManagementPlanItem, User
from app.schemas import (
    PLAN_MONTH,
    PlanCreate,
    PlanDetailOut,
    PlanItemCreate,
    PlanItemOut,
    PlanItemTaskIn,
    PlanItemUpdate,
    PlanOptions,
    PlanPage,
    PlanProgressOut,
    PlanUpdate,
    TaskOut,
)
from app.services import management_audit
from app.services import management_discussions as discussions
from app.services import management_plans as svc
from app.services import management_tasks as tasks
from app.services.management_expenses import month_key

router = APIRouter(prefix="/management/plans", tags=["management-plans"])
Month = Path(pattern=PLAN_MONTH)


@router.get("", response_model=PlanPage)
async def list_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every plan, newest month first, with the counts of the items the caller may see."""
    discussions.require_operational(user)
    return await svc.plans(db, user)


@router.get("/options", response_model=PlanOptions)
async def plan_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The catalogue (revenue for partners only, PN7), the verticals, the task owners (mgmt-028 MT6) and the planning window."""
    discussions.require_operational(user)
    first, last = svc.window()
    return {
        "kpis": svc.kpi_options(user),
        "verticals": [{"key": key, "label": lbl} for key, lbl in svc.VERTICALS.items()],
        "users": (await discussions.options(db))["users"],
        "current_month": month_key(first),
        "max_month": month_key(last),
    }


@router.post("", status_code=201, response_model=PlanDetailOut)
async def create_plan(payload: PlanCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    month_start = svc.parse_month(payload.month)
    svc.check_window(month_start)
    plan = ManagementPlan(month=month_start, status=payload.status, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(plan)
    try:
        await db.flush()
    except IntegrityError:  # the unique month, when two people plan it at once (PN11)
        await db.rollback()
        raise HTTPException(409, svc.DUPLICATE) from None
    management_audit.record(db, user, "mgmt.plan", "create", str(plan.id), fields=["month", "status"])
    await db.commit()
    svc.log("plan_created", user, plan.id)
    return await svc.detail(db, user, month_start)


@router.get("/{month}", response_model=PlanDetailOut)
async def get_plan(month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    return await svc.detail(db, user, svc.parse_month(month))


@router.patch("/{month}", response_model=PlanDetailOut)
async def change_plan(payload: PlanUpdate, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PN3: draft / active / closed in any direction; the same status again records nothing."""
    discussions.require_operational(user)
    month_start = svc.parse_month(month)
    plan = await svc.lock(db, month_start, writable=False)
    if plan.status != payload.status:
        previous = plan.status
        plan.status, plan.updated_by_user_id = payload.status, user.id
        management_audit.record(db, user, "mgmt.plan", "update", str(plan.id), fields=["status"])
        await db.commit()
        svc.log("plan_status_changed", user, plan.id, from_status=previous, to_status=payload.status)
    return await svc.detail(db, user, month_start)


@router.get("/{month}/progress", response_model=PlanProgressOut)
async def plan_progress(month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    return await svc.progress(db, user, svc.parse_month(month))


@router.post("/{month}/items", status_code=201, response_model=PlanItemOut)
async def create_item(payload: PlanItemCreate, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    discussions.require_operational(user)
    plan = await svc.lock(db, svc.parse_month(month))
    changes = payload.model_dump()
    state = svc.merged(None, changes)
    svc.check_item(user, state, changes)
    item = ManagementPlanItem(plan_id=plan.id, **state, position=await svc.next_position(db, plan), created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(item)
    await db.flush()
    management_audit.record(db, user, "mgmt.plan", "create", str(item.id), fields=[f for f in svc.ITEM_FIELDS if state[f] not in (None, False)])
    await db.commit()
    svc.log("plan_item_created", user, item.id, plan_id=str(plan.id))
    return await svc.one_item(db, item)


@router.patch("/{month}/items/{item_id}", response_model=PlanItemOut)
async def change_item(payload: PlanItemUpdate, item_id: UUID, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A partial change; nothing changed = nothing recorded. A changed target is audited by name ("who changed a target", PN9)."""
    discussions.require_operational(user)
    plan = await svc.lock(db, svc.parse_month(month))
    item = await svc.load_item(db, user, plan, item_id)
    changes = payload.model_dump(exclude_unset=True)
    state = svc.merged(item, changes)
    svc.check_item(user, state, changes)
    changed = [f for f in svc.ITEM_FIELDS if state[f] != getattr(item, f)]
    if changed:
        for field in changed:
            setattr(item, field, state[field])
        item.updated_by_user_id = user.id
        management_audit.record(db, user, "mgmt.plan", "update", str(item.id), fields=changed)
        await db.commit()
        svc.log("plan_item_changed", user, item.id, changed=changed)
    return await svc.one_item(db, item)


@router.delete("/{month}/items/{item_id}", status_code=204)
async def delete_item(item_id: UUID, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PN13: the item goes; tasks made from it stay, with their title."""
    discussions.require_operational(user)
    plan = await svc.lock(db, svc.parse_month(month))
    item = await svc.load_item(db, user, plan, item_id)
    await db.delete(item)
    management_audit.record(db, user, "mgmt.plan", "delete", str(item_id))
    await db.commit()
    svc.log("plan_item_deleted", user, item_id, plan_id=str(plan.id))
    return Response(status_code=204)


@router.post("/{month}/items/{item_id}/tasks", status_code=201, response_model=TaskOut)
async def create_item_task(payload: PlanItemTaskIn, item_id: UUID, month: str = Month, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PN10: a mgmt-028 task titled with the item's text, `source=plan`; mgmt-028's checks, notification and audit apply."""
    discussions.require_operational(user)
    plan = await svc.lock(db, svc.parse_month(month))
    item = await svc.load_item(db, user, plan, item_id)
    state = {"title": item.text, **payload.model_dump(), "status": "open"}
    task = await tasks.create(db, user, state, source="plan", source_id=item.id)
    await db.commit()
    tasks.log("task_created", user, task.id, source="plan")
    return await tasks.one(db, task.id)
