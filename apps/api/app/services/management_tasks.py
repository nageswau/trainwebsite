"""mgmt-028 (spec MT1-MT14): the management to-do and each staff member's "Management tasks", EVID-017 §28.

Partners and the super admin (M13 operational tier) assign tasks to any active staff user; the owner sees only their own tasks (MT9)
and moves the status on. Bands are IST calendar days (MT3). Every write adds a `management_audit` row (kind `mgmt.task`, field names
only) in the caller's transaction; the routes in `api/management_tasks.py` commit once. Logs carry ids and field names, never titles.
Spec: docs/superpowers/specs/2026-10-12-mgmt-028-management-tasks-design.md.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import ManagementTask, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services import management_audit
from app.services.bdm_travel import INDIA, india_today
from app.services.ledger import field_error
from app.services.management_discussions import person, staff_ids

logger = logging.getLogger("app.management")
BANDS = ("overdue", "today", "week", "later", "completed")
OPEN = ("open", "in_progress")
COMPLETED_DAYS = 7  # MT3: today and the six days before
MAX_AHEAD = timedelta(days=731)  # MT8: about two years
MY_TASKS_URL = "/account/management-tasks"
FIELDS = ("title", "owner_user_id", "priority", "deadline", "status")
PRIORITY_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}
PRIORITY_RANK = case({"high": 0, "medium": 1, "low": 2}, value=ManagementTask.priority)

NOT_FOUND = "Task not found"
CANCELLED = "This task was cancelled; it can't be updated"


def log(event: str, user: User, task_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), **extra}})


# --- bands (MT3, IST) ----------------------------------------------------------------------------------------------------------
def week_end(today: date) -> date:
    """The Sunday of today's Monday-Sunday week."""
    return today + timedelta(days=6 - today.weekday())


def _completed_since(today: date) -> datetime:
    return datetime.combine(today - timedelta(days=COMPLETED_DAYS - 1), time.min, INDIA)


def band_of(task, today: date) -> str | None:
    """The task's band; `None` for a task completed before the 7-day window."""
    if task.status == "cancelled":
        return "cancelled"
    if task.status == "completed":
        return "completed" if task.completed_at and task.completed_at >= _completed_since(today) else None
    if task.deadline < today:
        return "overdue"
    if task.deadline == today:
        return "today"
    return "week" if task.deadline <= week_end(today) else "later"


def band_filter(band: str, today: date):
    is_open = ManagementTask.status.in_(OPEN)
    return {
        "overdue": and_(is_open, ManagementTask.deadline < today),
        "today": and_(is_open, ManagementTask.deadline == today),
        "week": and_(is_open, ManagementTask.deadline > today, ManagementTask.deadline <= week_end(today)),
        "later": and_(is_open, ManagementTask.deadline > week_end(today)),
        "completed": and_(ManagementTask.status == "completed", ManagementTask.completed_at >= _completed_since(today)),
        "cancelled": ManagementTask.status == "cancelled",
    }[band]


def active_filter(today: date):
    """Every band but cancelled: what the §28 list shows."""
    return or_(ManagementTask.status.in_(OPEN), band_filter("completed", today))


# --- rules (MT6, MT8) ----------------------------------------------------------------------------------------------------------
async def check(db: AsyncSession, state: dict, before: dict | None = None) -> None:
    """The merged state of a create or change; only fields set or changed are checked, so an overdue task or one whose owner has
    since left stays editable."""

    def changed(field: str) -> bool:
        return before is None or state[field] != before[field]

    if changed("owner_user_id") and state["owner_user_id"] not in await staff_ids(db, [state["owner_user_id"]]):
        raise field_error("owner_user_id", "Choose an active staff member")
    today = india_today()
    if changed("deadline") and not today <= state["deadline"] <= today + MAX_AHEAD:
        raise field_error("deadline", "Choose a deadline from today up to two years ahead")


def set_status(task: ManagementTask, status: str) -> None:
    """MT2: completing stamps `completed_at`; reopening clears it."""
    if status == task.status:
        return
    task.status = status
    task.completed_at = datetime.now(UTC) if status == "completed" else None


def audit(db: AsyncSession, user: User, task: ManagementTask, changed: list[str], previous_status: str | None) -> None:
    """MT12: `complete` when the status became completed, `update` otherwise."""
    verb = "complete" if "status" in changed and task.status == "completed" and previous_status != "completed" else "update"
    management_audit.record(db, user, "mgmt.task", verb, str(task.id), fields=changed)


# --- notification (MT11) -------------------------------------------------------------------------------------------------------
def line(task: ManagementTask) -> str:
    return f"{task.title} — {task.deadline.strftime('%d %b %Y')} — {PRIORITY_LABELS[task.priority]} priority"


