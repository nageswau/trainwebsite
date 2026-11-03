"""itc-023 (DEC-SCOPE-352; backlog §itc-023, source §6/§9): at-risk thresholds per programme, the daily flag sweep and the scoped reads.

- Thresholds (R1): `it_risk_thresholds`, one row per programme; NULL turns a criterion off and a programme with none on is not monitored.
- Criteria (R3), per ACTIVE enrolment of a monitored programme's batch: attendance % (`training_progress` attended/counted, so itc-021's
  leave policy applies) below the minimum once `min_sessions` sessions count; the mean best-attempt assessment % below the minimum; the
  trailing run of `absent` marks at or above the limit.
- Transitions (R5): a raise inserts a flag and alerts; a recovery closes it and alerts; a change of reasons while flagged is silent; a
  flag whose enrolment or programme left monitoring is closed silently ('stopped'). Each change and its notices share one savepoint, so a
  failure sends nothing, and the partial unique index / the conditional UPDATE make an overlapping run a no-op (AC2: once per transition).
- Alerts (R6) use itc-002's fixed, preview-safe events: the student `it.training.check_in`, the trainer and the itc-003 counselor
  `it.training.at_risk`, all three `it.training.back_on_track`. Logs carry counts and ids only.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance, Batch, Enrollment, ItRiskThreshold, ItStudentCounselor, Program, StudentRiskFlag, User
from app.notifications.events import notify
from app.schemas import ItRiskThresholdIn
from app.services import it_lifecycle, training_progress
from app.services.audit_changes import audit_change

logger = logging.getLogger(__name__)

CRITERIA = ("min_attendance_percent", "min_assessment_percent", "max_consecutive_absences")
FIELDS = (*CRITERIA, "min_sessions")
READERS_ONLY = "Only IT staff can see at-risk students"
ADMINS_ONLY = "Only the IT Admin can change at-risk thresholds"
PROGRAM_NOT_FOUND = "Programme not found"
LIST_LIMIT = 200


# --- thresholds ----------------------------------------------------------------------------------------------------------------------
def require_admin(user: User) -> None:
    if (user.role, user.division) != ("it_admin", "it"):
        raise HTTPException(403, ADMINS_ONLY)


def _threshold_out(program: Program, row: ItRiskThreshold | None) -> dict:
    values = {field: getattr(row, field) for field in FIELDS} if row else ItRiskThresholdIn().model_dump()  # no row = the defaults (all off)
    return {"program_id": program.id, "program": program.title, "active": program.active, **values,
            "monitored": any(values[c] is not None for c in CRITERIA), "updated_at": row.updated_at if row else None}  # fmt: skip


async def list_thresholds(db: AsyncSession) -> list[dict]:
    rows = await db.execute(select(Program, ItRiskThreshold).outerjoin(ItRiskThreshold, ItRiskThreshold.program_id == Program.id).order_by(Program.title, Program.id))
    return [_threshold_out(program, row) for program, row in rows.all()]


async def save_threshold(db: AsyncSession, user: User, program_id: UUID, payload: ItRiskThresholdIn) -> dict:
    """Locks the programme's row (two saves serialise; last write wins) and audits before/after (itc-001)."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(404, PROGRAM_NOT_FOUND)
    row = await db.get(ItRiskThreshold, program_id, with_for_update=True)
    before = {field: getattr(row, field) for field in FIELDS} if row else {}
    if row is None:
        row = ItRiskThreshold(program_id=program_id)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.updated_by_id = user.id
    audit_change(db, user, "it.risk_thresholds.update", "program", program_id, before, payload.model_dump())
    await db.commit()
    await db.refresh(row)
    return _threshold_out(program, row)


# --- the sweep -----------------------------------------------------------------------------------------------------------------------
def _trailing_absences(rows) -> dict[UUID, int]:
    """(student_id, status) newest first -> the length of each student's leading run of 'absent'."""
    runs: dict[UUID, int] = {}
    ended: set[UUID] = set()
    for student_id, status in rows:
        if student_id in ended:
            continue
        if status == "absent":
            runs[student_id] = runs.get(student_id, 0) + 1
        else:
            ended.add(student_id)
    return runs


