"""ccrm-029 (DEC-SCOPE-250, T1-T8): counselor tasks -- the overseas counselor's to-do and the Overseas Admin's team-wide view (CC3).

A counselor sees and creates only their own tasks; they move the status of any of them and edit the rest only on tasks they created
(T3). The Overseas Admin (and Super Admin) creates for any active overseas counselor and changes anything, reassigning included. A link
is checked against the assignee's scope when set or changed (T4). Bands are IST days (T6). Every write adds an `AuditLog` row with field
names only in the caller's transaction; `api/counselor_tasks.py` commits once. Logs carry ids and field names, never titles.
Spec: docs/superpowers/specs/2026-10-24-ccrm-029-counselor-tasks-design.md."""

import logging
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lead_stages import CLOSED
from app.models import AuditLog, CounselorTask, Enquiry, Notification, OverseasApplication, University, User
from app.notifications.dispatch import queue_deliveries
from app.services.bdm_travel import INDIA, india_today
from app.services.counselor_students import is_visible_student, visible_student_ids
from app.services.lead_appointments import active_counselors
from app.services.ledger import field_error

logger = logging.getLogger("app.counselor_tasks")

ADMINS = ("overseas_admin", "super_admin")
BANDS = ("overdue", "today", "upcoming", "done")
DONE_DAYS = 7  # T6: today and the six days before
MAX_AHEAD = timedelta(days=731)  # about two years, as mgmt-028
OPTIONS_LIMIT = 200
TASKS_URL = "/overseas/counselor/tasks"
FIELDS = ("title", "due_on", "priority", "status", "counselor_user_id", "link")
LINK_COLUMNS = {"lead": "lead_id", "student": "student_user_id", "application": "application_id"}
PRIORITY_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}
PRIORITY_RANK = case({"high": 0, "medium": 1, "low": 2}, value=CounselorTask.priority)
STATUS_VERBS = {"done": "complete", "open": "reopen", "cancelled": "cancel"}

FORBIDDEN = "Only an overseas counselor or the Overseas Admin can use counselor tasks"
NOT_FOUND = "Task not found"
OWN_ONLY = "You can add tasks for yourself only"
STATUS_ONLY = "You can change only the status of a task someone else gave you"
CANCELLED = "This task was cancelled; it can't be changed"
CHOOSE_COUNSELOR = "Choose an active overseas counselor"
DUE_WINDOW = "Choose a due date from today up to two years ahead"
LINK_OUT_OF_SCOPE = "Choose a lead, student or application of this counselor"


def log(event: str, user: User, task_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), **extra}})


# --- access (T3) ---------------------------------------------------------------------------------------------------------------
def require_access(user: User) -> None:
    if user.role in ADMINS or (user.role == "counselor" and user.division == "overseas"):
        return
    raise HTTPException(403, FORBIDDEN)


def is_admin(user: User) -> bool:
    return user.role in ADMINS


def can_edit(user: User, task: CounselorTask) -> bool:
    """Every field but the status: the admin always; a counselor on the tasks they created themself."""
    return is_admin(user) or task.created_by_user_id == user.id


def scope(user: User) -> list:
    """A counselor's own tasks only; the admin's are all."""
    return [] if is_admin(user) else [CounselorTask.counselor_user_id == user.id]


# --- bands (T6, IST) -----------------------------------------------------------------------------------------------------------
def _done_since(today: date) -> datetime:
    return datetime.combine(today - timedelta(days=DONE_DAYS - 1), time.min, INDIA)


def band_of(task: CounselorTask, today: date) -> str | None:
    """The task's band; `None` for a task done before the 7-day window."""
    if task.status == "cancelled":
        return "cancelled"
    if task.status == "done":
        return "done" if task.completed_at and task.completed_at >= _done_since(today) else None
    if task.due_on < today:
        return "overdue"
    return "today" if task.due_on == today else "upcoming"


def band_filter(band: str, today: date):
    is_open = CounselorTask.status == "open"
    return {
        "overdue": and_(is_open, CounselorTask.due_on < today),
        "today": and_(is_open, CounselorTask.due_on == today),
        "upcoming": and_(is_open, CounselorTask.due_on > today),
        "done": and_(CounselorTask.status == "done", CounselorTask.completed_at >= _done_since(today)),
        "cancelled": CounselorTask.status == "cancelled",
    }[band]


