"""AGN-016 / DEC-SCOPE-051 -- an agency's tasks and follow-ups on its students.

Functions only (the services/agent_students.py shape): nothing here commits -- the router locks, writes, audits and commits.
A task has no assignee: it belongs to its student, so its scope is the student's (AGN-004 `student_scope`) and a reassigned
student's tasks follow it with no write to the task (T1).
Spec: docs/superpowers/specs/2026-10-02-agn-016-tasks-followups-design.md.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AgentOrgMember, AgentStudent, AgentTask, OverseasApplication, University, User
from app.services.agent_applications import WITHDRAWN
from app.services.agent_students import application_scope, student_scope

OPEN_TASK_CAP = 100  # T7: per student, checked under the agency lock
NOT_FOUND = "Task not found"
CLOSED = "This task is closed"
CAP_REACHED = f"This student already has {OPEN_TASK_CAP} open tasks. Complete or cancel some first."
APPLICATION_REFUSED = "Choose an application of this student"


def task_scope(user: User) -> list[ColumnElement]:
    """The tasks the caller may see: those of the students they may see (Masters: the agency's; staff: assigned to them)."""
    return [AgentTask.agent_student_id.in_(select(AgentStudent.id).where(*student_scope(user)))]


async def load_scoped_task(db: AsyncSession, user: User, task_id, *, lock: bool = False) -> AgentTask:
    """The caller's task or 404 -- the scope is in the WHERE clause, never checked after loading."""
    stmt = select(AgentTask).where(AgentTask.id == task_id, *task_scope(user)).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update(of=AgentTask) if lock else stmt)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row


# --- reads --------------------------------------------------------------------------------------------------------------------------

Account = aliased(User)
Assignee = aliased(User)
Creator = aliased(User)
Closer = aliased(User)
STUDENT_NAME = func.coalesce(Account.full_name, AgentStudent.full_name)  # a linked student's name is their account's


def _rows_stmt() -> Select:
    return (
        select(AgentTask, AgentStudent.status, STUDENT_NAME, AgentOrgMember.code, AgentOrgMember.status, Assignee.full_name, University.name, Creator.full_name, Closer.full_name)
        .join(AgentStudent, AgentStudent.id == AgentTask.agent_student_id)
        .outerjoin(Account, Account.id == AgentStudent.student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.id == AgentStudent.assigned_member_id)
        .outerjoin(Assignee, Assignee.id == AgentOrgMember.user_id)
        .outerjoin(OverseasApplication, OverseasApplication.id == AgentTask.application_id)
        .outerjoin(University, University.id == OverseasApplication.university_id)
        .outerjoin(Creator, Creator.id == AgentTask.created_by_user_id)
        .outerjoin(Closer, Closer.id == AgentTask.closed_by_user_id)
    )


def item(row, now: datetime) -> dict:
    """An explicit allowlist: people are named, never identified by user id; `overdue` uses the request's single `now` (T3)."""
    task, student_status, student_name, code, member_status, assignee, university, created_by, closed_by = row
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_at": task.due_at,
        "status": task.status,
        "overdue": task.status == "open" and task.due_at < now,
        "student": {"id": task.agent_student_id, "full_name": student_name, "status": student_status},
        "application": {"id": task.application_id, "university": university} if task.application_id else None,
        "assigned_to": {"code": code, "full_name": assignee, "status": member_status} if code else None,
        "created_by": created_by,
        "closed_by": closed_by,
        "closed_at": task.closed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


async def task_detail(db: AsyncSession, user: User, task_id, now: datetime) -> dict:
    row = (await db.execute(_rows_stmt().where(AgentTask.id == task_id, *task_scope(user)).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return item(row, now)


CLOSED_FIRST_NEWEST = (AgentTask.closed_at.desc(), AgentTask.id)


def _view(view: str, now: datetime) -> tuple[list[ColumnElement], tuple]:
    """T3/T4: (filters, order) per view. Open and overdue leave archived students' tasks out unless a student is named."""
    is_open = AgentTask.status == "open"
    return {
        "open": ([is_open], (AgentTask.due_at, AgentTask.id)),
        "overdue": ([is_open, AgentTask.due_at < now], (AgentTask.due_at, AgentTask.id)),
        "done": ([AgentTask.status == "done"], CLOSED_FIRST_NEWEST),
        "cancelled": ([AgentTask.status == "cancelled"], CLOSED_FIRST_NEWEST),
        "all": ([], (AgentTask.status != "open", case((is_open, AgentTask.due_at)), *CLOSED_FIRST_NEWEST)),
    }[view]


async def list_page(db: AsyncSession, user: User, *, view: str, student, limit: int, offset: int, now: datetime) -> dict:
    filters, order = _view(view, now)
    filters = [*task_scope(user), *filters]
    if student is not None:
        filters.append(AgentTask.agent_student_id == student)  # inside scope only: an out-of-scope id is an empty page
    elif view in ("open", "overdue"):
        filters.append(AgentStudent.status == "active")
    base = _rows_stmt().where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [item(r, now) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


# --- write checks (no commit) -------------------------------------------------------------------------------------------------------


async def check_application(db: AsyncSession, user: User, student: AgentStudent, application_id) -> None:
    """T4: the caller's application of this same student (AGN-008's owner rule: its own link, or a pre-AGN-008 row of the student's
    login), not School-bridged and not withdrawn. Anything else -- another student's, another agency's, unknown -- is one 422."""
    if application_id is None:
        return
    owner = OverseasApplication.agent_student_id == student.id
    if student.student_id is not None:
        owner = or_(owner, and_(OverseasApplication.agent_student_id.is_(None), OverseasApplication.student_id == student.student_id))
    found = await db.scalar(
        select(OverseasApplication.id).where(
            OverseasApplication.id == application_id, owner, OverseasApplication.school_student_id.is_(None), OverseasApplication.status != WITHDRAWN, *application_scope(user)
        )
    )
    if found is None:
        raise HTTPException(422, APPLICATION_REFUSED)


async def ensure_capacity(db: AsyncSession, student_id) -> None:
    """T7: runs under the agency lock, so two creates cannot both pass the count."""
    count = await db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.agent_student_id == student_id, AgentTask.status == "open"))
    if count >= OPEN_TASK_CAP:
        raise HTTPException(409, CAP_REACHED)


def apply_changes(task: AgentTask, user: User, changes: dict) -> list[str]:
    """Returns the sorted names of the fields whose value actually changed (a no-op PATCH audits nothing)."""
    changed = sorted(field for field, value in changes.items() if getattr(task, field) != value)
    for field in changed:
        setattr(task, field, changes[field])
    if changed:
        task.updated_by_user_id = user.id
    return changed


def close_task(task: AgentTask, user: User, status: str) -> None:
    """T2/T6: `done` or `cancelled`, final; who and when are the server's."""
    task.status, task.closed_at, task.closed_by_user_id, task.updated_by_user_id = status, datetime.now(UTC), user.id, user.id


def new_task(db: AsyncSession, user: User, student: AgentStudent, data: dict) -> AgentTask:
    """The id is set here (not at flush) so the audit row can name it before the single commit."""
    task = AgentTask(id=uuid4(), agent_student_id=student.id, status="open", created_by_user_id=user.id, updated_by_user_id=user.id, **data)
    db.add(task)
    return task
