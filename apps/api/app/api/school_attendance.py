"""ENH-030 -- daily class attendance for School students (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md).

A teacher marks their assigned students for one day in one call (DEC-SCOPE-038 D1/D2). Its own router, like ENH-005/011/013's, so
`schools.py` does not grow; `schools._overview_payload` reads `daily_attendance_summary` through a call-time import.
"""

from collections import Counter
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _own_school_id, _scoped_students_query, _today_ist, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import ATTENDANCE_STATUSES, AuditLog, SchoolAttendanceRecord, SchoolStudent, User
from app.schemas import SchoolAttendanceIn, SchoolAttendanceRosterOut

router = APIRouter(prefix="/school", tags=["school-attendance"])
logger = get_logger("app.school.attendance")

TEACHER_REQUIRED = "Teacher role required"
FUTURE_DATE = "Attendance cannot be marked for a future date"
NOT_ASSIGNED = "One or more students are not assigned to you"
MARK_ACTION = "school.daily_attendance_mark"
RECENT_LIMIT = 30  # C3: the read summary covers the 30 most recent marked days


def _require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "school_teacher":
        raise HTTPException(403, TEACHER_REQUIRED)
    return user


def _check_date(day: date) -> None:
    if day > _today_ist():
        raise HTTPException(422, FUTURE_DATE)


async def _roster(db: AsyncSession, user: User, school_id: UUID, day: date) -> dict:
    """The teacher's assigned students (the existing SCH-001-AC03 scope) with that day's status at this school, or None (not marked)."""
    scoped = await _scoped_students_query(db, user, school_id)
    students = (await db.scalars(scoped.order_by(SchoolStudent.grade_or_class, SchoolStudent.full_name, SchoolStudent.id))).all()
    marks: dict[UUID, str] = {}
    if students:
        rows = await db.execute(
            select(SchoolAttendanceRecord.school_student_id, SchoolAttendanceRecord.status).where(
                SchoolAttendanceRecord.school_student_id.in_([s.id for s in students]),
                SchoolAttendanceRecord.session_date == day,
                SchoolAttendanceRecord.school_id == school_id,
            )
        )
        marks = dict(rows.all())
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
    """Spec §5.2. One transaction: lock the listed students FOR SHARE (a transfer approval or reassignment takes them FOR UPDATE, so
    it waits for this write, or this waits for it and sees the result), re-check scope under the lock, tier gate, upsert, audit,
    commit. Any failure before the commit leaves nothing written. Records are sorted by student id, so every save locks and
    inserts in one order and two overlapping saves cannot deadlock (spec §11 A3). Unlisted students are untouched; a retry of the
    same body is harmless."""
    school_id = _own_school_id(user)
    _check_date(payload.session_date)
    records = sorted(payload.records, key=lambda r: r.student_id)
    ids = [r.student_id for r in records]
    locked = (
        await db.scalars(
            select(SchoolStudent).where(SchoolStudent.id.in_(ids)).order_by(SchoolStudent.id).with_for_update(read=True).execution_options(populate_existing=True)
        )
    ).all()
    if len(locked) != len(ids) or any(s.school_id != school_id or s.assigned_teacher_user_id != user.id for s in locked):
        raise HTTPException(403, NOT_ASSIGNED)
    # ENH-022: after scope, before any write -- a denial commits only its own audit row.
    await require_school_entitlement(db, user, school_id, None)
    before = dict(
        (
            await db.execute(
                select(SchoolAttendanceRecord.school_student_id, SchoolAttendanceRecord.status).where(
                    SchoolAttendanceRecord.school_student_id.in_(ids), SchoolAttendanceRecord.session_date == payload.session_date
                )
            )
        ).all()
    )
    # Spec §11 S5: the audit names who changed, from what, to what -- only rows whose status actually changed.
    changes = [{"student_id": str(r.student_id), "from": before.get(r.student_id), "to": r.status} for r in records if before.get(r.student_id) != r.status]
    stmt = pg_insert(SchoolAttendanceRecord).values(
        [
            {"id": uuid4(), "school_student_id": r.student_id, "school_id": school_id, "session_date": payload.session_date, "status": r.status, "marked_by_user_id": user.id}
            for r in records
        ]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_school_attendance_student_date",
            set_={"status": stmt.excluded.status, "school_id": stmt.excluded.school_id, "marked_by_user_id": stmt.excluded.marked_by_user_id, "updated_at": func.now()},
        )
    )
    tally = Counter(r.status for r in records)
    statuses = {s: tally[s] for s in ATTENDANCE_STATUSES if tally[s]}
    metadata = {"session_date": payload.session_date.isoformat(), "count": len(records), "statuses": statuses, "changes": changes}
    db.add(AuditLog(user_id=user.id, action=MARK_ACTION, entity_type="school", entity_id=str(school_id), metadata_json=metadata))
    await db.commit()
    logger.info("school_attendance_marked", extra={"extra_fields": {"actor_id": str(user.id), "school_id": str(school_id), "session_date": payload.session_date.isoformat(), "count": len(records), "changed": len(changes)}})
    return await _roster(db, user, school_id, payload.session_date)