def _active(today: date):
    return or_(CounselorTask.status == "open", band_filter("done", today))


def _ordering() -> tuple:
    """Open tasks by due day then priority; done (listed last) newest first; cancelled newest first."""
    is_done = CounselorTask.status != "open"
    return (
        is_done,
        case((is_done, func.coalesce(CounselorTask.completed_at, CounselorTask.cancelled_at))).desc().nulls_last(),
        CounselorTask.due_on,
        PRIORITY_RANK,
        CounselorTask.created_at,
        CounselorTask.id,
    )


# --- reads -----------------------------------------------------------------------------------------------------------------------
_counselor, _creator = aliased(User), aliased(User)


def _rows():
    """One query: the task, its counselor and its creator -- no N+1."""
    return select(CounselorTask, _counselor, _creator).join(_counselor, _counselor.id == CounselorTask.counselor_user_id).join(_creator, _creator.id == CounselorTask.created_by_user_id)


def _person(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name}


def _link_ref(task: CounselorTask) -> tuple[str, object] | None:
    for kind, column in LINK_COLUMNS.items():
        if getattr(task, column) is not None:
            return kind, getattr(task, column)
    return None


async def _link_labels(db: AsyncSession, tasks: list[CounselorTask]) -> dict[tuple[str, object], str]:
    """One query per link type on the page."""
    wanted: dict[str, set] = {kind: set() for kind in LINK_COLUMNS}
    for task in tasks:
        if ref := _link_ref(task):
            wanted[ref[0]].add(ref[1])
    labels: dict[tuple[str, object], str] = {}
    if wanted["lead"]:
        for i, code, name in (await db.execute(select(Enquiry.id, Enquiry.lead_code, Enquiry.name).where(Enquiry.id.in_(wanted["lead"])))).all():
            labels["lead", i] = f"{code} · {name}"
    if wanted["student"]:
        for i, name, code in (await db.execute(select(User.id, User.full_name, User.student_code).where(User.id.in_(wanted["student"])))).all():
            labels["student", i] = f"{name} · {code}" if code else name
    if wanted["application"]:
        rows = await db.execute(
            select(OverseasApplication.id, OverseasApplication.application_code, University.name)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.id.in_(wanted["application"]))
        )
        for i, code, university in rows.all():
            labels["application", i] = f"{code} · {university}"
    return labels


def _out(user: User, task: CounselorTask, counselor: User, creator: User, labels: dict, today: date) -> dict:
    ref = _link_ref(task)
    return {
        "id": task.id,
        "title": task.title,
        "due_on": task.due_on,
        "priority": task.priority,
        "status": task.status,
        "band": band_of(task, today),
        "source": task.source,
        "completed_at": task.completed_at,
        "link": None if ref is None else {"type": ref[0], "id": ref[1], "label": labels.get(ref, "")},
        "counselor": _person(counselor),
        "created_by": _person(creator),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "can_edit": can_edit(user, task),
    }


async def _counts(db: AsyncSession, where: list, today: date) -> dict:
    row = (await db.execute(select(*(func.count().filter(band_filter(b, today)) for b in BANDS)).select_from(CounselorTask).where(*where))).one()
    return dict(zip(BANDS, (n or 0 for n in row), strict=True))


