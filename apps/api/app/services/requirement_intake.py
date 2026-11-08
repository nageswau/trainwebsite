"""pob-027 (DEC-SCOPE-434 I1-I6): intake automation -- a new requirement's owner and notice (AC1), the task template and the tasks a
requirement's first owner starts with (AC2), and the Team Lead's settings.

Every hook runs in its caller's transaction: the owner, the notices and the tasks commit with the requirement or not at all. The tasks are
copied under the job row (a new row, or the assign route's `FOR UPDATE`), so they are copied once. Imported by `recruiter_requirements`:
it must not import that module or anything that reaches the telecaller import cycle. Logs and audit carry ids, kinds and counts only."""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Company, Job, RequirementAutomationSetting, RequirementTask, User
from app.notifications.events import notify
from app.services import requirement_owners as owners
from app.services.recruiter import MANAGER_ROLE, ROLE

logger = logging.getLogger("app.recruiter")

UNOWNED = "it.requirement.unowned"
EDITORS = frozenset({MANAGER_ROLE, "super_admin"})  # pob-001: the Team Lead is the placement manager
NOT_ALLOWED = "Only a Team Lead can change intake automation"
DEFAULT_TEMPLATE = [
    {"kind": "sourcing", "title": "Prepare the sourcing plan", "due_in_hours": 24},
    {"kind": "screening", "title": "Screen the first shortlisted profiles", "due_in_hours": 72},
]
QUEUE_URL = "/recruiter/requirements?assigned=unassigned"


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, NOT_ALLOWED)


async def team_leads(db: AsyncSession) -> list[User]:
    return list((await db.scalars(select(User).where(User.role == MANAGER_ROLE, User.active))).all())


# --- I1/I2: the owner and the notices ------------------------------------------------------------------------------------------------
async def _eligible(db: AsyncSession, user_id: UUID | None) -> UUID | None:
    """An active recruiter (`placement_team`), else nobody."""
    user = await db.get(User, user_id) if user_id else None
    return user.id if user is not None and user.active and user.role == ROLE else None


async def settle_owner(db: AsyncSession, job: Job) -> None:
    """Before the primary's history row: a requirement without an owner takes the company's recruiter; an ineligible owner is dropped
    (the requirement then waits in the Team Lead queue)."""
    owner = job.assigned_recruiter_user_id
    if owner is None:
        owner = await db.scalar(select(Company.assigned_recruiter_user_id).where(Company.id == job.company_id))
    job.assigned_recruiter_user_id = await _eligible(db, owner)


async def after_created(db: AsyncSession, actor: User | None, job: Job, now: datetime) -> None:
    """AC1: the owner is told (not when they created it), and starts with the template's tasks; with no owner, every Team Lead is told."""
    if job.assigned_recruiter_user_id is None:
        await notify(db, await team_leads(db), UNOWNED, job.id, action_url=QUEUE_URL)
        log("requirement_intake_unowned", job.id)
        return
    await owners.notify_assigned(db, actor, job, job.assigned_recruiter_user_id)
    await _copy_template(db, job, now)


async def after_assigned(db: AsyncSession, actor: User, job: Job, now: datetime) -> None:
    """The assign route (job row locked): the new primary is told; their open tasks move to them, or the template is copied when the
    requirement has none yet (AC2: once)."""
    owner_id = job.assigned_recruiter_user_id
    await owners.notify_assigned(db, actor, job, owner_id)
    has_tasks = await db.scalar(select(func.count()).select_from(RequirementTask).where(RequirementTask.job_id == job.id))
    if has_tasks:
        await db.execute(update(RequirementTask).where(RequirementTask.job_id == job.id, RequirementTask.status == "open").values(assignee_user_id=owner_id))
    else:
        await _copy_template(db, job, now)


async def _copy_template(db: AsyncSession, job: Job, now: datetime) -> None:
    items = (await settings(db)).task_template
    for item in items:
        db.add(RequirementTask(job_id=job.id, kind=item["kind"], title=item["title"], due_at=now + timedelta(hours=item["due_in_hours"]),
                               assignee_user_id=job.assigned_recruiter_user_id))  # fmt: skip
    if items:
        log("requirement_intake_tasks", job.id, count=len(items))


# --- I3: the settings ----------------------------------------------------------------------------------------------------------------
async def settings(db: AsyncSession, *, lock: bool = False) -> RequirementAutomationSetting:
    """The one row; the default template (not added) when the row is missing."""
    row = await db.get(RequirementAutomationSetting, 1, with_for_update=lock, populate_existing=True)
    return row if row is not None else RequirementAutomationSetting(id=1, task_template=DEFAULT_TEMPLATE)


async def save_settings(db: AsyncSession, user: User, template: list[dict]) -> RequirementAutomationSetting:
    """The Team Lead (403 otherwise); the row locked, created when missing, audited with the item counts (never a title)."""
    require_editor(user)
    row = await db.get(RequirementAutomationSetting, 1, with_for_update=True, populate_existing=True)
    if row is None:
        row = RequirementAutomationSetting(id=1, task_template=DEFAULT_TEMPLATE)
        db.add(row)
    if row.task_template != template:
        db.add(AuditLog(user_id=user.id, action="requirement_automation.settings", entity_type="requirement_automation_settings", entity_id="1",
                        metadata_json={"tasks": [len(row.task_template), len(template)]}))  # fmt: skip
    row.task_template = template
    row.updated_by_user_id = user.id
    return row


# --- I6: the tasks -----------------------------------------------------------------------------------------------------------------------
def can_complete(user: User, task: RequirementTask, can_edit: bool) -> bool:
    return task.status == "open" and (user.id == task.assignee_user_id or can_edit)


def task_out(user: User, task: RequirementTask, assignee: User | None, can_edit: bool) -> dict:
    return {
        "id": task.id, "kind": task.kind, "title": task.title, "due_at": task.due_at, "status": task.status, "completed_at": task.completed_at,
        "assignee": {"id": assignee.id, "full_name": assignee.full_name} if assignee else None, "can_complete": can_complete(user, task, can_edit),
    }  # fmt: skip


async def tasks_out(db: AsyncSession, user: User, job: Job, can_edit: bool) -> list[dict]:
    rows = (await db.execute(
        select(RequirementTask, User).join(User, User.id == RequirementTask.assignee_user_id)
        .where(RequirementTask.job_id == job.id).order_by(RequirementTask.due_at, RequirementTask.id)
    )).all()  # fmt: skip
    return [task_out(user, task, assignee, can_edit) for task, assignee in rows]


async def complete(db: AsyncSession, user: User, job: Job, task_id: UUID, can_edit: bool, now: datetime) -> RequirementTask:
    """The requirement's task (404 otherwise, also another requirement's), locked; the assignee or a writer (403); open only (409)."""
    task = await db.scalar(select(RequirementTask).where(RequirementTask.id == task_id, RequirementTask.job_id == job.id).with_for_update())
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.status != "open":
        raise HTTPException(409, "This task is already closed")
    if not can_complete(user, task, can_edit):
        raise HTTPException(403, "Only the assignee or a recruiter on this requirement can complete it")
    task.status, task.completed_at, task.completed_by_user_id = "done", now, user.id
    db.add(AuditLog(user_id=user.id, action="requirement_task.complete", entity_type="requirement_task", entity_id=str(task.id),
                    metadata_json={"job_id": str(job.id), "kind": task.kind}))  # fmt: skip
    return task


def log(event: str, job_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"job_id": str(job_id), **extra}})
