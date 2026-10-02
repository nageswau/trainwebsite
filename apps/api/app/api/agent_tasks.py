"""AGN-016 -- an agency's tasks and follow-ups on its students (DEC-SCOPE-053; spec §3-§5).

Reuses AGN-004's gate, lock order and scoped student load unchanged (api/agent_students.py is imported, not edited). Masters see
the agency's tasks; staff only those of students assigned to them (G4), so a reassigned student's tasks follow it (T1); anything
outside the caller's scope is 404. Every write locks the agency first, then its row, validates, writes its audit row in the same
transaction and commits once. Audit metadata and logs carry ids and field names only -- never a title or notes (student PII).
"""

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_shortlist import _commit
from app.api.agent_students import _gate, _locked_row
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrgMember, AgentStudent, AgentTask, AuditLog, User
from app.schemas import AgentTaskCreate, AgentTaskUpdate
from app.services.agent_applications import ARCHIVED
from app.services.agent_orgs import lock_active_org
from app.services.agent_shortlist import apply_changes  # AGN-007's "set only what differs, stamp the editor" -- one definition
from app.services.agent_tasks import CLOSED, check_application, close_task, ensure_capacity, list_page, load_scoped_task, new_task, task_detail

logger = logging.getLogger("app.agent_tasks")

router = APIRouter(prefix="/workflows/overseas/agent/crm/tasks", tags=["agent-tasks"])

CHANGED = "The task changed; reload and try again"


def _audit(db: AsyncSession, user: User, action: str, task: AgentTask, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001). The subject is the student (the shortlist precedent), so AGN-021's
    activity names it with no new resolver."""
    db.add(AuditLog(user_id=user.id, action=f"agent_student.{action}", entity_type="agent_student", entity_id=str(task.agent_student_id), metadata_json={"task_id": str(task.id), **(metadata or {})}))


def _log(event: str, membership: AgentOrgMember, user: User, student_id, task_id="-", *, level: int = logging.INFO, **extra) -> None:
    logger.log(level, event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "student_id": str(student_id), "task_id": str(task_id), **extra}})


def _refuse(status: int, detail: str, membership: AgentOrgMember, user: User, student_id, task_id="-") -> HTTPException:
    _log("agent_task_write_refused", membership, user, student_id, task_id, level=logging.WARNING, status=status, reason=detail)
    return HTTPException(status, detail)


TaskView = Literal["open", "overdue", "done", "cancelled", "all"]
MAX_OFFSET = 10_000  # AGN-021's bound: deep offsets are a scan, not a use case


@router.get("")
async def list_tasks(
    view: TaskView = "open",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, view=view, student=student, limit=limit, offset=offset, now=datetime.now(UTC))


@router.get("/{task_id}")
async def get_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"task": await task_detail(db, user, task_id, datetime.now(UTC))}


@router.post("", status_code=201)
async def create_task(payload: AgentTaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, payload.agent_student_id)  # agency lock, then the scoped student; 404 outside scope
    if student.status == "archived":
        raise _refuse(409, ARCHIVED, membership, user, student.id)
    await check_application(db, user, student, payload.application_id)
    await ensure_capacity(db, student.id)
    data = payload.model_dump(exclude={"agent_student_id"})
    task = new_task(db, user, student, data)
    _audit(db, user, "task_add", task, {"fields": sorted(k for k, v in data.items() if v is not None)})
    await _commit(db, CHANGED)
    _log("agent_task_created", membership, user, student.id, task.id)
    return {"task": await task_detail(db, user, task.id, datetime.now(UTC))}


@router.patch("/{task_id}")
async def update_task(task_id: UUID, payload: AgentTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Field edits, or `status` alone to close (T2, T6). The agency lock comes first (it also serialises with assign and archive), so
    the scoped load sees the current owner: a staff member reassigned away gets 404, and a second close waits, then gets 409."""
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    task = await load_scoped_task(db, user, task_id, lock=True)
    student = await db.get(AgentStudent, task.agent_student_id, populate_existing=True)  # in scope: the task's scope is its student's
    assert student is not None  # the task's foreign key (ON DELETE RESTRICT) guarantees the row
    if student.status == "archived":
        raise _refuse(409, ARCHIVED, membership, user, student.id, task.id)
    if task.status != "open":
        raise _refuse(409, CLOSED, membership, user, student.id, task.id)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        close_task(task, user, changes["status"])
        action, event = ("task_complete", "agent_task_completed") if task.status == "done" else ("task_cancel", "agent_task_cancelled")
        _audit(db, user, action, task)
        changed = ["status"]
    else:
        if changes.get("application_id") not in (None, task.application_id):
            await check_application(db, user, student, changes["application_id"])
        changed = apply_changes(task, changes, user)
        event = "agent_task_updated"
        if changed:
            _audit(db, user, "task_update", task, {"fields": changed})
    await _commit(db, CHANGED)
    if changed:
        _log(event, membership, user, student.id, task.id, fields=changed)
    return {"task": await task_detail(db, user, task.id, datetime.now(UTC))}
