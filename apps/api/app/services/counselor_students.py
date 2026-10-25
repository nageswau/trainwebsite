"""csc-001 (DEC-SCOPE-226, W3): the overseas students a counselor works with -- the students of the counselor's own applications plus
the students linked to the counselor (`OverseasStudentCounselor`). The picker (`GET /lookups/overseas-students`) and the write it feeds
(`POST /workflows/overseas/appointments`) share this, so the picker never offers a student the write refuses (ENH-031 §5).

csc-002 (DEC-SCOPE-227, W1-W3): an overseas counselor creates a walk-in student's login; the student is linked to that counselor and
gets the ENH-003 set-password link (delivered by the route after the commit). Functions only; nothing here commits except a refused
duplicate's audit row.

csc-003 (DEC-SCOPE-228, W6): while a walk-in account is pending (never activated), its counselor resends the link or fixes the name,
phone or email; an email change revokes the open link and the route mails a new one to the new address.

csc-005 (DEC-SCOPE-230, W3/W6): the Overseas Admin moves a student to another active overseas counselor -- AGN-023's rules (DEC-SCOPE-090)
for the student-level link."""

import logging
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import unique_student_code
from app.models import AuditLog, Notification, OverseasApplication, OverseasStudentCounselor, User, UserRoleAssignment
from app.notifications.dispatch import queue_deliveries
from app.schemas import CounselorStudentCreate
from app.services.agent_orgs import retry_after
from app.services.provisioning import IssuedWelcome, deliver_welcome_link, flush_unique_email, issue_welcome_token, provisioning_statuses, resend_wait_seconds, unusable_password_hash

logger = logging.getLogger("app.counselor_students")

OVERSEAS_COUNSELOR_ONLY = "Only an overseas counselor can add walk-in students"
STUDENT_NOT_FOUND = "Student not found"
ALREADY_ACTIVE = "This student has already set a password"
DEACTIVATED = "This account is deactivated"
# C2 / C5: the account emails a counselor may cause per rolling day -- creations, resends and email changes, refused duplicates included
# (AGN-002 QA-10) -- so the platform's mail cannot be used as a relay and existing addresses cannot be probed in bulk. Counted from audit
# rows (no new table). A name/phone edit sends nothing and is not counted.
MAIL_LIMIT = 20
MAIL_WINDOW = timedelta(hours=24)
CREATED, REJECTED = "counselor.student_create", "counselor.student_create_rejected"
RESENT, UPDATED, UPDATE_REJECTED = "counselor.student_resend", "counselor.student_update", "counselor.student_update_rejected"
EMAILED = "emailed"  # the outcome of an update that mailed a new link (an email change)
ADMIN_ONLY = "Only the Overseas Admin can assign a counselor"  # csc-005: AGN-023's wording and rule
CHOOSE_ACTIVE_COUNSELOR = "Choose an active overseas counselor"
ASSIGNED = "overseas.student.counselor_assign"
REASON_REQUIRED = "Give a reason for the reassignment"  # ccrm-033 (DEC-SCOPE-268 RR1)


def require_reason(previous_id, reason: str | None) -> None:
    """ccrm-033 RR1: replacing an existing counselor needs a reason; a first assignment does not."""
    if previous_id is not None and not reason:
        raise HTTPException(422, REASON_REQUIRED)


def with_reason(body: str, reason: str | None) -> str:
    return f"{body} Reason: {reason}" if reason else body


def reason_meta(reason: str | None) -> dict:
    """The audit metadata's `reason`, only when one was given (rows without one keep their pre-ccrm-033 shape)."""
    return {"reason": reason} if reason else {}


def visible_student_ids(counselor: User):
    """A subquery of student user ids, for `User.id.in_(...)`. A bridged application's NULL `student_id` matches nothing there."""
    return union(
        select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == counselor.id),
        select(OverseasStudentCounselor.student_user_id).where(OverseasStudentCounselor.counselor_user_id == counselor.id),
    )


async def is_visible_student(db: AsyncSession, counselor: User, student_id: UUID) -> bool:
    return bool(await db.scalar(select(exists().where(User.id == student_id, User.id.in_(visible_student_ids(counselor))))))


def require_overseas_counselor(user: User, message: str = OVERSEAS_COUNSELOR_ONLY) -> None:
    if user.role != "counselor" or user.division != "overseas":  # W1: an IT counselor works leads only (tel-017)
        raise HTTPException(403, message)