async def _evaluate(db: AsyncSession, batch_id: UUID, th: dict) -> dict[UUID, dict]:
    """Every active enrolment of the batch -> {student_id, reasons, figures}: four queries per batch whatever its size."""
    seats = (await db.execute(select(Enrollment.id, Enrollment.student_id).where(Enrollment.batch_id == batch_id, Enrollment.status == "active"))).all()
    if not seats:
        return {}
    att = training_progress.attendance(batch_id=batch_id)
    attendance = {sid: (counted, pct) for sid, counted, pct in await db.execute(select(att.c.student_id, att.c.counted, training_progress.percent(att.c.attended, att.c.counted)))}
    avg = training_progress.assessment_average(batch_id)
    averages = dict((await db.execute(select(avg.c.student_id, avg.c.average))).all())
    marks = await db.execute(select(Attendance.student_id, Attendance.status).where(Attendance.batch_id == batch_id).order_by(Attendance.student_id, Attendance.session_date.desc()))
    runs = _trailing_absences(marks.all())
    out = {}
    for enrollment_id, student_id in seats:
        counted, pct = attendance.get(student_id, (0, None))
        average, run = averages.get(student_id), runs.get(student_id, 0)
        reasons = []
        if th["min_attendance_percent"] is not None and pct is not None and counted >= th["min_sessions"] and pct < th["min_attendance_percent"]:
            reasons.append("attendance")
        if th["min_assessment_percent"] is not None and average is not None and average < th["min_assessment_percent"]:
            reasons.append("assessment")
        if th["max_consecutive_absences"] is not None and run >= th["max_consecutive_absences"]:
            reasons.append("absences")
        out[enrollment_id] = {"student_id": student_id, "reasons": reasons, "attendance_percent": pct, "assessment_percent": average, "consecutive_absences": run}
    return out


async def _alert(db: AsyncSession, trainer_id: UUID | None, student_id: UUID, enrollment_id: UUID, *, raised: bool) -> None:
    """The student, the batch's trainer and the student's itc-003 counselor (loaded per transition -- transitions are rare)."""
    counselor = await db.scalar(select(User).join(ItStudentCounselor, ItStudentCounselor.counselor_user_id == User.id).where(ItStudentCounselor.student_user_id == student_id))
    staff_event = "it.training.at_risk" if raised else "it.training.back_on_track"
    await notify(db, [await db.get(User, student_id)], "it.training.check_in" if raised else "it.training.back_on_track", enrollment_id, action_url="/it/student/attendance")
    await notify(db, [await db.get(User, trainer_id) if trainer_id else None], staff_event, enrollment_id, action_url="/it/trainer/student-progress")
    await notify(db, [counselor], staff_event, enrollment_id, action_url=f"/it/counselor/students/{student_id}/profile")


async def _apply(db: AsyncSession, counts: dict, batch_id: UUID, trainer_id: UUID | None, seats: dict[UUID, dict], open_flags: dict[UUID, UUID], now: datetime) -> None:
    """`open_flags`: enrolment id -> open flag id. Plain ids only, so a rolled-back seat never leaves an expired object behind."""
    for enrollment_id, seat in seats.items():
        flag_id, figures = open_flags.get(enrollment_id), {k: seat[k] for k in ("reasons", "attendance_percent", "assessment_percent", "consecutive_absences")}
        try:
            if seat["reasons"] and flag_id is None:
                async with db.begin_nested():
                    db.add(StudentRiskFlag(enrollment_id=enrollment_id, student_id=seat["student_id"], batch_id=batch_id, raised_at=now, **figures))
                    await db.flush()
                    await _alert(db, trainer_id, seat["student_id"], enrollment_id, raised=True)
                counts["raised"] += 1
            elif seat["reasons"]:
                await db.execute(update(StudentRiskFlag).where(StudentRiskFlag.id == flag_id, StudentRiskFlag.cleared_at.is_(None)).values(**figures))
                counts["kept"] += 1
            elif flag_id is not None:
                async with db.begin_nested():
                    closed = await db.scalar(
                        update(StudentRiskFlag).where(StudentRiskFlag.id == flag_id, StudentRiskFlag.cleared_at.is_(None))
                        .values(cleared_at=now, clear_reason="recovered").returning(StudentRiskFlag.id)  # keeps the last flagged figures (history)
                    )  # fmt: skip
                    if closed is not None:
                        await _alert(db, trainer_id, seat["student_id"], enrollment_id, raised=False)
                counts["cleared" if closed is not None else "duplicate"] += 1
            await db.commit()
        except IntegrityError:  # another run raised this enrolment's flag first
            await db.rollback()
            counts["duplicate"] += 1
        except Exception:
            await db.rollback()
            counts["failed"] += 1
            logger.exception("itc023_flag_failed", extra={"extra_fields": {"enrollment_id": str(enrollment_id)}})