async def notify_after_write(db: AsyncSession, actor: User, task: ManagementTask, changed: list[str], previous_owner) -> None:
    if task.owner_user_id == actor.id or not changed:
        return
    if task.owner_user_id != previous_owner:
        title = "A management task was assigned to you"
    else:
        title = "A management task assigned to you changed"
    recipient = await db.get_one(User, task.owner_user_id)
    note = Notification(user_id=recipient.id, title=title, body=line(task), read=False, action_url=MY_TASKS_URL)
    db.add(note)
    await queue_deliveries(db, note, recipient)


# --- reads ---------------------------------------------------------------------------------------------------------------------
_owner, _creator = aliased(User), aliased(User)


def _rows():
    """One query: the task, its owner and its creator -- no N+1."""
    return select(ManagementTask, _owner, _creator).join(_owner, _owner.id == ManagementTask.owner_user_id).join(_creator, _creator.id == ManagementTask.created_by_user_id)


def _ordering() -> tuple:
    """MT4: open bands by deadline then priority; completed (listed last) newest first."""
    is_completed = ManagementTask.status == "completed"
    return (is_completed, case((is_completed, ManagementTask.completed_at)).desc().nulls_last(), ManagementTask.deadline, PRIORITY_RANK, ManagementTask.created_at, ManagementTask.id)


def out(task: ManagementTask, owner: User, creator: User, today: date) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "owner": person(owner),
        "owner_active": owner.active,
        "priority": task.priority,
        "deadline": task.deadline,
        "status": task.status,
        "band": band_of(task, today),
        "source": task.source,
        "completed_at": task.completed_at,
        "created_by": person(creator),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def my_out(task: ManagementTask, today: date) -> dict:
    """MT9: only these keys ever leave for the owner."""
    return {"id": task.id, "title": task.title, "priority": task.priority, "deadline": task.deadline, "status": task.status, "band": band_of(task, today), "updated_at": task.updated_at}


async def counts(db: AsyncSession, where: list, today: date) -> dict:
    row = (await db.execute(select(*(func.count().filter(band_filter(b, today)) for b in BANDS)).select_from(ManagementTask).where(*where))).one()
    return dict(zip(BANDS, (n or 0 for n in row), strict=True))


async def page(db: AsyncSession, *, where: list, band: str | None, limit: int, offset: int) -> dict:
    """The band counts use every filter but the band, so they add up to the §28 list."""
    today = india_today()
    selected = [*where, band_filter(band, today) if band else active_filter(today)]
    total = await db.scalar(select(func.count()).select_from(ManagementTask).where(*selected))
    rows = (await db.execute(_rows().where(*selected).order_by(*_ordering()).limit(limit).offset(offset))).all()
    return {
        "items": [out(task, owner, creator, today) for task, owner, creator in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "today": today,
        "counts": await counts(db, where, today),
    }


async def one(db: AsyncSession, task_id) -> dict:
    """The row as written (populate_existing: never a stale identity-map copy after a commit)."""
    found = (await db.execute(_rows().where(ManagementTask.id == task_id).execution_options(populate_existing=True))).first()
    if found is None:
        raise HTTPException(404, NOT_FOUND)
    task, owner, creator = found
    return out(task, owner, creator, india_today())


async def mine(db: AsyncSession, user: User, limit: int = 200) -> dict:
    today = india_today()
    where = [ManagementTask.owner_user_id == user.id]
    rows = (await db.scalars(select(ManagementTask).where(*where, active_filter(today)).order_by(*_ordering()).limit(limit))).all()
    return {"items": [my_out(task, today) for task in rows], "today": today, "counts": await counts(db, where, today)}


# --- writes --------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, state: dict, *, source: str = "manual", source_id=None) -> ManagementTask:
    """A checked new task, audited and its owner notified, in the caller's transaction (the caller commits). mgmt-026 passes
    `source="plan"` and the plan item's id (MT5); the client never sets either."""
    await check(db, state)
    status = state.pop("status")
    task = ManagementTask(**state, status="open", source=source, source_id=source_id, created_by_user_id=user.id, updated_by_user_id=user.id)
    set_status(task, status)  # a task recorded as already completed gets its completed_at
    db.add(task)
    await db.flush()
    management_audit.record(db, user, "mgmt.task", "create", str(task.id), fields=list(FIELDS))
    await notify_after_write(db, user, task, list(FIELDS), None)
    return task


async def load(db: AsyncSession, task_id, *, owner: User | None = None) -> ManagementTask:
    """The task locked for a write; with `owner`, only that user's own task (MT9/MT13) -- another user's id is a 404, checked
    after the lock so a reassignment racing the owner's change wins."""
    stmt = select(ManagementTask).where(ManagementTask.id == task_id)
    if owner is not None:
        stmt = stmt.where(ManagementTask.owner_user_id == owner.id)
    task = await db.scalar(stmt.with_for_update().execution_options(populate_existing=True))
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    return task
