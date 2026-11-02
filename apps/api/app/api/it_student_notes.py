"""itc-028 (DEC-SCOPE-351) -- IT student notes: staff on /it/students/{id}/notes (the scope is the caller's role, services/it_student_notes
N2), the student's shared ones on /it/me/updates. API_CONTRACT.md §12IW; RBAC_MATRIX.md §2.251. Logs carry ids only, never a note."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import ItStudentNoteCreate, ItStudentNoteVisibility
from app.services import it_student_notes as notes

logger = logging.getLogger("app.it_student_notes")
router = APIRouter(prefix="/it/students", tags=["it-student-notes"])
me_router = APIRouter(prefix="/it/me", tags=["it-student-notes"])
Limit = Query(20, ge=1, le=100)
Offset = Query(0, ge=0)


def _log(event: str, actor: User, student_id: UUID, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), "actor_role": actor.role, "student_id": str(student_id), **extra}})


@router.get("/{student_id}/notes")
async def list_notes(student_id: UUID, limit: int = Limit, offset: int = Offset, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notes.page(db, user, await notes.staff_student(db, user, student_id), limit, offset)


@router.post("/{student_id}/notes", status_code=201)
async def add_note(student_id: UUID, payload: ItStudentNoteCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out = await notes.create(db, user, await notes.staff_student(db, user, student_id), payload.body)
    _log("it_student_note_added", user, student_id, note_id=str(out["id"]))
    return out


@router.put("/{student_id}/notes/{note_id}/visibility")
async def set_visibility(student_id: UUID, note_id: UUID, payload: ItStudentNoteVisibility, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):  # fmt: skip
    out = await notes.set_visibility(db, user, await notes.staff_student(db, user, student_id), note_id, payload.visibility)
    if out["changed"]:
        _log("it_student_note_visibility", user, student_id, note_id=str(note_id), visibility=payload.visibility)
    return out


@me_router.get("/updates")
async def my_updates(limit: int = Limit, offset: int = Offset, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await notes.feed(db, notes.require_student(user), limit, offset)
