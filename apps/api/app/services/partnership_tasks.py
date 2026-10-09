"""upc-020 (DEC-SCOPE-140, spec §3): partnership tasks and follow-ups -- scope, IST bands, the Q-22 auto-tasks, the university's Next /
Last Action and output.

Functions only; nothing here commits -- the route (or the stage / visit route whose event creates a task) owns the transaction. Every
partnership reader reads every task (TK8); only the assignee or the assignee's reporting head changes one (TK11). Auto-tasks are created
under the event's parent row lock (the university for a stage move, the visit for a completion), so the open-duplicate check cannot race
(TK7; `uq_partnership_tasks_open_rule` is the backstop). Logs and audit carry ids, kind, source, rule and field names -- never title,
notes or reason text.
"""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, PartnershipProfile, PartnershipTask, University, UniversityStageHistory, UniversityVisit, User
from app.partnership_stages import label_of
from app.partnership_task_rules import STAGE_RULES, VISIT_RULE, Rule
from app.services import bdm_activities
from app.services import university_visits as visits
from app.services.bdm_travel import india_today
from app.services.partnership import partnership_context
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Task not found"
READ_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # TK8
CREATE_ROLES = frozenset({"partnership_manager", "partnership_head"})  # TK9
ACTOR_REFUSAL = "Only the person this task is assigned to, or their partnership head, can change it"
STATE_REFUSALS = {"done": "This task is already done", "cancelled": "This task was cancelled"}
ASSIGNEE_INVALID = "Choose yourself or an active partnership manager from your team"
DAILY_CAP = 200  # manual tasks per creator per IST day: an abuse bound far above real use (bdm-008)
BANDS = ("overdue", "today", "tomorrow", "upcoming", "done", "cancelled")
PRIORITY_RANK = case({"high": 0, "medium": 1, "low": 2}, value=PartnershipTask.priority)


# --- access ---------------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES:
        raise HTTPException(403, "Partnership tasks access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def require_creator(db: AsyncSession, user: User) -> None:
    await require_reader(db, user)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Only partnership managers and heads add tasks")


def can_act(user: User, task: PartnershipTask, assignee_head_id: UUID | None) -> bool:
    """TK11: the assignee, or the head the assignee reports to."""
    return user.id == task.assignee_user_id or (user.role == "partnership_head" and user.id == assignee_head_id)


async def check_assignee(db: AsyncSession, user: User, assignee_id: UUID) -> None:
    """TK10: a manager assigns themselves; a head themselves or an active direct report (upc-010's lead rule)."""
    if not await db.scalar(select(User.id).where(User.id == assignee_id, *visits.lead_filter(user))):
        raise HTTPException(422, ASSIGNEE_INVALID)


def check_due(value: date) -> None:
    visits.check_future(value, "The due date")


async def check_daily_cap(db: AsyncSession, user: User) -> None:
    """A soft bound: two concurrent saves may pass it by one (bdm-008's accepted race)."""
    start, end = bdm_activities.day_range(india_today())
    count = await db.scalar(
        select(func.count())
        .select_from(PartnershipTask)
        .where(PartnershipTask.created_by_user_id == user.id, PartnershipTask.source == "manual", PartnershipTask.created_at >= start, PartnershipTask.created_at < end)
    )
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, f"You've added {DAILY_CAP} tasks today")


# --- bands (TK13, IST) ----------------------------------------------------------------------------------------------------------
def band_of(task: PartnershipTask, today: date) -> str:
    if task.status != "open":
        return task.status
    if task.due_on < today:
        return "overdue"
    if task.due_on == today:
        return "today"
    return "tomorrow" if task.due_on == today + timedelta(days=1) else "upcoming"


def band_filter(band: str, today: date):
    is_open = PartnershipTask.status == "open"
    tomorrow = today + timedelta(days=1)
    return {
        "overdue": and_(is_open, PartnershipTask.due_on < today),
        "today": and_(is_open, PartnershipTask.due_on == today),
        "tomorrow": and_(is_open, PartnershipTask.due_on == tomorrow),
        "upcoming": and_(is_open, PartnershipTask.due_on > tomorrow),
        "open": is_open,
        "done": PartnershipTask.status == "done",
        "cancelled": PartnershipTask.status == "cancelled",
    }[band]


async def assignee_filter(db: AsyncSession, user: User, assignee: str | None) -> list:
    """`me`, `team` (a head: themselves and their direct reports; anyone else: themselves) or one user id; unknown values are a 422."""
    if assignee is None:
        return []
    if assignee == "me" or (assignee == "team" and user.role != "partnership_head"):
        return [PartnershipTask.assignee_user_id == user.id]
    if assignee == "team":
        team = select(PartnershipProfile.user_id).where(PartnershipProfile.reporting_head_user_id == user.id)
        return [or_(PartnershipTask.assignee_user_id == user.id, PartnershipTask.assignee_user_id.in_(team))]
    try:
        return [PartnershipTask.assignee_user_id == UUID(assignee)]
    except ValueError:
        raise HTTPException(422, "assignee must be me, team or a user id") from None


