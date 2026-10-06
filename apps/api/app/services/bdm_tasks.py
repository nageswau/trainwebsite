"""bdm-008 (DEC-SCOPE-074, spec §5-§7): follow-up and task scope, buckets, counts, permissions and output.

Functions only; nothing here commits -- the route owns the transaction. Every `{task_id}` resolves through the caller's scope in SQL,
so another BDM's task is the same 404 as a missing one. Lock order: an outcome follow-up's appointment before the task (bdm-007's
order); an organization before its tasks. Logs and audit carry ids, kind, source, field names and counts -- never title, notes or
reason text.
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BDM_ORG_TYPES, AuditLog, BdmAppointment, BdmOrganization, BdmProfile, BdmTask, User
from app.services.bdm import bdm_context, person_ref
from app.services.bdm_activities import day_range

logger = logging.getLogger("app.bdm")

NOT_FOUND = "Task not found"
OWNER_ONLY = "Only the assigned BDM can change this task"
STATE_REFUSALS = {"done": "This task is already done", "cancelled": "This task was cancelled"}
FROM_REPORT = "Change this follow-up from its meeting report"
PAST_DUE = "Due date can't be in the past"
NOT_ASSIGNED = "Only the assigned BDM can add tasks for this organization"
ARCHIVED = "This organization is archived — restore it before adding tasks"
ARCHIVE_REASON = "Organization archived"  # the cancel reason on items an archive closed (F6)
DAILY_CAP = 200  # an abuse bound, far above real use (bdm-009 V10's pattern)
TABS = ("today", "overdue", "upcoming", "done", "cancelled")
ORG_JOIN = BdmOrganization.id == BdmTask.organization_id


async def caller_filters(db: AsyncSession, user: User) -> list:
    """Read scope: a BDM their own items; a manager their team's (sub-select, so a row lock never touches bdm_profiles); super_admin
    all; any other role 403."""
    if user.role == "bdm":
        await bdm_context(db, user)
        return [BdmTask.assignee_user_id == user.id]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [BdmTask.assignee_user_id.in_(team)]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


def bucket_filter(bucket: str, today: date):
    is_open = BdmTask.status == "open"
    return {
        "today": and_(is_open, BdmTask.due_on == today),
        "overdue": and_(is_open, BdmTask.due_on < today),
        "upcoming": and_(is_open, BdmTask.due_on > today),
        "open": is_open,
        "done": BdmTask.status == "done",
        "cancelled": BdmTask.status == "cancelled",
    }[bucket]


def org_type_filter(org_type: str):
    """`none` = no organization. Every query here outer-joins the organization, so the type is read from the join."""
    return BdmTask.organization_id.is_(None) if org_type == "none" else BdmOrganization.org_type == org_type


def is_overdue(status: str, due_on: date, today: date) -> bool:
    return status == "open" and due_on < today


def permissions(user: User, task: BdmTask) -> dict[str, bool]:
    """F2/F3/F4: only the assigned BDM writes; outcome follow-ups are only completed here (their date lives on the appointment)."""
    can_complete = user.role == "bdm" and task.assignee_user_id == user.id and task.status == "open"
    can_change = can_complete and task.source == "manual"
    return {"can_edit": can_change, "can_complete": can_complete, "can_cancel": can_change}


def _ordering(bucket: str) -> tuple:
    if bucket == "done":
        return (BdmTask.completed_at.desc(), BdmTask.id)
    if bucket == "cancelled":
        return (BdmTask.cancelled_at.desc(), BdmTask.id)
    return (BdmTask.due_on, BdmTask.created_at, BdmTask.id)


def _rows():
    """One page query: organization (outer), assignee and source appointment code (outer) -- no N+1."""
    return (
        select(BdmTask, BdmOrganization, User, BdmAppointment.code)
        .select_from(BdmTask)
        .outerjoin(BdmOrganization, ORG_JOIN)
        .join(User, User.id == BdmTask.assignee_user_id)
        .outerjoin(BdmAppointment, BdmAppointment.id == BdmTask.source_appointment_id)
    )


def _count(*filters):
    return select(func.count()).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN).where(*filters)


def _out(user: User, task: BdmTask, org: BdmOrganization | None, assignee: User, appt_code: str | None, today: date) -> dict:
    return {
        "id": task.id, "kind": task.kind, "title": task.title, "notes": task.notes, "due_on": task.due_on, "status": task.status,
        "source": task.source, "overdue": is_overdue(task.status, task.due_on, today),
        "organization": None if org is None else {
            "id": org.id, "code": org.code, "name": org.name, "org_type": org.org_type, "archived": org.archived_at is not None,
        },
        "appointment": None if task.source_appointment_id is None else {"id": task.source_appointment_id, "code": appt_code},
        "assignee": person_ref(assignee),
        "completed_at": task.completed_at, "cancelled_at": task.cancelled_at, "cancel_reason": task.cancel_reason,
        "created_at": task.created_at, "updated_at": task.updated_at,
        "permissions": permissions(user, task),
    }


async def _bucket_counts(db: AsyncSession, filters: list, today: date) -> dict:
    row = (await db.execute(
        select(*(func.count().filter(bucket_filter(b, today)) for b in TABS)).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN).where(*filters)
    )).one()
    return dict(zip(TABS, (n or 0 for n in row), strict=True))


async def _type_counts(db: AsyncSession, filters: list) -> list[dict]:
    rows = (await db.execute(
        select(BdmOrganization.org_type, func.count()).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN)
        .where(*filters).group_by(BdmOrganization.org_type)
    )).all()
    found: dict[str | None, int] = {t: n for t, n in rows}
    return [{"org_type": t, "count": found[t]} for t in (*BDM_ORG_TYPES, None) if found.get(t)]


async def page(db: AsyncSession, user: User, base: list, bucket: str, org_type: str | None, today: date, limit: int, offset: int) -> dict:
    """AC4: the tab counts use every filter but the bucket; the type counts every filter but the type -- so they add up to the list."""
    in_bucket = bucket_filter(bucket, today)
    of_type = [org_type_filter(org_type)] if org_type else []
    filters = [*base, in_bucket, *of_type]
    total = await db.scalar(_count(*filters))
    rows = (await db.execute(_rows().where(*filters).order_by(*_ordering(bucket)).limit(limit).offset(offset))).tuples().all()
    return {
        "items": [_out(user, t, o, u, code, today) for t, o, u, code in rows],
        "total": total or 0, "limit": limit, "offset": offset, "today": today,
        "counts": {"buckets": await _bucket_counts(db, [*base, *of_type], today), "by_org_type": await _type_counts(db, [*base, in_bucket])},
    }


async def one(db: AsyncSession, user: User, task_id: UUID, today: date) -> dict:
    """The row as written (populate_existing: never a stale identity-map copy after a commit)."""
    task, org, assignee, code = (await db.execute(_rows().where(BdmTask.id == task_id).execution_options(populate_existing=True))).tuples().one()
    return _out(user, task, org, assignee, code, today)


async def load_for_write(db: AsyncSession, user: User, task_id: UUID, action: str) -> BdmTask:
    """§6.6 steps 1-3: scope (404); locks in the global order (an outcome follow-up's appointment first); then the owner (403)."""
    task = await db.scalar(select(BdmTask).where(BdmTask.id == task_id, *await caller_filters(db, user)))
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    if task.source_appointment_id is not None:
        await db.execute(select(BdmAppointment.id).where(BdmAppointment.id == task.source_appointment_id).with_for_update())
    locked = await db.scalar(select(BdmTask).where(BdmTask.id == task_id).with_for_update().execution_options(populate_existing=True))
    if locked is None:  # never in practice (tasks are not deleted); kept so the type is narrowed without an assert
        raise HTTPException(404, NOT_FOUND)
    if user.role != "bdm" or locked.assignee_user_id != user.id:
        logger.warning("bdm_task_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), "action": action}})
        raise HTTPException(403, OWNER_ONLY)
    return locked


def require_open(task: BdmTask) -> None:
    if task.status != "open":
        raise HTTPException(409, STATE_REFUSALS[task.status])


def require_manual(task: BdmTask) -> None:
    if task.source != "manual":
        raise HTTPException(409, FROM_REPORT)


async def check_daily_cap(db: AsyncSession, user_id: UUID, today: date) -> None:
    """Create only (bdm-009's check_daily_cap). A soft bound: two concurrent saves may pass it by one (bdm-009 V10's accepted race)."""
    start, end = day_range(today)
    count = await db.scalar(select(func.count()).select_from(BdmTask).where(
        BdmTask.assignee_user_id == user_id, BdmTask.source == "manual", BdmTask.created_at >= start, BdmTask.created_at < end))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, f"You've added {DAILY_CAP} tasks today")


async def cancel_open_for_organization(db: AsyncSession, org_id: UUID) -> int:
    """F6: the archive's transaction (the caller holds the organization lock) cancels every assignee's open items on it."""
    cancelled = await db.scalars(
        update(BdmTask).where(BdmTask.organization_id == org_id, BdmTask.status == "open")
        .values(status="cancelled", cancelled_at=func.now(), cancel_reason=ARCHIVE_REASON, updated_at=func.now())
        .returning(BdmTask.id)
        .execution_options(synchronize_session=False)
    )
    return len(cancelled.all())


def audit(db: AsyncSession, user: User, action: str, task_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, kind, source, field names only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_task.{action}", entity_type="bdm_task", entity_id=str(task_id), metadata_json=metadata or {}))


def log(event: str, user: User, task_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), **extra}})
