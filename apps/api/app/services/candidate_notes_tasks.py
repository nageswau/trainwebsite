"""hrc-016 (DEC-SCOPE-385, spec docs/superpowers/specs/2026-11-04-hrc-016-candidate-notes-tasks-timeline-design.md): private candidate
notes (T2) and candidate tasks (T3-T8).

Both follow the candidate's own rule (rec-009 R11): every candidate reader reads them, every writer writes them, on any pool candidate.
Notes are internal only: this module and the candidate timeline are the only readers of `candidate_notes`. Functions only; nothing here
commits -- the route owns the transaction. Audit rows and logs carry ids and field names, never a note's or task's text."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, Candidate, CandidateNote, CandidateTask, Job, JobApplication, RecruiterProfile, User
from app.notifications.events import notify
from app.schemas import CandidateTaskCreate
from app.services import candidates
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_follow_ups import check_due
from app.services.recruiter import ROLE

logger = logging.getLogger("app.candidates")

TASK_NOT_FOUND = "Task not found"
STATE_REFUSALS = {"done": "This task is already done", "cancelled": "This task was cancelled"}
ASSIGNEE_INVALID = "Choose an active recruiter or manager"
APPLICATION_INVALID = "Choose an application of this candidate"
JOB_INVALID = "Choose a requirement"
APPLICATION_MISMATCH = "The application is for another requirement"
LOOKUP_LIMIT = 20
VIEWS = ("today", "overdue", "upcoming")

T = CandidateTask
IS_OPEN = T.status == "open"
Assignee, Creator, Completer = aliased(User), aliased(User), aliased(User)


def _person(user: User | None) -> dict | None:
    return None if user is None else {"id": user.id, "full_name": user.full_name}


def _audit(db: AsyncSession, user: User, entity: str, action: str, row_id: UUID, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"{entity}.{action}", entity_type=f"{entity}s", entity_id=str(row_id), metadata_json=metadata))


def log(event: str, user: User, candidate_id: UUID, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "candidate_id": str(candidate_id), **{k: str(v) for k, v in extra.items()}}})


def require_open_candidate(candidate: Candidate) -> None:
    """An archived (or merged) candidate takes no new note or task -- the calls/messages rule."""
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)


# --- notes (T2) -----------------------------------------------------------------------------------------------------------------
def _note_out(note: CandidateNote, author: User | None) -> dict:
    return {"id": note.id, "body": note.body, "author": _person(author), "created_at": note.created_at}


async def note_page(db: AsyncSession, candidate_id: UUID, limit: int, offset: int) -> dict:
    where = CandidateNote.candidate_id == candidate_id
    total = await db.scalar(select(func.count()).select_from(CandidateNote).where(where))
    rows = (await db.execute(
        select(CandidateNote, User).outerjoin(User, User.id == CandidateNote.author_user_id).where(where)
        .order_by(CandidateNote.created_at.desc(), CandidateNote.id.desc()).limit(limit).offset(offset)
    )).all()  # fmt: skip
    return {"items": [_note_out(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def add_note(db: AsyncSession, user: User, candidate: Candidate, body: str) -> dict:
    note = CandidateNote(candidate_id=candidate.id, author_user_id=user.id, body=body)
    db.add(note)
    await db.flush()
    _audit(db, user, "candidate_note", "create", note.id, {"candidate_id": str(candidate.id)})
    await db.refresh(note)
    return _note_out(note, user)


# --- assignees (T4) -------------------------------------------------------------------------------------------------------------
def _eligible() -> list:
    """An active user who works candidates: a recruiter with a profile, a placement manager or super_admin."""
    return [User.active.is_(True), User.role.in_(candidates.WRITERS), or_(User.role != ROLE, exists().where(RecruiterProfile.user_id == User.id))]


async def _locked_assignee(db: AsyncSession, user_id: UUID) -> User:
    """FOR SHARE: a concurrent deactivation waits for this commit. Inactive, another role or unknown is one 422 (no probing which)."""
    person = await db.scalar(select(User).where(User.id == user_id, *_eligible()).with_for_update(read=True))
    if person is None:
        raise HTTPException(422, ASSIGNEE_INVALID)
    return person


async def lookup(db: AsyncSession, pattern: str | None) -> list[dict]:
    stmt = select(User.id, User.full_name, User.role).where(*_eligible())
    if pattern:
        stmt = stmt.where(User.full_name.ilike(pattern, escape="\\"))
    rows = (await db.execute(stmt.order_by(User.full_name, User.id).limit(LOOKUP_LIMIT))).all()
    return [{"id": i, "full_name": n, "role": r} for i, n, r in rows]


# --- tasks (T3-T8) --------------------------------------------------------------------------------------------------------------
def _rows():
    """One query: the task, its candidate, requirement, assignee, creator and completer -- no N+1."""
    return (
        select(T, Candidate, Job, Assignee, Creator, Completer)
        .join(Candidate, Candidate.id == T.candidate_id)
        .outerjoin(Job, Job.id == T.job_id)
        .join(Assignee, Assignee.id == T.assignee_user_id)
        .join(Creator, Creator.id == T.created_by_user_id)
        .outerjoin(Completer, Completer.id == func.coalesce(T.completed_by_user_id, T.cancelled_by_user_id))
    )


def _task_out(user: User, now: datetime, task: CandidateTask, candidate: Candidate, job: Job | None, assignee: User, creator: User, closer: User | None) -> dict:
    return {
        "id": task.id, "task_type": task.task_type, "title": task.title, "notes": task.notes, "due_at": task.due_at, "status": task.status,
        "overdue": task.status == "open" and task.due_at < now,
        "assignee": {"id": assignee.id, "full_name": assignee.full_name, "active": assignee.active},
        "candidate": {"id": candidate.id, "candidate_code": candidate.candidate_code, "name": candidate.name},
        "application_id": task.application_id,
        "requirement": None if job is None else {"id": job.id, "code": job.requirement_code, "title": job.title},
        "created_by": _person(creator), "created_at": task.created_at,
        "completed_at": task.completed_at, "completed_by": _person(closer) if task.status == "done" else None,
        "cancelled_at": task.cancelled_at, "cancelled_by": _person(closer) if task.status == "cancelled" else None,
        "can_change": task.status == "open" and user.role in candidates.WRITERS and candidate.archived_at is None,
    }  # fmt: skip


async def _page(db: AsyncSession, user: User, now: datetime, where: list, order: tuple, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(T).join(Candidate, Candidate.id == T.candidate_id).where(*where))
    rows = (await db.execute(_rows().where(*where).order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [_task_out(user, now, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, user: User, task_id: UUID, now: datetime) -> dict:
    return _task_out(user, now, *(await db.execute(_rows().where(T.id == task_id))).one())


async def candidate_page(db: AsyncSession, user: User, candidate_id: UUID, now: datetime, limit: int, offset: int) -> dict:
    """T11: open tasks by due time, then done / cancelled newest first."""
    order = (case((IS_OPEN, 0), else_=1), case((IS_OPEN, T.due_at)).asc(), func.coalesce(T.completed_at, T.cancelled_at).desc(), T.id)
    return await _page(db, user, now, [T.candidate_id == candidate_id], order, limit, offset)


def views(now: datetime) -> dict:
    """T8 = rec-024 FU2, in IST: Today = due before tonight's midnight (overdue included); Overdue = past due; Upcoming = from tomorrow."""
    _, tonight = day_range(today_ist(now))
    return {"today": IS_OPEN & (T.due_at < tonight), "overdue": IS_OPEN & (T.due_at < now), "upcoming": IS_OPEN & (T.due_at >= tonight)}


