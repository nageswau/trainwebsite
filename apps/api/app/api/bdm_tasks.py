"""bdm-008 (DEC-SCOPE-074, spec §6): BDM follow-ups and tasks.

Every `{task_id}` resolves through `services.bdm_tasks` scope (out of scope = 404); every write is one transaction -- scope, locks
(appointment or organization before the task), owner, state, validation, change, audit, one commit here, log. Lists carry the
counts the tabs and type chips show, computed from the same filters."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmTask, User
from app.schemas import BdmAppointmentReason, BdmTaskBucket, BdmTaskCreate, BdmTaskKind, BdmTaskOrgType, BdmTaskOut, BdmTaskPage, BdmTaskUpdate
from app.services import bdm_organizations as org_svc
from app.services import bdm_tasks as svc
from app.services.bdm import bdm_context
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/bdm/tasks", tags=["bdm-tasks"])


@router.get("", response_model=BdmTaskPage)
async def list_tasks(
    bucket: BdmTaskBucket = "today",
    kind: BdmTaskKind | None = None,
    org_type: BdmTaskOrgType | None = None,
    organization_id: UUID | None = None,
    bdm_user_id: UUID | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they only narrow it (bdm-006 R-A10)."""
    base = await svc.caller_filters(db, user)
    if bdm_user_id is not None:
        if user.role == "bdm":
            raise HTTPException(422, "bdm_user_id is only for managers")
        base.append(BdmTask.assignee_user_id == bdm_user_id)
    if kind:
        base.append(BdmTask.kind == kind)
    if organization_id:
        base.append(BdmTask.organization_id == organization_id)
    return await svc.page(db, user, base, bucket, org_type, today_ist(await db_now(db)), limit, offset)


@router.post("", status_code=201, response_model=BdmTaskOut)
async def create_task(payload: BdmTaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§6.2, in this order so each refusal is exactly one rule. Not idempotent (a retry adds a second task; the cap bounds abuse)."""
    await bdm_context(db, user)
    if payload.organization_id is not None:
        org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type scope -> 404; serializes with archive
        if org.assigned_bdm_user_id != user.id:
            raise HTTPException(403, svc.NOT_ASSIGNED)
        if org.archived_at is not None:
            raise HTTPException(422, svc.ARCHIVED)
    today = today_ist(await db_now(db))
    if payload.due_on < today:
        raise HTTPException(422, svc.PAST_DUE)
    if await svc.created_today(db, user.id, today) >= svc.DAILY_CAP:
        raise HTTPException(409, f"You've added {svc.DAILY_CAP} tasks today")
    task = BdmTask(
        kind=payload.kind, title=payload.title, notes=payload.notes, due_on=payload.due_on, organization_id=payload.organization_id,
        source="manual", assignee_user_id=user.id, status="open",
    )
    db.add(task)
    await db.flush()
    svc.audit(db, user, "create", task.id, {"kind": task.kind, "organization": task.organization_id is not None})
    await db.commit()
    svc.log("bdm_task_created", user, task.id, kind=task.kind)
    return await svc.one(db, user, task.id, today)


@router.patch("/{task_id}", response_model=BdmTaskOut)
async def update_task(task_id: UUID, payload: BdmTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§6.3. Values equal to the stored ones are not changes (no audit, no updated_at bump); only a changed due date must be today or later."""
    task = await svc.load_for_write(db, user, task_id, "update")
    svc.require_open(task)
    svc.require_manual(task)
    today = today_ist(await db_now(db))
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(task, k) != v)
    if "due_on" in changed and changes["due_on"] < today:
        raise HTTPException(422, svc.PAST_DUE)
    for key in changed:
        setattr(task, key, changes[key])
    if changed:
        svc.audit(db, user, "update", task.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("bdm_task_updated", user, task.id, fields=changed)
    return await svc.one(db, user, task.id, today)


@router.post("/{task_id}/complete", response_model=BdmTaskOut)
async def complete_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Any open item of the assignee, outcome follow-ups included (F2). A second complete meets `done` under the lock -> 409."""
    task = await svc.load_for_write(db, user, task_id, "complete")
    svc.require_open(task)
    now = await db_now(db)
    task.status, task.completed_at = "done", now
    svc.audit(db, user, "complete", task.id, {"source": task.source})
    await db.commit()
    svc.log("bdm_task_completed", user, task.id, source=task.source)
    return await svc.one(db, user, task.id, today_ist(now))


@router.post("/{task_id}/cancel", response_model=BdmTaskOut)
async def cancel_task(task_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Manual items only (F3); the reason is kept and never logged."""
    task = await svc.load_for_write(db, user, task_id, "cancel")
    svc.require_open(task)
    svc.require_manual(task)
    now = await db_now(db)
    task.status, task.cancelled_at, task.cancel_reason = "cancelled", now, payload.reason
    svc.audit(db, user, "cancel", task.id)
    await db.commit()
    svc.log("bdm_task_cancelled", user, task.id)
    return await svc.one(db, user, task.id, today_ist(now))
