"""AGN-016 -- an agency's tasks and follow-ups on its students (DEC-SCOPE-051; spec §3-§5).

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
from app.models import AgentOrgMember, AgentTask, AuditLog, User
from app.schemas import AgentTaskCreate
from app.services.agent_applications import ARCHIVED
from app.services.agent_tasks import check_application, ensure_capacity, list_page, new_task, task_detail

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