async def my_page(db: AsyncSession, user: User, due: str, now: datetime, limit: int, offset: int) -> dict:
    """AC2: the caller's own open tasks, oldest due first, with the three views' totals (so the tabs agree with the lists)."""
    mine = [T.assignee_user_id == user.id, *candidates.pool_filter()]
    conditions = views(now)
    out = await _page(db, user, now, [*mine, conditions[due]], (T.due_at, T.id), limit, offset)
    counts = (await db.execute(
        select(*(func.count().filter(c) for c in conditions.values())).select_from(T).join(Candidate, Candidate.id == T.candidate_id).where(*mine)
    )).one()  # fmt: skip
    return {**out, "day": today_ist(now), "counts": {view: n or 0 for view, n in zip(conditions, counts, strict=True)}}


async def _links(db: AsyncSession, candidate: Candidate, application_id: UUID | None, job_id: UUID | None) -> UUID | None:
    """T3: an application must be this candidate's (its job is taken from it); a requirement must exist and match the application."""
    if application_id is not None:
        application = await db.scalar(select(JobApplication).where(JobApplication.id == application_id, JobApplication.candidate_id == candidate.id))
        if application is None:
            raise HTTPException(422, APPLICATION_INVALID)
        if job_id is not None and job_id != application.job_id:
            raise HTTPException(422, APPLICATION_MISMATCH)
        return application.job_id
    if job_id is not None and await db.scalar(select(Job.id).where(Job.id == job_id)) is None:
        raise HTTPException(422, JOB_INVALID)
    return job_id


