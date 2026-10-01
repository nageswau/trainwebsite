"""ENH-030 -- daily class attendance for School students (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md).

A teacher marks their assigned students for one day in one call (DEC-SCOPE-041 D1/D2). Its own router, like ENH-005/011/013's, so
`schools.py` does not grow; `schools._overview_payload` reads `daily_attendance_summary` through a call-time import.
"""

from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import TIER_TIMEZONE, _own_school_id, _scoped_students_query, _today_ist, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import ATTENDANCE_STATUSES, AuditLog, SchoolAttendanceRecord, SchoolStudent, SchoolStudentTransferRequest, User
from app.schemas import SchoolAttendanceIn, SchoolAttendanceRosterOut

router = APIRouter(prefix="/school", tags=["school-attendance"])
logger = get_logger("app.school.attendance")

TEACHER_REQUIRED = "Teacher role required"
FUTURE_DATE = "Attendance cannot be marked for a future date"
NOT_ASSIGNED = "One or more students are not assigned to you"
BUSY = "This class's attendance is being changed elsewhere. Try again."
NOT_ENROLLED = "One or more students were not enrolled at your school on"  # + the day (review I-3)
MARK_ACTION = "school.daily_attendance_mark"
DENIED_ACTION = "school.daily_attendance_denied"
ATTENDANCE_LOCK_TIMEOUT = "5s"  # bounded wait for the student row locks (ENH-004/005 value); a bound parameter, never request input
RECENT_LIMIT = 30  # C3: the read summary covers the 30 most recent marked days


def _require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "school_teacher":
        raise HTTPException(403, TEACHER_REQUIRED)
    return user


def _check_date(day: date) -> None:
    if day > _today_ist():
        raise HTTPException(422, FUTURE_DATE)


async def _enrolled_on(db: AsyncSession, school_id: UUID, students: Sequence[tuple[UUID, datetime]]) -> dict[UUID, date]:
    """Review I-3 (DEC-SCOPE-041, user-approved 2026-09-30): the school-calendar day each student's time at `school_id` began -- the
    latest approved transfer into it, else when the student was created there. A day before that is not theirs to be marked for."""
    ids = [student_id for student_id, _created in students]
    moved: dict[UUID, datetime | None] = {}
    if ids:
        rows = await db.execute(
            select(SchoolStudentTransferRequest.school_student_id, func.max(SchoolStudentTransferRequest.decided_at))
            .where(SchoolStudentTransferRequest.school_student_id.in_(ids), SchoolStudentTransferRequest.to_school_id == school_id, SchoolStudentTransferRequest.status == "approved")
            .group_by(SchoolStudentTransferRequest.school_student_id)
        )
        moved = dict(rows.all())
    return {student_id: (moved.get(student_id) or created).astimezone(TIER_TIMEZONE).date() for student_id, created in students}


async def _statuses_on(db: AsyncSession, school_id: UUID, day: date, student_ids: Sequence[UUID]) -> dict[UUID, str]:
    """Each listed student's status on `day` in this school's register (C1); a student with no row is absent from the result."""
    rows = await db.execute(
        select(SchoolAttendanceRecord.school_student_id, SchoolAttendanceRecord.status).where(
            SchoolAttendanceRecord.school_student_id.in_(student_ids),
            SchoolAttendanceRecord.school_id == school_id,
            SchoolAttendanceRecord.session_date == day,
        )
    )
    return dict(rows.all())


async def _roster(db: AsyncSession, user: User, school_id: UUID, day: date) -> dict:
    """The teacher's assigned students (the existing SCH-001-AC03 scope) who were enrolled at this school on `day` (review I-3), with
    that day's status at this school, or None (not marked)."""
    scoped = await _scoped_students_query(db, user, school_id)
    students = (await db.scalars(scoped.order_by(SchoolStudent.grade_or_class, SchoolStudent.full_name, SchoolStudent.id))).all()
    enrolled = await _enrolled_on(db, school_id, [(s.id, s.created_at) for s in students])
    students = [s for s in students if enrolled[s.id] <= day]
    marks = await _statuses_on(db, school_id, day, [s.id for s in students]) if students else {}
    return {
        "session_date": day,
        "today": _today_ist(),
        "students": [{"id": s.id, "full_name": s.full_name, "grade_or_class": s.grade_or_class, "status": marks.get(s.id)} for s in students],
    }


@router.get("/attendance", response_model=SchoolAttendanceRosterOut)
async def attendance_roster(day: date | None = Query(None, alias="date"), user: User = Depends(_require_teacher), db: AsyncSession = Depends(get_db)):
    """Spec §5.1. Pure read: no database write."""
    school_id = _own_school_id(user)
    day = day or _today_ist()
    _check_date(day)
    body = await _roster(db, user, school_id, day)
    logger.info("school_attendance_roster_read", extra={"extra_fields": {"actor_id": str(user.id), "session_date": day.isoformat(), "count": len(body["students"])}})
    return body