# --- output ---------------------------------------------------------------------------------------------------------------------
_assignee, _creator = aliased(User), aliased(User)


def _rows():
    """One page query: university, assignee (+ their reporting head, for permissions) and creator -- no N+1."""
    return (
        select(PartnershipTask, University, _assignee, _creator, PartnershipProfile.reporting_head_user_id)
        .join(University, University.id == PartnershipTask.university_id)
        .join(_assignee, _assignee.id == PartnershipTask.assignee_user_id)
        .join(_creator, _creator.id == PartnershipTask.created_by_user_id)
        .outerjoin(PartnershipProfile, PartnershipProfile.user_id == PartnershipTask.assignee_user_id)
    )


def _out(user: User, task: PartnershipTask, uni: University, assignee: User, creator: User, head_id: UUID | None, today: date) -> dict:
    band = band_of(task, today)
    acts = task.status == "open" and can_act(user, task, head_id)
    return {
        "id": task.id,
        "university": {"id": uni.id, "university_code": uni.university_code, "name": uni.name},
        "kind": task.kind,
        "title": task.title,
        "notes": task.notes,
        "due_on": task.due_on,
        "priority": task.priority,
        "status": task.status,
        "band": band,
        "overdue": band == "overdue",
        "source": task.source,
        "assignee": person_ref(assignee),
        "created_by": person_ref(creator),
        "completed_at": task.completed_at,
        "cancelled_at": task.cancelled_at,
        "cancel_reason": task.cancel_reason,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "permissions": dict.fromkeys(("can_edit", "can_reschedule", "can_complete", "can_cancel"), acts),
    }


def _ordering(band: str) -> tuple:
    if band == "done":
        return (PartnershipTask.completed_at.desc(), PartnershipTask.id)
    if band == "cancelled":
        return (PartnershipTask.cancelled_at.desc(), PartnershipTask.id)
    return (PartnershipTask.due_on, PRIORITY_RANK, PartnershipTask.created_at, PartnershipTask.id)


