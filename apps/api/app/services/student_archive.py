"""ccrm-040 (DEC-SCOPE-275, AR1-AR7) -- archive instead of delete. The student's csc-001 counselor or the Overseas Admin archives an
overseas student whose applications are all closed; only the Admin restores. An archived student's applications are archived with
them (derived from the archive row, no per-application flag): both leave the staff working lists and no new application is opened.
Functions only; the routes commit."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, OverseasApplication, OverseasStudentArchive, OverseasStudentCounselor, User
from app.services import application_outcomes as outcomes
from app.services.counselor_students import _notify, require_overseas_counselor
from app.services.student_profiles import _is_admin, staff_student

ARCHIVED, RESTORED = "overseas.student.archive", "overseas.student.restore"
OWNER_ONLY = "Only the student's counselor or the Overseas Admin can archive this student"
ADMIN_ONLY = "Only the Overseas Admin can restore a student"
ALREADY_ARCHIVED = "This student is already archived"
NOT_ARCHIVED = "This student is not archived"
NO_NEW_APPLICATION = "This student is archived. The Overseas Admin can restore them."
Archiver = aliased(User)


def not_archived(student_id_column):
    """For `.where(...)`: the student (or the application's student) is not archived. A NULL student id (a School-bridged application)
    matches no archive row, so it stays."""
    return ~exists().where(OverseasStudentArchive.student_user_id == student_id_column)


async def is_archived(db: AsyncSession, student_id: UUID) -> bool:
    return await db.get(OverseasStudentArchive, student_id) is not None


async def refuse_new_application(db: AsyncSession, student_id: UUID) -> None:
    """AR6: no new application for an archived student, whoever asks."""
    if await is_archived(db, student_id):
        raise HTTPException(409, NO_NEW_APPLICATION)


async def _counselor_id(db: AsyncSession, student_id: UUID) -> UUID | None:
    return await db.scalar(select(OverseasStudentCounselor.counselor_user_id).where(OverseasStudentCounselor.student_user_id == student_id))


async def permissions(db: AsyncSession, user: User, student: User, archived: bool) -> dict:
    """What the 360 offers: the same rules as the writes below."""
    owner = _is_admin(user) or await _counselor_id(db, student.id) == user.id
    return {"archive": owner and not archived, "restore": _is_admin(user) and archived}


def archive_out(row: OverseasStudentArchive, archived_by: str | None) -> dict:
    return {"archived_at": row.created_at, "archived_by": archived_by, "reason": row.reason}


async def read(db: AsyncSession, student_id: UUID) -> dict | None:
    found = (
        await db.execute(
            select(OverseasStudentArchive, Archiver.full_name)
            .join(Archiver, Archiver.id == OverseasStudentArchive.archived_by_user_id)
            .where(OverseasStudentArchive.student_user_id == student_id)
        )
    ).first()
    return archive_out(*found) if found else None


async def _tell_counselor(db: AsyncSession, actor: User, student: User, title: str, body: str) -> None:
    """When the Admin acts, the student's counselor hears about it (an inactive counselor is not told)."""
    counselor_id = await _counselor_id(db, student.id)
    if counselor_id is None or counselor_id == actor.id:
        return
    counselor = await db.get(User, counselor_id)
    if counselor is not None and counselor.active:
        await _notify(db, counselor, title, body)


async def archive(db: AsyncSession, user: User, student_id: UUID, reason: str) -> dict:
    """No commit. AR1-AR3. The student row is locked so an archive and a restore of the same student serialise; the primary key on the
    archive row stops a second archive either way."""
    if not _is_admin(user):
        require_overseas_counselor(user, OWNER_ONLY)
    student = await staff_student(db, user, student_id)  # csc-001 scope or the Admin; anything else is a 404
    if not _is_admin(user) and await _counselor_id(db, student.id) != user.id:
        raise HTTPException(403, OWNER_ONLY)
    await db.execute(select(User.id).where(User.id == student.id).with_for_update())
    if await is_archived(db, student.id):
        raise HTTPException(409, ALREADY_ARCHIVED)
    apps = (await db.scalars(select(OverseasApplication).where(OverseasApplication.student_id == student.id))).all()
    open_codes = sorted(a.application_code or str(a.id) for a in apps if not outcomes.is_closed(a) and a.status != "enrolled")
    if open_codes:
        raise HTTPException(409, f"Close or withdraw the student's open applications first: {', '.join(open_codes)}")
    row = OverseasStudentArchive(student_user_id=student.id, archived_by_user_id=user.id, reason=reason)
    db.add(row)
    db.add(AuditLog(user_id=user.id, action=ARCHIVED, entity_type="user", entity_id=str(student.id), outcome="archived", metadata_json={"reason": reason}))
    await _tell_counselor(db, user, student, "Student archived", f"{student.full_name} was archived by the Overseas Admin. Reason: {reason}")
    await db.flush()
    await db.refresh(row)
    return archive_out(row, user.full_name)


async def restore(db: AsyncSession, user: User, student_id: UUID) -> dict:
    """No commit. AR1/AR4: the Admin only; the row goes, the audit log keeps the history."""
    if not _is_admin(user):
        raise HTTPException(403, ADMIN_ONLY)
    student = await staff_student(db, user, student_id)
    await db.execute(select(User.id).where(User.id == student.id).with_for_update())
    row = await db.get(OverseasStudentArchive, student.id, populate_existing=True)
    if row is None:
        raise HTTPException(409, NOT_ARCHIVED)
    await db.delete(row)
    db.add(AuditLog(user_id=user.id, action=RESTORED, entity_type="user", entity_id=str(student.id), outcome="restored", metadata_json={}))
    await _tell_counselor(db, user, student, "Student restored", f"{student.full_name} was restored by the Overseas Admin and is back in your lists.")
    return {"id": student.id, "archived": False}


async def page(db: AsyncSession, user: User, limit: int, offset: int) -> dict:
    """AR7: archived students, newest first -- every one for the Admin, the counselor's own (csc-001 link) otherwise."""
    if not _is_admin(user):
        require_overseas_counselor(user, "Only overseas staff can list archived students")
    stmt = select(User, OverseasStudentArchive, Archiver.full_name).join(OverseasStudentArchive, OverseasStudentArchive.student_user_id == User.id)
    stmt = stmt.join(Archiver, Archiver.id == OverseasStudentArchive.archived_by_user_id)
    if not _is_admin(user):
        stmt = stmt.join(OverseasStudentCounselor, OverseasStudentCounselor.student_user_id == User.id).where(OverseasStudentCounselor.counselor_user_id == user.id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(OverseasStudentArchive.created_at.desc(), User.id).limit(limit).offset(offset))).all()
    items = [{"id": s.id, "full_name": s.full_name, "email": s.email, "student_code": s.student_code, **archive_out(a, by)} for s, a, by in rows]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