def student_out(student: User, setup: str | None) -> dict:
    return {"id": student.id, "full_name": student.full_name, "email": student.email, "phone": student.phone, "student_code": student.student_code, "setup": setup}


async def _enforce_budget(db: AsyncSession, counselor_id: UUID) -> None:
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(
                AuditLog.user_id == counselor_id,
                or_(AuditLog.action.in_((CREATED, REJECTED, RESENT, UPDATE_REJECTED)), and_(AuditLog.action == UPDATED, AuditLog.outcome == EMAILED)),
                AuditLog.created_at > now - MAIL_WINDOW,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(MAIL_LIMIT)
        )
    ).all()
    wait = retry_after(recent, MAIL_LIMIT, now, MAIL_WINDOW)
    if wait:
        logger.warning("counselor_student_mail_throttled", extra={"extra_fields": {"actor_id": str(counselor_id), "wait_seconds": wait}})
        raise HTTPException(429, f"You have sent {MAIL_LIMIT} account emails in the last 24 hours. Try again later.", headers={"Retry-After": str(wait)})


async def _reject_existing_email(db: AsyncSession, counselor_id: UUID, action: str = REJECTED) -> NoReturn:
    """Audited and committed before the 409 (the raised request would roll it back), so it counts toward the budget. The address itself
    is never recorded."""
    db.add(AuditLog(user_id=counselor_id, action=action, entity_type="user", entity_id=str(counselor_id), outcome="rejected", metadata_json={"reason": "email_exists"}))
    await db.commit()
    logger.info("counselor_student_email_rejected", extra={"extra_fields": {"actor_id": str(counselor_id), "action": action, "reason": "email_exists"}})
    raise HTTPException(409, "Email already exists")


async def _lock_counselor(db: AsyncSession, counselor_id: UUID) -> None:
    """One counselor's account changes run one at a time, so the budget holds under concurrency (lock order: counselor -> student ->
    tokens, as the ENH-003 Re-send)."""
    await db.execute(select(User.id).where(User.id == counselor_id).with_for_update())


async def create_student(db: AsyncSession, counselor: User, payload: CounselorStudentCreate, *, registration_source: str = "counselor_walk_in") -> tuple[User, IssuedWelcome]:
    """No commit (ccrm-008's lead conversion passes `lead_conversion`). The counselor's own row is locked first, so one counselor's creates run one at a time and the budget holds under
    concurrency (lock order: counselor -> new user -> tokens, as ENH-003 Re-send)."""
    counselor_id = counselor.id  # a plain value: a rollback below expires the ORM objects
    await _lock_counselor(db, counselor_id)
    await _enforce_budget(db, counselor_id)
    if await db.scalar(select(User.id).where(User.email == payload.email)):
        await _reject_existing_email(db, counselor_id)
    student = User(
        email=payload.email, password_hash=unusable_password_hash(), full_name=payload.full_name, role="overseas_student", division="overseas",
        phone=payload.phone, active=True, email_verified=False, student_code=await unique_student_code(db, User.student_code),
        profile={"registration_source": registration_source},
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


async def deliver_link(student: User, issued: IssuedWelcome, counselor: User) -> dict:
    """After the commit. AGN-001/002 S3: only an admin may see the link token, so a counselor never can."""
    delivery = await deliver_welcome_link(user=student, issued=issued, issued_by=counselor)
    delivery.pop("development_welcome_token", None)
    return delivery


async def _locked_pending_student(db: AsyncSession, counselor_id: UUID, student_id: UUID) -> tuple[User, str]:
    """The caller's own linked student, row-locked, still pending (never activated) and not deactivated; with its set-up status.
    Anything that is not the caller's linked student is the same 404 (no disclosure)."""
    linked = await db.scalar(select(OverseasStudentCounselor.id).where(OverseasStudentCounselor.student_user_id == student_id, OverseasStudentCounselor.counselor_user_id == counselor_id))
    student = await db.scalar(select(User).where(User.id == student_id).with_for_update().execution_options(populate_existing=True)) if linked else None
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    setup = (await provisioning_statuses(db, [student.id])).get(student.id)
    if setup is None:
        raise HTTPException(409, ALREADY_ACTIVE)
    if not student.active:
        raise HTTPException(409, DEACTIVATED)
    return student, setup


async def resend_link(db: AsyncSession, counselor: User, student_id: UUID) -> tuple[User, IssuedWelcome]:
    """No commit. The ENH-003 Re-send rules (per-account cooldown; the open link is superseded) plus the counselor's mail budget."""
    counselor_id = counselor.id
    await _lock_counselor(db, counselor_id)
    student, _ = await _locked_pending_student(db, counselor_id, student_id)
    wait = await resend_wait_seconds(db, student.id)
    if wait:
        logger.warning("counselor_student_resend_throttled", extra={"extra_fields": {"actor_id": str(counselor_id), "student_id": str(student.id), "wait_seconds": wait}})
        raise HTTPException(429, f"A link was just sent; wait {wait} seconds before re-sending", headers={"Retry-After": str(wait)})
    await _enforce_budget(db, counselor_id)
    issued = await issue_welcome_token(db, user=student, issued_by=counselor)
    db.add(AuditLog(user_id=counselor_id, action=RESENT, entity_type="user", entity_id=str(student.id), outcome=EMAILED, metadata_json={"token_id": str(issued.token_id)}))
    return student, issued


async def update_student(db: AsyncSession, counselor: User, student_id: UUID, changes: dict) -> tuple[User, str, IssuedWelcome | None]:
    """No commit. Only the fields that actually change are written; an email change revokes the open link and issues a new one (mailed
    by the route after the commit). Returns the student, its set-up status and the new link, if any."""
    counselor_id = counselor.id
    await _lock_counselor(db, counselor_id)
    student, setup = await _locked_pending_student(db, counselor_id, student_id)
    changes = {field: value for field, value in changes.items() if getattr(student, field) != value}
    if not changes:
        return student, setup, None
    if "email" in changes:
        await _enforce_budget(db, counselor_id)
        if await db.scalar(select(User.id).where(User.email == changes["email"])):
            await _reject_existing_email(db, counselor_id, UPDATE_REJECTED)
    for field, value in changes.items():
        setattr(student, field, value)
    issued = None
    if "email" in changes:
        try:
            await flush_unique_email(db)  # another request took the address since the check: rolled back, then the same audited 409
        except HTTPException:
            await _reject_existing_email(db, counselor_id, UPDATE_REJECTED)
        issued = await issue_welcome_token(db, user=student, issued_by=counselor)
        setup = "pending_setup"
    db.add(AuditLog(user_id=counselor_id, action=UPDATED, entity_type="user", entity_id=str(student.id), outcome=EMAILED if issued else "updated", metadata_json={"fields": sorted(changes)}))
    return student, setup, issued


async def _notify(db: AsyncSession, recipient: User, title: str, body: str) -> None:
    """In-app row plus queued deliveries (ENH-014), sent after the commit -- as AGN-023's assignment notices."""
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url="/overseas/counselor/students")
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, recipient)