async def _notify(db: AsyncSession, actor: User, assignee: User, task_id: UUID) -> None:
    """T7: the assignee, never the actor; fixed text, so no candidate name reaches an email or a lock screen."""
    if assignee.id != actor.id:
        await notify(db, [assignee], "it.candidate.task_assigned", task_id, action_url="/recruiter/tasks")


async def create(db: AsyncSession, user: User, candidate: Candidate, payload: CandidateTaskCreate, now: datetime) -> CandidateTask:
    check_due(payload.due_at, now)
    job_id = await _links(db, candidate, payload.application_id, payload.job_id)
    assignee = await _locked_assignee(db, payload.assignee_user_id)
    task = CandidateTask(candidate_id=candidate.id, application_id=payload.application_id, job_id=job_id, task_type=payload.task_type, title=payload.title,
                         notes=payload.notes, due_at=payload.due_at, assignee_user_id=assignee.id, created_by_user_id=user.id)  # fmt: skip
    db.add(task)
    await db.flush()
    _audit(db, user, "candidate_task", "create", task.id, {"candidate_id": str(candidate.id), "task_type": task.task_type, "assignee_id": str(assignee.id)})
    await _notify(db, user, assignee, task.id)
    return task


async def load_for_write(db: AsyncSession, user: User, task_id: UUID) -> CandidateTask:
    """T5: writers only; the candidate (pool, not archived) then the task are locked, in that order, so a double complete is a 409."""
    candidates.require_writer(user)
    candidate_id = await db.scalar(select(T.candidate_id).where(T.id == task_id))
    if candidate_id is None:
        raise HTTPException(404, TASK_NOT_FOUND)
    require_open_candidate(await candidates.load(db, candidate_id, lock=True))
    task = await db.scalar(select(T).where(T.id == task_id).with_for_update())
    if task.status in STATE_REFUSALS:
        raise HTTPException(409, STATE_REFUSALS[task.status])
    return task


async def update(db: AsyncSession, user: User, task: CandidateTask, sent: dict, now: datetime) -> list[str]:
    """T6: equal values are not changes; only a changed due time must be in the future."""
    changed = sorted(key for key, value in sent.items() if getattr(task, key) != value)
    if "due_at" in changed:
        check_due(sent["due_at"], now)
    assignee = await _locked_assignee(db, sent["assignee_user_id"]) if "assignee_user_id" in changed else None
    for key in changed:
        setattr(task, key, sent[key])
    if changed:
        _audit(db, user, "candidate_task", "update", task.id, {"candidate_id": str(task.candidate_id), "fields": changed})
    if assignee is not None:
        await _notify(db, user, assignee, task.id)
    return changed


def close(db: AsyncSession, user: User, task: CandidateTask, status: str, now: datetime) -> None:
    if status == "done":
        task.status, task.completed_at, task.completed_by_user_id = "done", now, user.id
    else:
        task.status, task.cancelled_at, task.cancelled_by_user_id = "cancelled", now, user.id
    _audit(db, user, "candidate_task", "complete" if status == "done" else "cancel", task.id, {"candidate_id": str(task.candidate_id)})
