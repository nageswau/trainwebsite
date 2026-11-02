"""itc-028 (DEC-SCOPE-351): internal vs student-visible notes on an IT student (spec 2026-11-02-itc-028-it-student-notes-design.md).

N2 -- who reaches a student, each in the scope they already have (anything outside it is the same 404 as a missing student; any other role
is 403): the IT counselor their itc-003 linked students, HR (`hr_team` with `student_progress.view`) the nehn-017 placement pool, a trainer
the students seated in a batch they teach, the IT Admin any IT student. N3: they all read every note on the student, whoever wrote it.
N4: a note starts internal and is append-only. N5: only its author or the IT Admin changes its visibility -- audited before/after, a
no-op changes nothing. N8: a share sends the student one fixed-text notice (never the note). N7: the student reads only their own shared
notes through `feed`, whose items are an explicit allow-list (the leak guard of AC1).

Logs and audit rows carry ids and the visibility only, never the note's text."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Enrollment, ItStudentCounselor, ItStudentNote, User
from app.notifications.events import notify
from app.services import hr_students
from app.services.audit_changes import audit_change
from app.services.permissions import user_has_grant

STAFF_ONLY = "Only the student's IT counselor, trainer, HR or the IT Admin can see these notes"
STUDENTS_ONLY = "Only an IT student has updates"
AUTHOR_ONLY = "Only the note's author or the IT Admin can change who sees it"
STUDENT_NOT_FOUND, NOTE_NOT_FOUND = "Student not found", "Note not found"
VISIBILITY = "it.student_note.visibility"
SHARED_EVENT, UPDATES_URL = "it.student.update_shared", "/it/student/updates"
UNSEATED = ("pending_consent", "rejected")  # workflows.PROGRESS_UNSEATED: never one of the batch's students


def _is_admin(user: User) -> bool:
    return user.role == "it_admin" and user.division == "it"


async def _scope(db: AsyncSession, user: User):
    """The caller's reachable-student condition on `User`, or 403 for a role without one."""
    if _is_admin(user):
        return true()
    if user.role == "counselor" and user.division == "it":
        return select(ItStudentCounselor.id).where(ItStudentCounselor.student_user_id == User.id, ItStudentCounselor.counselor_user_id == user.id).exists()
    if user.role == "trainer" and user.division == "it":
        seated = select(Enrollment.id).join(Batch, Batch.id == Enrollment.batch_id)
        return seated.where(Enrollment.student_id == User.id, Batch.trainer_id == user.id, Enrollment.status.not_in(UNSEATED)).exists()
    if user.role in hr_students.HR_ROLES and await user_has_grant(db, user, "student_progress", "view"):
        return User.id.in_(hr_students.population())
    raise HTTPException(403, STAFF_ONLY)


async def staff_student(db: AsyncSession, user: User, student_id: UUID) -> User:
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "it_student", User.division == "it", await _scope(db, user)))
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    return student


def _staff_out(note: ItStudentNote, author: User, reader: User) -> dict:
    return {
        "id": note.id, "body": note.body, "visibility": note.visibility, "author_name": author.full_name, "author_role": author.role,
        "created_at": note.created_at, "shared_at": note.shared_at, "can_change_visibility": note.author_user_id == reader.id or _is_admin(reader),
    }  # fmt: skip


def _page(items: list, total: int | None, limit: int, offset: int) -> dict:
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def page(db: AsyncSession, user: User, student: User, limit: int, offset: int) -> dict:
    mine = ItStudentNote.student_user_id == student.id
    total = await db.scalar(select(func.count()).select_from(ItStudentNote).where(mine))
    rows = (
        await db.execute(
            select(ItStudentNote, User).join(User, User.id == ItStudentNote.author_user_id).where(mine)
            .order_by(ItStudentNote.created_at.desc(), ItStudentNote.id.desc()).limit(limit).offset(offset)
        )
    ).all()  # fmt: skip
    student_out = {"id": student.id, "full_name": student.full_name, "student_code": student.student_code}
    return {"student": student_out, **_page([_staff_out(note, author, user) for note, author in rows], total, limit, offset)}


async def create(db: AsyncSession, user: User, student: User, body: str) -> dict:
    """Commits one insert (always internal, N4), then re-reads the row for its server-set times."""
    note = ItStudentNote(student_user_id=student.id, author_user_id=user.id, body=body)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _staff_out(note, user, user)


async def set_visibility(db: AsyncSession, user: User, student: User, note_id: UUID, visibility: str) -> dict:
    """Commits. The note row is locked, so two shares of one note cannot both notify the student."""
    note = await db.scalar(select(ItStudentNote).where(ItStudentNote.id == note_id, ItStudentNote.student_user_id == student.id).with_for_update())
    if note is None:
        raise HTTPException(404, NOTE_NOT_FOUND)
    if note.author_user_id != user.id and not _is_admin(user):
        raise HTTPException(403, AUTHOR_ONLY)
    changed = note.visibility != visibility
    if changed:
        audit_change(db, user, VISIBILITY, "it_student_note", note.id, {"visibility": note.visibility}, {"visibility": visibility},
                     metadata={"student_id": str(student.id)})  # fmt: skip
        note.visibility, note.shared_at = visibility, func.now() if visibility == "student" else None
        if visibility == "student":
            await notify(db, [student], SHARED_EVENT, note.id, action_url=UPDATES_URL)
        await db.commit()
        await db.refresh(note)
    author = user if note.author_user_id == user.id else await db.get(User, note.author_user_id)
    return {**_staff_out(note, author, user), "changed": changed}


def require_student(user: User) -> User:
    if user.role != "it_student" or user.division != "it":
        raise HTTPException(403, STUDENTS_ONLY)
    return user


async def feed(db: AsyncSession, student: User, limit: int, offset: int) -> dict:
    """N7: the student's own shared notes, newest share first -- only the allow-listed fields below ever leave this function."""
    shared = (ItStudentNote.student_user_id == student.id) & (ItStudentNote.visibility == "student")
    total = await db.scalar(select(func.count()).select_from(ItStudentNote).where(shared))
    rows = (
        await db.execute(
            select(ItStudentNote.id, ItStudentNote.body, ItStudentNote.shared_at, User.full_name, User.role)
            .join(User, User.id == ItStudentNote.author_user_id).where(shared)
            .order_by(ItStudentNote.shared_at.desc(), ItStudentNote.id.desc()).limit(limit).offset(offset)
        )
    ).all()  # fmt: skip
    items = [{"id": i, "body": body, "author_name": name, "author_role": role, "shared_at": at} for i, body, at, name, role in rows]
    return _page(items, total, limit, offset)
