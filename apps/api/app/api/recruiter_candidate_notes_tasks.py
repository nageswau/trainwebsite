"""hrc-016 (DEC-SCOPE-387, API §12KF): a candidate's private notes and tasks, and the caller's "My tasks".

The candidate rule (rec-009 R11): candidate readers read, writers write, on any pool candidate; another role 403. Every write is one
transaction -- role, the candidate lock (archived 409), the task lock and state, validation, change, audit, one commit here, then the log
line (ids only)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET, SEARCH
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import User
from app.schemas import CandidateAssignee, CandidateNoteIn, CandidateTaskCreate, CandidateTaskUpdate
from app.services import candidate_notes_tasks as svc
from app.services import candidates
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/recruiter", tags=["recruiter-candidate-notes-tasks"])


@router.get("/candidates/{candidate_id}/notes")
async def list_notes(candidate_id: UUID, response: Response, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):  # fmt: skip
    """T2: internal only -- the one route that serves a note's text (the timeline shows an excerpt)."""
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id, viewer_id=user.id)
    response.headers.update(NO_STORE)
    return await svc.note_page(db, candidate.id, limit, offset)


@router.post("/candidates/{candidate_id}/notes", status_code=201)
async def add_note(candidate_id: UUID, payload: CandidateNoteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Append-only; not idempotent (a retry adds a second note)."""
    candidates.require_writer(user)
    candidate = await candidates.load(db, candidate_id, lock=True, viewer_id=user.id)
    svc.require_open_candidate(candidate)
    note = await svc.add_note(db, user, candidate, payload.body)
    await db.commit()
    svc.log("candidate_note_added", user, candidate.id, note_id=note["id"])
    return note


@router.get("/candidates/{candidate_id}/tasks")
async def list_candidate_tasks(candidate_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id, viewer_id=user.id)
    return await svc.candidate_page(db, user, candidate.id, await db_now(db), limit, offset)


@router.post("/candidates/{candidate_id}/tasks", status_code=201)
async def create_task(candidate_id: UUID, payload: CandidateTaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Not idempotent (a retry adds a second task)."""
    candidates.require_writer(user)
    candidate = await candidates.load(db, candidate_id, lock=True, viewer_id=user.id)
    svc.require_open_candidate(candidate)
    now = await db_now(db)
    task = await svc.create(db, user, candidate, payload, now)
    await db.commit()
    svc.log("candidate_task_created", user, candidate.id, task_id=task.id, task_type=payload.task_type)
    return await svc.one(db, user, task.id, now)


@router.get("/candidate-tasks")
async def my_tasks(due: Literal["today", "overdue", "upcoming"] = "today", limit: int = LIMIT, offset: int = OFFSET,
                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    """T8 (AC2): the caller's own open tasks; only roles that can be assigned one have the list (QA-01: in its own words)."""
    if user.role not in candidates.WRITERS:
        raise HTTPException(403, "Your role has no candidate tasks")
    return await svc.my_page(db, user, due, await db_now(db), limit, offset)


@router.get("/candidate-tasks/assignees", response_model=list[CandidateAssignee])
async def assignees(q: str | None = SEARCH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T4: the assignee picker -- active people who may be given a task (names and roles only)."""
    candidates.require_writer(user)
    return await svc.lookup(db, like_pattern(q))


@router.patch("/candidate-tasks/{task_id}")
async def update_task(task_id: UUID, payload: CandidateTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    task = await svc.load_for_write(db, user, task_id)
    now = await db_now(db)
    changed = await svc.update(db, user, task, payload.model_dump(exclude_unset=True), now)
    await db.commit()
    if changed:
        svc.log("candidate_task_updated", user, task.candidate_id, task_id=task_id, fields=",".join(changed))
    return await svc.one(db, user, task_id, now)


async def _close(db: AsyncSession, user: User, task_id: UUID, status: str) -> dict:
    task = await svc.load_for_write(db, user, task_id)
    now = await db_now(db)
    svc.close(db, user, task, status, now)
    await db.commit()
    svc.log(f"candidate_task_{'completed' if status == 'done' else 'cancelled'}", user, task.candidate_id, task_id=task_id)
    return await svc.one(db, user, task_id, now)


@router.post("/candidate-tasks/{task_id}/complete")
async def complete_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A second complete meets `done` under the lock -> 409."""
    return await _close(db, user, task_id, "done")


@router.post("/candidate-tasks/{task_id}/cancel")
async def cancel_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _close(db, user, task_id, "cancelled")