async def page(db: AsyncSession, user: User, *, where: list, band: str | None, limit: int, offset: int) -> dict:
    """Without `band`: overdue, today, upcoming and done in the last 7 days. The counts use every filter but the band."""
    today = india_today()
    selected = [*where, band_filter(band, today) if band else _active(today)]
    total = await db.scalar(select(func.count()).select_from(CounselorTask).where(*selected))
    rows = (await db.execute(_rows().where(*selected).order_by(*_ordering()).limit(limit).offset(offset))).all()
    labels = await _link_labels(db, [row[0] for row in rows])
    return {
        "items": [_out(user, *row, labels, today) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "today": today,
        "counts": await _counts(db, where, today),
    }


async def one(db: AsyncSession, user: User, task_id) -> dict:
    """The row as written (populate_existing: never a stale identity-map copy after a commit); out of scope reads as missing."""
    found = (await db.execute(_rows().where(CounselorTask.id == task_id, *scope(user)).execution_options(populate_existing=True))).first()
    if found is None:
        raise HTTPException(404, NOT_FOUND)
    return _out(user, *found, await _link_labels(db, [found[0]]), india_today())


async def options(db: AsyncSession, user: User, counselor_id) -> dict:
    """The form's choices: the admin's counselors, and the links of the chosen counselor (a counselor: their own)."""
    counselors = []
    if is_admin(user):
        counselors = [_person(c) for c in (await db.scalars(active_counselors("overseas").order_by(User.full_name, User.id))).all()]
    target = user if not is_admin(user) else counselor_id and await db.scalar(active_counselors("overseas").where(User.id == counselor_id))
    links: dict[str, list] = {"leads": [], "students": [], "applications": []}
    if target:
        leads = await db.execute(
            select(Enquiry.id, Enquiry.lead_code, Enquiry.name)
            .where(Enquiry.owner_id == target.id, Enquiry.division == "overseas", Enquiry.status.not_in(CLOSED))
            .order_by(Enquiry.created_at.desc())
            .limit(OPTIONS_LIMIT)
        )
        links["leads"] = [{"id": i, "label": f"{code} · {name}"} for i, code, name in leads.all()]
        students = await db.execute(select(User.id, User.full_name, User.student_code).where(User.id.in_(visible_student_ids(target))).order_by(User.full_name, User.id).limit(OPTIONS_LIMIT))
        links["students"] = [{"id": i, "label": f"{name} · {code}" if code else name} for i, name, code in students.all()]
        apps = await db.execute(
            select(OverseasApplication.id, OverseasApplication.application_code, University.name)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.counselor_id == target.id, OverseasApplication.status != "withdrawn")
            .order_by(OverseasApplication.created_at.desc())
            .limit(OPTIONS_LIMIT)
        )
        links["applications"] = [{"id": i, "label": f"{code} · {university}"} for i, code, university in apps.all()]
    return {"counselors": counselors, "links": links}


# --- rules (T1, T3, T4) ----------------------------------------------------------------------------------------------------------
def link_of(task: CounselorTask) -> dict | None:
    ref = _link_ref(task)
    return None if ref is None else {"type": ref[0], "id": ref[1]}


async def _link_in_scope(db: AsyncSession, counselor: User, link: dict) -> bool:
    kind, target = link["type"], link["id"]
    if kind == "lead":
        stmt = exists().where(Enquiry.id == target, Enquiry.owner_id == counselor.id, Enquiry.division == counselor.division)
        return bool(await db.scalar(select(stmt)))
    if kind == "student":
        return await is_visible_student(db, counselor, target)
    return bool(await db.scalar(select(exists().where(OverseasApplication.id == target, OverseasApplication.counselor_id == counselor.id))))


async def check(db: AsyncSession, state: dict, before: dict | None = None) -> None:
    """The merged state of a create or change; only fields set or changed are checked, so an overdue task, or one whose counselor or
    link has since moved on, stays editable. A new counselor re-checks the link against their scope."""

    def changed(field: str) -> bool:
        return before is None or state[field] != before[field]

    counselor = None
    if changed("counselor_user_id"):
        counselor = await db.scalar(active_counselors("overseas").where(User.id == state["counselor_user_id"]))
        if counselor is None:
            raise field_error("counselor_user_id", CHOOSE_COUNSELOR)
    today = india_today()
    if changed("due_on") and not today <= state["due_on"] <= today + MAX_AHEAD:
        raise field_error("due_on", DUE_WINDOW)
    if state["link"] is not None and (changed("link") or changed("counselor_user_id")):
        counselor = counselor or await db.get_one(User, state["counselor_user_id"])
        if not await _link_in_scope(db, counselor, state["link"]):
            raise field_error("link", LINK_OUT_OF_SCOPE)


