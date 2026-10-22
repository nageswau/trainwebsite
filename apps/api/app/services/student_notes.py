"""ccrm-010 (DEC-SCOPE-241, N1-N4): internal notes on an overseas student -- the counselling history. The overseas counselor reads and
writes notes on the students in their csc-001 scope (own applications' plus linked students), whoever wrote them, so the history survives
a reassignment; the Overseas Admin does so for any overseas student. Append-only. No student- or agent-facing route returns these."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OverseasApplication, OverseasStudentNote, University, User
from app.schemas import StudentNoteCreate
from app.services.counselor_students import STUDENT_NOT_FOUND, is_visible_student

NOT_ALLOWED = "Only an overseas counselor or the Overseas Admin can see student notes"
CHOOSE_APPLICATION = "Choose one of this student's applications"


def _is_admin(user: User) -> bool:
    return user.role == "overseas_admin" and user.division == "overseas"


async def _student(db: AsyncSession, user: User, student_id: UUID) -> User:
    """The overseas student the caller may see; anything else is the same 404 (no disclosure)."""
    admin = _is_admin(user)
    if not admin and (user.role != "counselor" or user.division != "overseas"):  # N1: an IT counselor works leads only (tel-017)
        raise HTTPException(403, NOT_ALLOWED)
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "overseas_student"))
    if student is None or (not admin and not await is_visible_student(db, user, student_id)):
        raise HTTPException(404, STUDENT_NOT_FOUND)
    return student


def _label(university: str | None, reference: str | None) -> str | None:
    return f"{university} · {reference}" if reference else university


async def _applications(db: AsyncSession, user: User, student_id: UUID, application_id: UUID | None = None) -> list[dict]:
    """N3: the applications a note may be attached to -- the counselor's own for this student, or any of the student's for the admin."""
    stmt = (
        select(OverseasApplication.id, University.name, OverseasApplication.application_reference)
        .join(University, University.id == OverseasApplication.university_id)
        .where(OverseasApplication.student_id == student_id)
        .order_by(OverseasApplication.created_at, OverseasApplication.id)
    )
    if not _is_admin(user):
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    if application_id is not None:
        stmt = stmt.where(OverseasApplication.id == application_id)
    return [{"id": app_id, "label": _label(name, reference)} for app_id, name, reference in (await db.execute(stmt)).all()]


def _note_out(note: OverseasStudentNote, author: User, application: dict | None) -> dict:
    return {"id": note.id, "body": note.body, "author_name": author.full_name, "author_role": author.role, "application": application, "created_at": note.created_at}


async def page(db: AsyncSession, user: User, student_id: UUID, limit: int, offset: int) -> dict:
    student = await _student(db, user, student_id)
    mine = OverseasStudentNote.student_user_id == student.id
    total = await db.scalar(select(func.count()).select_from(OverseasStudentNote).where(mine))
    rows = (
        await db.execute(
            select(OverseasStudentNote, User, University.name, OverseasApplication.application_reference)
            .join(User, User.id == OverseasStudentNote.author_user_id)
            .outerjoin(OverseasApplication, OverseasApplication.id == OverseasStudentNote.application_id)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(mine)
            .order_by(OverseasStudentNote.created_at.desc(), OverseasStudentNote.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code},
        "applications": await _applications(db, user, student.id),
        "items": [_note_out(note, author, {"id": note.application_id, "label": _label(name, ref)} if note.application_id else None) for note, author, name, ref in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def create(db: AsyncSession, user: User, student_id: UUID, payload: StudentNoteCreate) -> dict:
    """Commits: one insert, then the row is re-read for its server-set `created_at`."""
    student = await _student(db, user, student_id)
    application = None
    if payload.application_id is not None:
        matches = await _applications(db, user, student.id, payload.application_id)
        if not matches:
            raise HTTPException(422, CHOOSE_APPLICATION)
        application = matches[0]
    note = OverseasStudentNote(student_user_id=student.id, application_id=payload.application_id, author_user_id=user.id, body=payload.body)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _note_out(note, user, application)
