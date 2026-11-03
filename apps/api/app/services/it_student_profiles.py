"""itc-012 (DEC-SCOPE-345): the IT student record -- the structured profile (`ItStudentProfile`: personal details and the emergency
contact) and the per-enrolment start/end date and delivery-mode overrides that default to the batch's.

Who: the IT student for themselves (profile only), their itc-003 counselor (only linked students; anything else is 404) and the IT Admin
(any IT student). Nobody else has a route (C1, Q-11: trainers, HR, placement and super_admin get 403). A save locks the student's user
row, so two first saves cannot both insert; last write wins after that. The profile's audit row names the changed fields only (personal
data); an override's carries before/after (itc-001 -- dates and mode are not personal data). Nothing here logs a value."""

from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Batch, Enrollment, ItStudentCounselor, ItStudentProfile, NotificationPreference, Program, User
from app.schemas import ItEnrollmentOverridePatch, ItStudentProfilePatch
from app.services.audit_changes import audit_change

STUDENTS_ONLY = "Only an IT student has this profile"
STAFF_ONLY = "Only the student's IT counselor or the IT Admin can see this profile"
STUDENT_NOT_FOUND = "Student not found"
ENROLLMENT_NOT_FOUND = "Enrolment not found"
END_BEFORE_START = "The end date cannot be before the start date"
UPDATED, DATES_UPDATED = "it.student_profile.update", "it.enrollment.dates_update"
FIELDS = tuple(ItStudentProfilePatch.model_fields)
OVERRIDES = tuple(ItEnrollmentOverridePatch.model_fields)


def require_student(user: User) -> User:
    if user.role != "it_student" or user.division != "it":
        raise HTTPException(403, STUDENTS_ONLY)
    return user


async def staff_student(db: AsyncSession, user: User, student_id: UUID, *, portal: str) -> User:
    """`portal` is the route's ("counselor" or "admin"): the IT counselor on theirs sees only linked students, the IT Admin on theirs any
    IT student. Another role is 403; a student outside the scope is the same 404 as a missing one (no disclosure)."""
    admin = portal == "admin"
    if (user.role, user.division) != ("it_admin" if admin else "counselor", "it"):
        raise HTTPException(403, STAFF_ONLY)
    stmt = select(User).where(User.id == student_id, User.role == "it_student")
    if not admin:
        stmt = stmt.join(ItStudentCounselor, ItStudentCounselor.student_user_id == User.id).where(ItStudentCounselor.counselor_user_id == user.id)
    student = await db.scalar(stmt)
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    return student


def _enrollment_out(enrollment: Enrollment, batch: Batch, program: Program) -> dict:
    return {
        "id": enrollment.id, "enrollment_code": enrollment.enrollment_code, "program": program.title, "batch": batch.name, "status": enrollment.status,
        "start_date": enrollment.start_date or batch.start_date, "end_date": enrollment.end_date or batch.end_date,
        "delivery_mode": enrollment.delivery_mode or batch.mode,
        "start_date_override": enrollment.start_date, "end_date_override": enrollment.end_date, "delivery_mode_override": enrollment.delivery_mode,
        "batch_start_date": batch.start_date, "batch_end_date": batch.end_date, "batch_mode": batch.mode,
    }  # fmt: skip


async def read(db: AsyncSession, student: User) -> dict:
    """The page's shape; an unsaved profile reads as empty (`exists: false`). Enrolments newest first, with effective values.
    `populate_existing`: after a save in the same session the rows still hold `func.now()` and pre-save values -- reload them."""
    profile = await db.get(ItStudentProfile, student.id, populate_existing=True)
    out = {field: getattr(profile, field, None) for field in FIELDS} | {"exists": profile is not None}
    author = await db.get(User, profile.updated_by_user_id) if profile and profile.updated_by_user_id else None
    out |= {"updated_at": profile.updated_at if profile else None, "updated_by_name": author.full_name if author else None}
    rows = (
        await db.execute(
            select(Enrollment, Batch, Program).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id)
            .where(Enrollment.student_id == student.id).order_by(Enrollment.created_at.desc(), Enrollment.id)
            .execution_options(populate_existing=True)
        )
    ).all()  # fmt: skip
    # itc-033 (DEC-SCOPE-357 C3): the student's own "phone calls" choice, read-only here (no row = allowed)
    calls_opt_out = await db.scalar(select(NotificationPreference.calls_opt_out).where(NotificationPreference.user_id == student.id))
    return {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "calls_allowed": not calls_opt_out},
        "profile": out,
        "enrollments": [_enrollment_out(*row) for row in rows],
    }


async def _lock(db: AsyncSession, student_id: UUID) -> None:
    await db.execute(select(User.id).where(User.id == student_id).with_for_update())


async def save(db: AsyncSession, actor: User, student: User, payload: ItStudentProfilePatch) -> dict:
    """Commits. Only the fields sent change; an unchanged save still records who saved last."""
    actor_id, actor_role, student_id = actor.id, actor.role, student.id
    await _lock(db, student_id)
    profile = await db.get(ItStudentProfile, student_id)
    if profile is None:
        profile = ItStudentProfile(student_user_id=student_id)
        db.add(profile)
    sent = payload.model_dump(exclude_unset=True)
    changed = sorted(field for field, value in sent.items() if getattr(profile, field) != value)
    for field, value in sent.items():
        setattr(profile, field, value)
    profile.updated_by_user_id = actor_id
    profile.updated_at = func.now()
    db.add(AuditLog(user_id=actor_id, action=UPDATED, entity_type="user", entity_id=str(student_id), metadata_json={"fields": changed, "role": actor_role}))
    await db.commit()
    return await read(db, student)


async def save_enrollment(db: AsyncSession, actor: User, student: User, enrollment_id: UUID, payload: ItEnrollmentOverridePatch) -> dict:
    """Commits. Only the overrides sent change (a null clears one). The effective end may not precede the effective start (422)."""
    await _lock(db, student.id)
    row = (await db.execute(select(Enrollment, Batch).join(Batch, Batch.id == Enrollment.batch_id).where(Enrollment.id == enrollment_id, Enrollment.student_id == student.id))).first()
    if row is None:
        raise HTTPException(404, ENROLLMENT_NOT_FOUND)
    enrollment, batch = row
    before = {field: getattr(enrollment, field) for field in OVERRIDES}
    after = before | payload.model_dump(exclude_unset=True)
    if (after["end_date"] or batch.end_date) < (after["start_date"] or batch.start_date):
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "end_date"), "msg": END_BEFORE_START, "input": str(after["end_date"] or batch.end_date)}])
    for field, value in after.items():
        setattr(enrollment, field, value)
    audit_change(db, actor, DATES_UPDATED, "enrollment", enrollment.id, before, after, metadata={"student_id": str(student.id)})
    await db.commit()
    return await read(db, student)