@router.put("/attendance", response_model=SchoolAttendanceRosterOut)
async def mark_daily_attendance(payload: SchoolAttendanceIn, user: User = Depends(_require_teacher), db: AsyncSession = Depends(get_db)):
    """Spec §5.2. One transaction: lock the listed students FOR SHARE with the teacher's scope inside the locking query (a transfer
    approval or reassignment takes the row FOR UPDATE, so one waits for the other and this one then sees the result; a wait past
    ATTENDANCE_LOCK_TIMEOUT is a 409), refuse and audit if any listed student is outside the scope, tier gate, upsert, audit, commit.
    Any failure before the commit leaves no mark written. Records are sorted by student id, so every save locks and inserts in one
    order and two overlapping saves cannot deadlock (spec §11 A3). Unlisted students are untouched; a retry of the same body is
    harmless."""
    school_id = _own_school_id(user)
    _check_date(payload.session_date)
    records = sorted(payload.records, key=lambda r: r.student_id)
    ids = [r.student_id for r in records]
    actor = {"actor_id": str(user.id), "school_id": str(school_id), "session_date": payload.session_date.isoformat()}
    # `set_config(..., true)` is SET LOCAL with a bound parameter, so no SQL is built from a string (the ENH-004/005 pattern).
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": ATTENDANCE_LOCK_TIMEOUT})
    # The scope filter is part of the locking query, so a student this teacher does not teach is never locked or waited on (no lock
    # griefing); unknown, unassigned and other-school ids are the same absence, so the 403 cannot be used to probe ids.
    try:
        locked = (
            await db.execute(
                select(SchoolStudent.id, SchoolStudent.created_at)
                .where(SchoolStudent.id.in_(ids), SchoolStudent.school_id == school_id, SchoolStudent.assigned_teacher_user_id == user.id)
                .order_by(SchoolStudent.id)
                .with_for_update(read=True)
            )
        ).all()
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "55P03":  # lock_not_available: a transfer/reassignment held a row past the bound
            logger.warning("school_attendance_lock_timeout", extra={"extra_fields": {**actor, "requested": len(ids), "lock_timeout": ATTENDANCE_LOCK_TIMEOUT}})
            raise HTTPException(409, BUSY) from exc
        raise
    if len(locked) != len(ids):
        # A security-relevant event (probing, or a stale roster after a reassignment): record it with counts only, then refuse.
        outside = len(ids) - len(locked)
        db.add(
            AuditLog(
                user_id=user.id,
                action=DENIED_ACTION,
                entity_type="school",
                entity_id=str(school_id),
                outcome="denied",
                metadata_json={"session_date": actor["session_date"], "requested": len(ids), "outside": outside},
            )
        )
        await db.commit()
        logger.warning("school_attendance_denied", extra={"extra_fields": {**actor, "requested": len(ids), "outside": outside}})
        raise HTTPException(403, NOT_ASSIGNED)
    # Review I-3: a past day may only be marked for students enrolled at this school on it (read under the same lock, so a transfer
    # approved meanwhile is seen). Nothing has been written yet.
    enrolled = await _enrolled_on(db, school_id, [(row.id, row.created_at) for row in locked])
    not_yet = sum(1 for day in enrolled.values() if day > payload.session_date)
    if not_yet:
        logger.info("school_attendance_not_enrolled", extra={"extra_fields": {**actor, "requested": len(ids), "not_enrolled": not_yet}})
        raise HTTPException(422, f"{NOT_ENROLLED} {payload.session_date.strftime('%d %b %Y')}")
    # ENH-022: after scope, before any write -- a denial commits only its own audit row.
    await require_school_entitlement(db, user, school_id, None)
    before = await _statuses_on(db, school_id, payload.session_date, ids)
    # Spec §11 S5: the audit names who changed, from what, to what -- only rows whose status actually changed.
    changes = [{"student_id": str(r.student_id), "from": before.get(r.student_id), "to": r.status} for r in records if before.get(r.student_id) != r.status]
    stmt = pg_insert(SchoolAttendanceRecord).values(
        [{"id": uuid4(), "school_student_id": r.student_id, "school_id": school_id, "session_date": payload.session_date, "status": r.status, "marked_by_user_id": user.id} for r in records]
    )
    tally: Counter[str] = Counter(r.status for r in records)
    statuses = {s: tally[s] for s in ATTENDANCE_STATUSES if tally[s]}
    metadata = {"session_date": actor["session_date"], "count": len(records), "statuses": statuses, "changes": changes}
    # The marks and their audit row commit together or not at all; a failure is rolled back, logged (ids and counts only), re-raised.
    try:
        await db.execute(
            stmt.on_conflict_do_update(
                # School is part of the key: a previous school's row for the same day is never overwritten (C1/AC10).
                constraint="uq_school_attendance_student_school_date",
                set_={"status": stmt.excluded.status, "marked_by_user_id": stmt.excluded.marked_by_user_id, "updated_at": func.now()},
            )
        )
        db.add(AuditLog(user_id=user.id, action=MARK_ACTION, entity_type="school", entity_id=str(school_id), metadata_json=metadata))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        # Spec §11 S6: no traceback -- the DB error text carries the bound parameters (student ids and their statuses).
        failure = {"error": type(exc).__name__, "sqlstate": getattr(getattr(exc, "orig", None), "sqlstate", None)}
        logger.error("school_attendance_mark_failed", extra={"extra_fields": {**actor, "count": len(records), **failure}})
        raise
    logger.info("school_attendance_marked", extra={"extra_fields": {**actor, "count": len(records), "changed": len(changes)}})
    return await _roster(db, user, school_id, payload.session_date)


async def daily_attendance_summary(db: AsyncSession, student: SchoolStudent) -> dict:
    """Spec §5.3 / C1 / C3: the student's 30 most recent records at their CURRENT school, newest first, with per-status counts over
    those same records. No scope check here: callers (`_overview_payload`) have already applied the reader's own."""
    rows = (
        await db.execute(
            select(SchoolAttendanceRecord.session_date, SchoolAttendanceRecord.status)
            .where(SchoolAttendanceRecord.school_student_id == student.id, SchoolAttendanceRecord.school_id == student.school_id)
            .order_by(SchoolAttendanceRecord.session_date.desc())
            .limit(RECENT_LIMIT)
        )
    ).all()
    counts = Counter(status for _day, status in rows)
    return {"counts": {s: counts[s] for s in ATTENDANCE_STATUSES}, "recent": [{"session_date": day, "status": status} for day, status in rows]}