def apply(task: CounselorTask, state: dict, changed: list[str]) -> None:
    for field in changed:
        if field == "link":
            for kind, column in LINK_COLUMNS.items():
                setattr(task, column, state["link"]["id"] if state["link"] and state["link"]["type"] == kind else None)
        elif field == "status":
            set_status(task, state["status"])
        else:
            setattr(task, field, state[field])


def set_status(task: CounselorTask, status: str) -> None:
    """T2: done stamps `completed_at`, reopening clears it; cancelled stamps `cancelled_at` and is final (the route refuses after)."""
    task.status = status
    task.completed_at = datetime.now(UTC) if status == "done" else None
    task.cancelled_at = datetime.now(UTC) if status == "cancelled" else None


def audit(db: AsyncSession, user: User, task: CounselorTask, verb: str, changed: list[str]) -> None:
    db.add(AuditLog(user_id=user.id, action=f"counselor_task.{verb}", entity_type="counselor_task", entity_id=str(task.id), metadata_json={"fields": changed}))


def verb_for(changed: list[str], status: str) -> str:
    """`complete` / `reopen` / `cancel` when the status moved, `update` otherwise."""
    return STATUS_VERBS[status] if "status" in changed else "update"


# --- notification (T5) -----------------------------------------------------------------------------------------------------------
def line(task: CounselorTask) -> str:
    return f"{task.title} — due {task.due_on.strftime('%d %b %Y')} — {PRIORITY_LABELS[task.priority]} priority"


async def notify(db: AsyncSession, actor: User, task: CounselorTask, previous_counselor) -> None:
    """The counselor hears about a task someone else gave them or changed; their own changes notify nobody."""
    if task.counselor_user_id == actor.id:
        return
    title = "A task was assigned to you" if task.counselor_user_id != previous_counselor else "A task assigned to you changed"
    recipient = await db.get_one(User, task.counselor_user_id)
    note = Notification(user_id=recipient.id, title=title, body=line(task), read=False, action_url=TASKS_URL)
    db.add(note)
    await queue_deliveries(db, note, recipient)


# --- writes ------------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, payload: dict) -> CounselorTask:
    """A checked new task, audited and its counselor notified, in the caller's transaction (the caller commits)."""
    if not is_admin(user):
        if payload["counselor_user_id"] not in (None, user.id):
            raise HTTPException(403, OWN_ONLY)
        payload["counselor_user_id"] = user.id
    elif payload["counselor_user_id"] is None:
        raise field_error("counselor_user_id", CHOOSE_COUNSELOR)
    state = {**payload, "status": "open"}
    await check(db, state)
    task = CounselorTask(title=state["title"], due_on=state["due_on"], priority=state["priority"], counselor_user_id=state["counselor_user_id"], created_by_user_id=user.id, updated_by_user_id=user.id)
    apply(task, state, ["link"])
    db.add(task)
    await db.flush()
    audit(db, user, task, "create", list(FIELDS))
    await notify(db, user, task, None)
    return task


async def load(db: AsyncSession, user: User, task_id) -> CounselorTask:
    """The task locked for a write; another counselor's task is a 404, checked after the lock so a reassignment racing the change wins."""
    task = await db.scalar(select(CounselorTask).where(CounselorTask.id == task_id, *scope(user)).with_for_update().execution_options(populate_existing=True))
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    return task


async def change(db: AsyncSession, user: User, task: CounselorTask, changes: dict) -> list[str]:
    """A partial change of a locked task; returns the fields that changed (none = nothing recorded)."""
    if task.status == "cancelled":
        raise HTTPException(409, CANCELLED)
    before = {f: getattr(task, f) for f in FIELDS if f != "link"} | {"link": link_of(task)}
    state = {**before, **changes}
    changed = [f for f in FIELDS if state[f] != before[f]]
    if not changed:
        return []
    if "counselor_user_id" in changed and not is_admin(user):
        raise HTTPException(403, OWN_ONLY)
    if set(changed) - {"status"} and not can_edit(user, task):
        raise HTTPException(403, STATUS_ONLY)
    await check(db, state, before)
    apply(task, state, changed)
    task.updated_by_user_id = user.id
    audit(db, user, task, verb_for(changed, task.status), changed)
    await notify(db, user, task, before["counselor_user_id"])
    return changed