async def page(db: AsyncSession, user: User, filters: list, band: str, limit: int, offset: int) -> dict:
    """The band counts use every filter but the band, so the tabs add up to the lists."""
    today = india_today()
    in_band = [*filters, band_filter(band, today)]
    total = await db.scalar(select(func.count()).select_from(PartnershipTask).where(*in_band))
    rows = (await db.execute(_rows().where(*in_band).order_by(*_ordering(band)).limit(limit).offset(offset))).all()
    counts = (await db.execute(select(*(func.count().filter(band_filter(b, today)) for b in BANDS)).select_from(PartnershipTask).where(*filters))).one()
    return {
        "items": [_out(user, task, uni, assignee, creator, head_id, today) for task, uni, assignee, creator, head_id in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "today": today,
        "counts": dict(zip(BANDS, (n or 0 for n in counts), strict=True)),
    }


async def one(db: AsyncSession, user: User, task_id: UUID) -> dict:
    """The row as written (populate_existing: never a stale identity-map copy after a commit)."""
    task, uni, assignee, creator, head_id = (await db.execute(_rows().where(PartnershipTask.id == task_id).execution_options(populate_existing=True))).one()
    return {"task": _out(user, task, uni, assignee, creator, head_id, india_today())}


async def load_for_write(db: AsyncSession, user: User, task_id: UUID, action: str) -> PartnershipTask:
    """Lock the task (404 when missing), then the actor (403, logged ids only), then the state (409)."""
    await require_reader(db, user)
    task = await db.scalar(select(PartnershipTask).where(PartnershipTask.id == task_id).with_for_update().execution_options(populate_existing=True))
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    head_id = await db.scalar(select(PartnershipProfile.reporting_head_user_id).where(PartnershipProfile.user_id == task.assignee_user_id))
    if not can_act(user, task, head_id):
        log("partnership_task_refused", user, task.id, action=action)
        raise HTTPException(403, ACTOR_REFUSAL)
    if task.status != "open":
        raise HTTPException(409, STATE_REFUSALS[task.status])
    return task


# --- auto-tasks (Q-22: TK4-TK7, TK16) ---------------------------------------------------------------------------------------------
async def _auto_assignee(db: AsyncSession, actor: User, uni: University) -> User | None:
    """TK6: the active primary manager, else the active backup, else a partnership actor; otherwise nobody (the rule is skipped)."""
    for user_id in (uni.primary_manager_user_id, uni.backup_manager_user_id):
        owner = await db.get(User, user_id) if user_id else None
        if owner is not None and owner.active:
            return owner
    return actor if actor.role in CREATE_ROLES else None


async def _auto_create(db: AsyncSession, actor: User, university_id: UUID, key: str, assignee: User | None, rule: Rule, due_on: date, source: str) -> None:
    """TK7: one open task per (university, rule key). A skipped rule is logged, never an error: the event itself must not fail."""
    if assignee is None:
        log("partnership_task_auto_skipped", actor, "-", university_id=str(university_id), rule=key, why="no_assignee")
        return
    open_already = await db.scalar(select(PartnershipTask.id).where(PartnershipTask.university_id == university_id, PartnershipTask.rule == key, PartnershipTask.status == "open"))
    if open_already is not None:
        log("partnership_task_auto_skipped", actor, open_already, university_id=str(university_id), rule=key, why="open_duplicate")
        return
    task = PartnershipTask(
        id=uuid4(), university_id=university_id, kind=rule.kind, title=rule.title, due_on=due_on, priority=rule.priority, source=source, rule=key,
        assignee_user_id=assignee.id, created_by_user_id=actor.id, status="open",
    )  # fmt: skip
    db.add(task)
    audit(db, actor, "auto_create", task.id, {"kind": rule.kind, "source": source, "university_id": str(university_id), "rule": key})
    log("partnership_task_auto_created", actor, task.id, university_id=str(university_id), rule=key)


async def on_stage_entered(db: AsyncSession, actor: User, uni: University) -> None:
    """Called by the stage move, on the university row it has locked."""
    rule = STAGE_RULES.get(uni.stage)
    if rule is None:
        return
    due = india_today() + timedelta(days=rule.days)
    await _auto_create(db, actor, uni.id, f"stage:{uni.stage}", await _auto_assignee(db, actor, uni), rule, due, "stage")


async def on_visit_completed(db: AsyncSession, actor: User, v: UniversityVisit) -> None:
    """upc-010 VS16: the completed visit's follow-up date becomes a follow-up for the visit's lead (on the visit row it has locked)."""
    if v.follow_up_date is None:
        return
    lead = await db.get(User, v.lead_user_id)
    assignee = lead if lead is not None and lead.active else None
    await _auto_create(db, actor, v.university_id, f"visit:{v.id}", assignee, VISIT_RULE, v.follow_up_date, "visit")


async def sync_visit_due(db: AsyncSession, v: UniversityVisit) -> None:
    """TK16: a changed visit follow-up date moves the visit's open follow-up (a done or cancelled one keeps its date)."""
    if v.follow_up_date is None:
        return
    await db.execute(
        update(PartnershipTask)
        .where(PartnershipTask.rule == f"visit:{v.id}", PartnershipTask.status == "open")
        .values(due_on=v.follow_up_date, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


# --- the university's Next / Last Action (TK14, TK15) -----------------------------------------------------------------------------
async def follow_up_out(db: AsyncSession, university_id: UUID) -> dict:
    today = india_today()
    nxt = (await db.execute(
        select(PartnershipTask, User).join(User, User.id == PartnershipTask.assignee_user_id)
        .where(PartnershipTask.university_id == university_id, PartnershipTask.status == "open", PartnershipTask.kind == "follow_up")
        .order_by(PartnershipTask.due_on, PRIORITY_RANK, PartnershipTask.created_at, PartnershipTask.id).limit(1)
    )).first()  # fmt: skip
    done = (await db.execute(
        select(PartnershipTask.title, PartnershipTask.completed_at)
        .where(PartnershipTask.university_id == university_id, PartnershipTask.status == "done")
        .order_by(PartnershipTask.completed_at.desc()).limit(1)
    )).first()  # fmt: skip
    moved = (await db.execute(
        select(UniversityStageHistory.to_stage, UniversityStageHistory.created_at)
        .where(UniversityStageHistory.university_id == university_id, UniversityStageHistory.kind == "move")
        .order_by(UniversityStageHistory.position.desc()).limit(1)
    )).first()  # fmt: skip
    actions: list[tuple[datetime, str]] = []  # (when, what)
    if done and done.completed_at:  # always set on a done task (ck_partnership_tasks_completed)
        actions.append((done.completed_at, done.title))
    if moved:
        actions.append((moved.created_at, f"Moved to {label_of(moved.to_stage)}"))
    next_action = None
    if nxt:
        task, assignee = nxt
        next_action = {"id": task.id, "title": task.title, "due_on": task.due_on, "priority": task.priority, "band": band_of(task, today), "assignee": person_ref(assignee)}
    last = max(actions) if actions else None
    return {"next_action": next_action, "last_action": {"title": last[1], "at": last[0]} if last else None}


def audit(db: AsyncSession, user: User, action: str, task_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, kind, source, rule and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"partnership_task.{action}", entity_type="partnership_task", entity_id=str(task_id), metadata_json=metadata or {}))


def log(event: str, user: User, task_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), **extra}})
