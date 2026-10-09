"""upc-020 (DEC-SCOPE-139, spec §3): partnership follow-ups and tasks.

Every partnership reader reads every task (TK8). Every write is one transaction: the task row lock, the actor (the assignee or their
head: 403 logged), the state (409), validation (422), the change + audit row, one commit here, then the structured log."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import PartnershipTask, University, User
from app.partnership_task_rules import TITLES
from app.schemas import (
    PartnershipTaskBand,
    PartnershipTaskCancel,
    PartnershipTaskCatalogue,
    PartnershipTaskEnvelope,
    PartnershipTaskIn,
    PartnershipTaskKind,
    PartnershipTaskPage,
    PartnershipTaskReschedule,
    PartnershipTaskUpdate,
)
from app.services import partnership_tasks as svc
from app.services import partnership_universities as unis
from app.services import university_visits as visits

router = APIRouter(prefix="/partnership/tasks", tags=["partnership-tasks"])


@router.get("", response_model=PartnershipTaskPage)
async def list_tasks(
    band: PartnershipTaskBand = "today",
    assignee: str | None = Query(None, max_length=36),
    university_id: UUID | None = None,
    kind: PartnershipTaskKind | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """TK13: one band (or every open item), counts per band over the other filters."""
    await svc.require_reader(db, user)
    filters = await svc.assignee_filter(db, user, assignee)
    if university_id is not None:
        filters.append(PartnershipTask.university_id == university_id)
    if kind is not None:
        filters.append(PartnershipTask.kind == kind)
    return await svc.page(db, user, filters, band, limit, offset)


@router.get("/catalogue", response_model=PartnershipTaskCatalogue)
async def catalogue(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TK3: §19's twelve titles, offered as suggestions by the form."""
    await svc.require_reader(db, user)
    return {"titles": list(TITLES)}


@router.post("", status_code=201, response_model=PartnershipTaskEnvelope)
async def create_task(payload: PartnershipTaskIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TK9/TK10, in this order so each refusal is one rule. Not idempotent (a retry adds a second task; the daily bound limits abuse)."""
    await svc.require_creator(db, user)
    uni = await db.get(University, payload.university_id)
    if uni is None:
        raise HTTPException(422, "Choose a university")
    unis.require(user, uni, await unis.team_of(db, user), "can_edit_contacts", "task_create")  # edit scope 403, inactive 409
    assignee_id = payload.assignee_user_id or user.id
    await svc.check_assignee(db, user, assignee_id)
    svc.check_due(payload.due_on)
    await svc.check_daily_cap(db, user)
    task = PartnershipTask(
        university_id=uni.id, kind=payload.kind, title=payload.title, notes=payload.notes, due_on=payload.due_on, priority=payload.priority,
        assignee_user_id=assignee_id, created_by_user_id=user.id, source="manual", status="open",
    )  # fmt: skip
    db.add(task)
    await db.flush()
    svc.audit(db, user, "create", task.id, {"kind": task.kind, "source": "manual", "university_id": str(uni.id)})
    await db.commit()
    svc.log("partnership_task_created", user, task.id, university_id=str(uni.id), kind=task.kind)
    return await svc.one(db, user, task.id)


@router.patch("/{task_id}", response_model=PartnershipTaskEnvelope)
async def update_task(task_id: UUID, payload: PartnershipTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TK12: values equal to the stored ones are not changes (no audit). A new assignee follows TK10 for the caller."""
    task = await svc.load_for_write(db, user, task_id, "update")
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(task, k) != v)
    if "assignee_user_id" in changed:
        await svc.check_assignee(db, user, changes["assignee_user_id"])
    for key in changed:
        setattr(task, key, changes[key])
    if changed:
        svc.audit(db, user, "update", task.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("partnership_task_updated", user, task.id, fields=changed)
    return await svc.one(db, user, task.id)


@router.post("/{task_id}/reschedule", response_model=PartnershipTaskEnvelope)
async def reschedule(task_id: UUID, payload: PartnershipTaskReschedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    task = await svc.load_for_write(db, user, task_id, "reschedule")
    svc.check_due(payload.due_on)
    if payload.due_on != task.due_on:
        task.due_on = payload.due_on
        svc.audit(db, user, "reschedule", task.id)
    await db.commit()
    svc.log("partnership_task_rescheduled", user, task.id)
    return await svc.one(db, user, task.id)


@router.post("/{task_id}/complete", response_model=PartnershipTaskEnvelope)
async def complete(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A second complete meets `done` under the lock → 409."""
    task = await svc.load_for_write(db, user, task_id, "complete")
    task.status, task.completed_at = "done", visits.now()
    svc.audit(db, user, "complete", task.id, {"source": task.source})
    await db.commit()
    svc.log("partnership_task_completed", user, task.id, source=task.source)
    return await svc.one(db, user, task.id)


@router.post("/{task_id}/cancel", response_model=PartnershipTaskEnvelope)
async def cancel(task_id: UUID, payload: PartnershipTaskCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The reason is kept on the task and never logged."""
    task = await svc.load_for_write(db, user, task_id, "cancel")
    task.status, task.cancelled_at, task.cancel_reason = "cancelled", visits.now(), payload.reason
    svc.audit(db, user, "cancel", task.id, {"source": task.source})
    await db.commit()
    svc.log("partnership_task_cancelled", user, task.id, source=task.source)
    return await svc.one(db, user, task.id)
