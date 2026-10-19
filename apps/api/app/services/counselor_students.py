"""csc-001 (DEC-SCOPE-226, W3): the overseas students a counselor works with -- the students of the counselor's own applications plus
the students linked to the counselor (`OverseasStudentCounselor`). The picker (`GET /lookups/overseas-students`) and the write it feeds
(`POST /workflows/overseas/appointments`) share this, so the picker never offers a student the write refuses (ENH-031 §5).

csc-002 (DEC-SCOPE-227, W1-W3): an overseas counselor creates a walk-in student's login; the student is linked to that counselor and
gets the ENH-003 set-password link (delivered by the route after the commit). Functions only; nothing here commits except a refused
duplicate's audit row."""

import logging
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import unique_student_code
from app.models import AuditLog, OverseasApplication, OverseasStudentCounselor, User, UserRoleAssignment
from app.schemas import CounselorStudentCreate
from app.services.agent_orgs import retry_after
from app.services.provisioning import IssuedWelcome, flush_unique_email, issue_welcome_token, provisioning_statuses, unusable_password_hash

logger = logging.getLogger("app.counselor_students")

OVERSEAS_COUNSELOR_ONLY = "Only an overseas counselor can add walk-in students"
# C2: a counselor's creations per rolling day, refused duplicates included (AGN-002 QA-10), so the platform's mail cannot be used as a
# relay and existing addresses cannot be probed in bulk. Counted from audit rows (no new table).
CREATE_LIMIT = 20
CREATE_WINDOW = timedelta(hours=24)
CREATED, REJECTED = "counselor.student_create", "counselor.student_create_rejected"


def visible_student_ids(counselor: User):
    """A subquery of student user ids, for `User.id.in_(...)`. A bridged application's NULL `student_id` matches nothing there."""
    return union(
        select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == counselor.id),
        select(OverseasStudentCounselor.student_user_id).where(OverseasStudentCounselor.counselor_user_id == counselor.id),
    )


async def is_visible_student(db: AsyncSession, counselor: User, student_id: UUID) -> bool:
    return bool(await db.scalar(select(exists().where(User.id == student_id, User.id.in_(visible_student_ids(counselor))))))


def require_overseas_counselor(user: User) -> None:
    if user.role != "counselor" or user.division != "overseas":  # W1: an IT counselor works leads only (tel-017)
        raise HTTPException(403, OVERSEAS_COUNSELOR_ONLY)


def student_out(student: User, setup: str | None) -> dict:
    return {"id": student.id, "full_name": student.full_name, "email": student.email, "phone": student.phone, "student_code": student.student_code, "setup": setup}


async def _enforce_budget(db: AsyncSession, counselor_id: UUID) -> None:
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == counselor_id, AuditLog.action.in_((CREATED, REJECTED)), AuditLog.created_at > now - CREATE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(CREATE_LIMIT)
        )
    ).all()
    wait = retry_after(recent, CREATE_LIMIT, now, CREATE_WINDOW)
    if wait:
        logger.warning("counselor_student_create_throttled", extra={"extra_fields": {"actor_id": str(counselor_id), "wait_seconds": wait}})
        raise HTTPException(429, f"You have added {CREATE_LIMIT} students in the last 24 hours. Try again later.", headers={"Retry-After": str(wait)})


async def _reject_existing_email(db: AsyncSession, counselor_id: UUID) -> NoReturn:
    """Audited and committed before the 409 (the raised request would roll it back), so it counts toward the budget. The address itself
    is never recorded."""
    db.add(AuditLog(user_id=counselor_id, action=REJECTED, entity_type="user", entity_id=str(counselor_id), outcome="rejected", metadata_json={"reason": "email_exists"}))
    await db.commit()
    logger.info("counselor_student_create_rejected", extra={"extra_fields": {"actor_id": str(counselor_id), "reason": "email_exists"}})
    raise HTTPException(409, "Email already exists")


async def create_student(db: AsyncSession, counselor: User, payload: CounselorStudentCreate) -> tuple[User, IssuedWelcome]:
    """No commit. The counselor's own row is locked first, so one counselor's creates run one at a time and the budget holds under
    concurrency (lock order: counselor -> new user -> tokens, as ENH-003 Re-send)."""
    counselor_id = counselor.id  # a plain value: a rollback below expires the ORM objects
    await db.execute(select(User.id).where(User.id == counselor_id).with_for_update())
    await _enforce_budget(db, counselor_id)
    if await db.scalar(select(User.id).where(User.email == payload.email)):
        await _reject_existing_email(db, counselor_id)
    student = User(
        email=payload.email, password_hash=unusable_password_hash(), full_name=payload.full_name, role="overseas_student", division="overseas",
        phone=payload.phone, active=True, email_verified=False, student_code=await unique_student_code(db, User.student_code),
        profile={"registration_source": "counselor_walk_in"},
    )  # fmt: skip
    db.add(student)
    try:
        await flush_unique_email(db)  # another request took the address since the check: rolled back, then the same audited 409
    except HTTPException:
        await _reject_existing_email(db, counselor_id)
    db.add(UserRoleAssignment(user_id=student.id, division="overseas", role="overseas_student", is_active=True, assigned_by_user_id=counselor_id, approval_status="approved"))
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor_id, assigned_by_user_id=counselor_id))
    issued = await issue_welcome_token(db, user=student, issued_by=counselor)
    db.add(AuditLog(user_id=counselor_id, action=CREATED, entity_type="user", entity_id=str(student.id), outcome="created", metadata_json={"student_code": student.student_code}))
    return student, issued


async def page(db: AsyncSession, counselor: User, limit: int, offset: int) -> dict:
    """The counselor's linked students, newest link first, with ENH-003's set-up status (`None` once the student has a password)."""
    mine = OverseasStudentCounselor.counselor_user_id == counselor.id
    total = await db.scalar(select(func.count()).select_from(OverseasStudentCounselor).where(mine))
    students = (
        await db.scalars(
            select(User)
            .join(OverseasStudentCounselor, OverseasStudentCounselor.student_user_id == User.id)
            .where(mine)
            .order_by(OverseasStudentCounselor.created_at.desc(), OverseasStudentCounselor.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    statuses = await provisioning_statuses(db, [s.id for s in students])
    return {"items": [student_out(s, statuses.get(s.id)) for s in students], "total": total or 0, "limit": limit, "offset": offset}
