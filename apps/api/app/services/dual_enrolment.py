"""ENH-033 (DEC-SCOPE-441): a counselor or telecaller of the target division adds that division to an existing student (D1), with a
counselor of that division always chosen (D2), adding only (D4), on the staff member's attestation that the student asked (D5), access
only -- no program enrolment or application (D6). Same login, same Student ID; the active portal is not changed."""

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ItStudentCounselor, Notification, OverseasStudentCounselor, User, UserRoleAssignment
from app.notifications.dispatch import queue_deliveries
from app.services.student_divisions import DIVISION_LABEL, STUDENT_ROLE, assignment, held_divisions, is_student_of, student_of

STAFF_ROLES = {"counselor", "telecaller"}
OTHER = {"it": "overseas", "overseas": "it"}
COUNSELOR_TABLE = {"it": ItStudentCounselor, "overseas": OverseasStudentCounselor}
ENROLLED = "student.dual_enrol"
STUDENT_ID = re.compile(r"^[0-9A-Za-z]{8}$")

NOT_FOUND = "No student found"
CONFIRM = "Confirm the student asked to enrol"


def require_staff(user: User, division: str) -> None:
    """D1: a counselor or telecaller of the target division only (not super_admin, not admins)."""
    if user.role not in STAFF_ROLES or user.division != division:
        raise HTTPException(403, f"Only a {DIVISION_LABEL[division]} counselor or telecaller can add a student to {DIVISION_LABEL[division]}")


def _ref_filter(ref: str):
    ref = ref.strip()
    if "@" in ref:
        return func.lower(User.email) == ref.lower()
    if STUDENT_ID.match(ref):
        return User.student_code == ref.upper()
    return None


async def _source_student(db: AsyncSession, division: str, where, *, lock: bool = False) -> User:
    """An active student of the *other* division (D4: adding to an existing student). Anything else is the same 404."""
    stmt = select(User).where(where, User.active.is_(True), student_of(OTHER[division]))
    student = await db.scalar(stmt.with_for_update(of=User) if lock else stmt)
    if student is None:
        raise HTTPException(404, NOT_FOUND)
    return student


async def lookup(db: AsyncSession, user: User, division: str, ref: str) -> dict:
    require_staff(user, division)
    where = _ref_filter(ref)
    if where is None:
        raise HTTPException(422, "Enter the student's email or 8-character Student ID")
    student = await _source_student(db, division, where)
    return {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "divisions": await held_divisions(db, student)}


async def enrol(db: AsyncSession, user: User, division: str, student_id: UUID, counselor_id: UUID, student_requested: bool) -> dict:
    """No commit. Locks the student row so two simultaneous adds serialise (the second sees the first's assignment)."""
    require_staff(user, division)
    if student_requested is not True:
        raise HTTPException(422, CONFIRM)
    student = await _source_student(db, division, User.id == student_id, lock=True)
    label = DIVISION_LABEL[division]
    existing = await assignment(db, student.id, division)
    if existing is not None and not existing.is_active:
        raise HTTPException(409, f"This student's {label} access was ended; ask an admin")
    if existing is not None or await is_student_of(db, student, division):
        raise HTTPException(409, f"Already enrolled in {label}")
    counselor = await db.get(User, counselor_id)
    if counselor is None or counselor.role != "counselor" or counselor.division != division or not counselor.active:
        raise HTTPException(422, f"Pick an active {label} counselor")

    if await assignment(db, student.id, student.division) is None:  # the source portal's row, so a switch away can come back
        db.add(UserRoleAssignment(user_id=student.id, division=student.division, role=student.role, is_active=True, approval_status="approved"))
    db.add(UserRoleAssignment(user_id=student.id, division=division, role=STUDENT_ROLE[division], is_active=True,
                              assigned_by_user_id=user.id, approval_status="approved"))  # fmt: skip
    table = COUNSELOR_TABLE[division]
    link = await db.scalar(select(table).where(table.student_user_id == student.id))
    if link is None:
        db.add(table(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=user.id))
    else:
        link.counselor_user_id, link.assigned_by_user_id = counselor.id, user.id
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"Already enrolled in {label}") from None
    db.add(AuditLog(user_id=user.id, action=ENROLLED, entity_type="user", entity_id=str(student.id),
                    metadata_json={"division": division, "counselor_id": str(counselor.id), "student_requested": True, "by_role": user.role}))  # fmt: skip
    await _notify(db, student, f"You are now enrolled in {label}",
                  f"You can now use the {label} student portal with your existing login. Use the Portal menu at the top to switch. "
                  f"Your {label} counselor is {counselor.full_name}.", None)  # no link: the new portal opens only after switching  # fmt: skip
    await _notify(db, counselor, "Student assigned to you", f"{student.full_name} has joined {label} and is now one of your students.",
                  f"/{division}/counselor/students")  # fmt: skip
    return {"student_id": student.id, "division": division, "counselor_id": counselor.id, "counselor_name": counselor.full_name}


async def _notify(db: AsyncSession, recipient: User, title: str, body: str, action_url: str | None) -> None:
    """In-app row plus queued email/push deliveries, sent after the commit (ENH-014), as csc-005's notices."""
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, recipient)


def counselor_picker_allowed(user: User, division: str) -> bool:
    """ENH-033: the target division's counselors and telecallers also use that division's counselor picker."""
    return user.role in STAFF_ROLES and user.division == division