async def assign_counselor(db: AsyncSession, admin: User, student_id: UUID, counselor_id: UUID, reason: str | None = None) -> dict:
    """No commit. AGN-023 (H2, H8): the Overseas Admin only; swap only (a counselor is required); the same counselor changes nothing. A
    student with no link yet gets one (C14). The student row is locked so two reassignments serialise. ccrm-033: a swap needs a reason,
    kept in the audit row (the student 360 History shows it) and sent to both counselors."""
    if admin.role != "overseas_admin" or admin.division != "overseas":  # C13: not super_admin, as AGN-023
        raise HTTPException(403, ADMIN_ONLY)
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "overseas_student").with_for_update())
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    counselor = await db.get(User, counselor_id)
    if counselor is None or counselor.role != "counselor" or counselor.division != "overseas" or not counselor.active:
        raise HTTPException(422, CHOOSE_ACTIVE_COUNSELOR)
    result = {"id": student.id, "counselor_id": counselor.id, "counselor_name": counselor.full_name}
    row = await db.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id))
    if row is not None and row.counselor_user_id == counselor.id:
        return {**result, "changed": False}
    previous_id = row.counselor_user_id if row else None
    require_reason(previous_id, reason)
    if row is None:
        db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    else:
        row.counselor_user_id, row.assigned_by_user_id = counselor.id, admin.id
    db.add(AuditLog(user_id=admin.id, action=ASSIGNED, entity_type="user", entity_id=str(student.id),
                    metadata_json={"from_counselor_id": str(previous_id) if previous_id else None, "to_counselor_id": str(counselor.id), **reason_meta(reason)}))  # fmt: skip
    await _notify(db, counselor, "Student assigned to you", with_reason(f"{student.full_name} is now one of your students.", reason))
    previous = await db.get(User, previous_id) if previous_id else None
    if previous is not None and previous.active:
        await _notify(db, previous, "Student reassigned", with_reason("A student has moved to another counselor.", reason))
    return {**result, "changed": True}


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
