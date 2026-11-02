"""itc-003 (DEC-SCOPE-337): the IT student -> counselor link (`ItStudentCounselor`, one counselor per student -- Q-03). The lead's student
link sets it (`link_on_conversion`), undoing a mistaken link removes it (`unlink_on_unconversion`), the IT Admin moves it with a reason
(`assign`, csc-005 / ccrm-033's rules), and the IT counselor reads only their own students (`page`, `one`; anything else is 404).

Functions only; nothing here commits. Every write runs with the student's user row locked (the link path's `bdm_leads.locked_student`,
or `assign`'s own lock), so a link and a reassignment of one student serialise. Logs and audit rows carry ids and the reason only."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Enquiry, ItStudentCounselor, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services.counselor_students import reason_meta, require_reason, with_reason

logger = logging.getLogger("app.it_student_counselors")

IT_COUNSELOR_ONLY = "Only an IT counselor can view IT students"
ADMIN_ONLY = "Only the IT Admin can assign a counselor"
CHOOSE_ACTIVE_COUNSELOR = "Choose an active IT counselor"
STUDENT_NOT_FOUND = "Student not found"
LINKED, ASSIGNED = "it.student.counselor_link", "it.student.counselor_assign"
STUDENTS_URL = "/it/counselor/students"


def require_it_counselor(user: User, message: str = IT_COUNSELOR_ONLY) -> None:
    if user.role != "counselor" or user.division != "it":
        raise HTTPException(403, message)


def _is_it_counselor(user: User | None) -> bool:
    return user is not None and user.role == "counselor" and user.division == "it"


async def _row(db: AsyncSession, student_id: UUID) -> ItStudentCounselor | None:
    return await db.scalar(select(ItStudentCounselor).where(ItStudentCounselor.student_user_id == student_id))


async def link_on_conversion(db: AsyncSession, actor: User, lead: Enquiry, student_id: UUID) -> None:
    """An IT lead owned by an IT counselor gives its newly linked student that counselor -- only when the student has none yet (one per
    student; an existing counselor stays until the IT Admin moves them)."""
    if lead.division != "it" or lead.owner_id is None or await _row(db, student_id) is not None:
        return
    if not _is_it_counselor(await db.get(User, lead.owner_id)):
        return
    db.add(ItStudentCounselor(student_user_id=student_id, counselor_user_id=lead.owner_id, assigned_by_user_id=actor.id))
    db.add(AuditLog(user_id=actor.id, action=LINKED, entity_type="user", entity_id=str(student_id),
                    metadata_json={"counselor_id": str(lead.owner_id), "lead_id": str(lead.id)}))  # fmt: skip


async def unlink_on_unconversion(db: AsyncSession, lead: Enquiry, student_id: UUID) -> None:
    """A mistaken link is undone: its student leaves the lead owner's caseload. A link the IT Admin has moved since is kept."""
    row = await _row(db, student_id)
    if lead.division == "it" and row is not None and row.counselor_user_id == lead.owner_id:
        await db.delete(row)


async def _notify(db: AsyncSession, recipient: User, title: str, body: str) -> None:
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url=STUDENTS_URL)
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, recipient)


async def assign(db: AsyncSession, admin: User, student_id: UUID, counselor_id: UUID, reason: str | None = None) -> dict:
    """No commit. The IT Admin only (not super_admin, csc-005 C13); swap only; the same counselor changes nothing; replacing a counselor
    needs a reason (ccrm-033), kept in the audit row and sent to both counselors (a deactivated previous counselor is not told)."""
    if admin.role != "it_admin" or admin.division != "it":
        raise HTTPException(403, ADMIN_ONLY)
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "it_student").with_for_update())
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    counselor = await db.get(User, counselor_id)
    if not _is_it_counselor(counselor) or not counselor.active:
        raise HTTPException(422, CHOOSE_ACTIVE_COUNSELOR)
    result = {"id": student.id, "counselor_id": counselor.id, "counselor_name": counselor.full_name}
    row = await _row(db, student.id)
    if row is not None and row.counselor_user_id == counselor.id:
        return {**result, "changed": False}
    previous_id = row.counselor_user_id if row else None
    require_reason(previous_id, reason)
    if row is None:
        db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    else:
        row.counselor_user_id, row.assigned_by_user_id = counselor.id, admin.id
    db.add(AuditLog(user_id=admin.id, action=ASSIGNED, entity_type="user", entity_id=str(student.id),
                    metadata_json={"from_counselor_id": str(previous_id) if previous_id else None, "to_counselor_id": str(counselor.id), **reason_meta(reason)}))  # fmt: skip
    await _notify(db, counselor, "Student assigned to you", with_reason(f"{student.full_name} is now one of your students.", reason))
    previous = await db.get(User, previous_id) if previous_id else None
    if previous is not None and previous.active:
        await _notify(db, previous, "Student reassigned", with_reason("A student has moved to another counselor.", reason))
    return {**result, "changed": True}


def _mine(counselor: User):
    return (
        select(User, ItStudentCounselor.created_at)
        .join(ItStudentCounselor, ItStudentCounselor.student_user_id == User.id)
        .where(ItStudentCounselor.counselor_user_id == counselor.id, User.role == "it_student")
    )


def _out(student: User, since) -> dict:
    return {"id": student.id, "student_code": student.student_code, "full_name": student.full_name, "email": student.email, "phone": student.phone, "linked_since": since}


async def page(db: AsyncSession, counselor: User, limit: int, offset: int, pattern: str | None = None) -> dict:
    """The counselor's IT students, newest link first; `pattern` (a literal ILIKE pattern) narrows by name, email or Student ID."""
    stmt = _mine(counselor)
    if pattern:
        stmt = stmt.where(or_(*(column.ilike(pattern, escape="\\") for column in (User.full_name, User.email, User.student_code))))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(ItStudentCounselor.created_at.desc(), User.id).limit(limit).offset(offset))).all()
    return {"items": [_out(student, since) for student, since in rows], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, counselor: User, student_id: UUID) -> dict:
    row = (await db.execute(_mine(counselor).where(User.id == student_id))).first()
    if row is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    return _out(*row)


async def counselors_of(db: AsyncSession, student_ids: list[UUID]) -> dict[UUID, User]:
    """Each student's counselor, for the IT Admin's Students table and the student's own dashboard."""
    if not student_ids:
        return {}
    stmt = select(ItStudentCounselor.student_user_id, User).join(User, User.id == ItStudentCounselor.counselor_user_id).where(ItStudentCounselor.student_user_id.in_(student_ids))
    return {student_id: counselor for student_id, counselor in (await db.execute(stmt)).all()}