async def sweep(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    """One pass over every monitored programme's batches; idempotent, so a rerun the same day changes nothing."""
    counts = {"raised": 0, "kept": 0, "cleared": 0, "stopped": 0, "duplicate": 0, "failed": 0}
    rows = await db.execute(select(ItRiskThreshold.program_id, *(getattr(ItRiskThreshold, f) for f in FIELDS)).where(or_(*(getattr(ItRiskThreshold, c).is_not(None) for c in CRITERIA))))
    monitored = {program_id: dict(zip(FIELDS, values, strict=True)) for program_id, *values in rows.all()}  # plain values: they outlive a rollback
    open_flags = dict((await db.execute(select(StudentRiskFlag.enrollment_id, StudentRiskFlag.id).where(StudentRiskFlag.cleared_at.is_(None)))).all())
    evaluated: set[UUID] = set()
    batches = (await db.execute(select(Batch.id, Batch.trainer_id, Batch.program_id).where(Batch.program_id.in_(list(monitored))).order_by(Batch.id))).all() if monitored else []
    for batch_id, trainer_id, program_id in batches:
        seats = await _evaluate(db, batch_id, monitored[program_id])
        evaluated.update(seats)
        await _apply(db, counts, batch_id, trainer_id, seats, open_flags, now)
    stale = [flag_id for eid, flag_id in open_flags.items() if eid not in evaluated]
    if stale:  # the enrolment is no longer active or its programme no longer monitored: closed without an alert (R5)
        result = await db.execute(update(StudentRiskFlag).where(StudentRiskFlag.id.in_(stale), StudentRiskFlag.cleared_at.is_(None)).values(cleared_at=now, clear_reason="stopped"))
        counts["stopped"] = result.rowcount
        await db.commit()
    logger.info("itc023_at_risk_done", extra={"extra_fields": {"at": now.isoformat(), **counts}})
    try:  # itc-031 (DEC-SCOPE-358 L7): the lifecycle history catches up (flags just raised/cleared, start dates reached); never the counts
        await it_lifecycle.sync_all(db)
    except Exception:
        await db.rollback()
        logger.exception("itc031_lifecycle_catch_up_failed")
    return counts


async def run_at_risk_sweep() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await sweep(db, now=datetime.now(UTC))


# --- scoped reads --------------------------------------------------------------------------------------------------------------------
def _scoped(user: User):
    """The flags this reader may see (R8): the IT Admin any, an IT counselor their linked students, a trainer their batches."""
    stmt = (
        select(StudentRiskFlag, User, Batch, Program).join(User, User.id == StudentRiskFlag.student_id).join(Batch, Batch.id == StudentRiskFlag.batch_id).join(Program, Program.id == Batch.program_id)
    )
    if user.division != "it":
        raise HTTPException(403, READERS_ONLY)
    if user.role == "it_admin":
        return stmt, "/it/admin/students/{}/profile"
    if user.role == "counselor":
        return stmt.join(
            ItStudentCounselor, and_(ItStudentCounselor.student_user_id == StudentRiskFlag.student_id, ItStudentCounselor.counselor_user_id == user.id)
        ), "/it/counselor/students/{}/profile"
    if user.role == "trainer":
        return stmt.where(Batch.trainer_id == user.id), None
    raise HTTPException(403, READERS_ONLY)


async def list_flags(db: AsyncSession, user: User, *, student_id: UUID | None = None, history: bool = False) -> list[dict]:
    stmt, profile = _scoped(user)
    if student_id:
        stmt = stmt.where(StudentRiskFlag.student_id == student_id)
    if not history:
        stmt = stmt.where(StudentRiskFlag.cleared_at.is_(None))
    rows = await db.execute(stmt.order_by(StudentRiskFlag.cleared_at.is_not(None), StudentRiskFlag.raised_at.desc(), StudentRiskFlag.id).limit(LIST_LIMIT))
    return [
        {
            "id": flag.id, "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code},
            "program": program.title, "batch": {"id": batch.id, "name": batch.name}, "reasons": flag.reasons,
            "attendance_percent": flag.attendance_percent, "assessment_percent": flag.assessment_percent, "consecutive_absences": flag.consecutive_absences,
            "raised_at": flag.raised_at, "cleared_at": flag.cleared_at, "clear_reason": flag.clear_reason,
            "profile_url": profile.format(student.id) if profile else None,
        }
        for flag, student, batch, program in rows.all()
    ]  # fmt: skip
