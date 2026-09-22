"""ENH-011 -- School skills tracker: Soft Skills / Digital Skills batches run by a Career Counselor
(docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md, `DEC-SCOPE-023`).

Its own router, like ENH-005's, so `schools.py` does not grow. The portfolio and parent-notification helpers are reused
unchanged from `schools.py`. A batch belongs to one school in the counselor's `SchoolStaffAssignment` portfolio; anything
outside that portfolio is a 404 (existence is not revealed), except a student, which keeps `_student_in_portfolio`'s 403 so
this matches SCH-004/009. Every route depends on `_require_career_counselor`, so a wrong role is a 403 before any lookup."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _notify_student_parents, _portfolio_school_ids, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    School,
    SchoolSkillAssessment,
    SchoolSkillAttendance,
    SchoolSkillBatch,
    SchoolSkillEnrollment,
    SchoolSkillScore,
    SchoolSkillSession,
    SchoolStudent,
    User,
)
from app.schemas import (
    SkillAssessmentCreate,
    SkillAssessmentOut,
    SkillAssessmentScoresOut,
    SkillAttendanceIn,
    SkillBatchCreate,
    SkillBatchDetail,
    SkillBatchOut,
    SkillBatchPage,
    SkillBatchStatus,
    SkillBatchUpdate,
    SkillEnrollCreate,
    SkillEnrollmentOut,
    SkillEnrollmentUpdate,
    SkillModule,
    SkillScoresIn,
    SkillSessionCreate,
    SkillSessionOut,
)

router = APIRouter(prefix="/school", tags=["school-skills"])
logger = get_logger("app.school.skills")

BASE = "/career-counselor"
BATCH_NOT_FOUND = "Skills batch not found"
ENROLMENT_NOT_FOUND = "Enrolment not found"
BATCH_CLOSED = "This batch is closed. Reopen it to make this change."
STUDENT_MOVED = "This student has moved to another school; their record in this batch is read-only"
MODULE_LABEL = {"soft_skills": "Soft Skills", "digital_skills": "Digital Skills"}

# Read at call time so a test can shorten it; never request input. Bounds the unpaginated batch detail (spec §5.1).
MAX_ENROLMENTS_PER_BATCH = 200
# D8/D11: the counselor decides; `certified` is terminal.
TRANSITIONS: dict[str, set[str]] = {
    "enrolled": {"completed", "certified", "withdrawn"},
    "completed": {"certified", "enrolled"},
    "withdrawn": {"enrolled"},
    "certified": set(),
}


async def _require_career_counselor(user: User = Depends(get_current_user)) -> User:
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    return user


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id: UUID, **metadata) -> None:
    """One `AuditLog` row in the caller's transaction. Metadata is ids and counts only, never a student's name (AC-12)."""
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


async def _batch_in_portfolio(db: AsyncSession, user: User, batch_id: UUID, lock: Literal["update", "share"] | None = None) -> SchoolSkillBatch:
    """The batch, if its school is in this counselor's portfolio, else 404. `lock="update"` (FOR NO KEY UPDATE) serializes
    enrolments against each other and against a close; `lock="share"` (FOR SHARE) lets child writes run together while a
    concurrent close waits for them (spec §5.4)."""
    portfolio = await _portfolio_school_ids(db, user)
    stmt = select(SchoolSkillBatch).where(SchoolSkillBatch.id == batch_id, SchoolSkillBatch.school_id.in_(portfolio))
    if lock == "update":
        stmt = stmt.with_for_update(key_share=True)
    elif lock == "share":
        stmt = stmt.with_for_update(read=True)
    batch = await db.scalar(stmt) if portfolio else None
    if batch is None:
        raise HTTPException(404, BATCH_NOT_FOUND)
    return batch


def _batch_out(batch: SchoolSkillBatch, school_name: str, enrolled_count: int) -> dict:
    return {
        "id": batch.id,
        "school": {"id": batch.school_id, "name": school_name},
        "module_type": batch.module_type,
        "title": batch.title,
        "topic": batch.topic,
        "trainer_name": batch.trainer_name,
        "start_date": batch.start_date,
        "end_date": batch.end_date,
        "status": batch.status,
        "enrolled_count": enrolled_count,
        "created_at": batch.created_at,
    }


def _active_counts():
    """Enrolments that still count (not withdrawn), per batch."""
    return (
        select(SchoolSkillEnrollment.batch_id, func.count().label("n"))
        .where(SchoolSkillEnrollment.status != "withdrawn")
        .group_by(SchoolSkillEnrollment.batch_id)
        .subquery()
    )


def enrollment_out(enrollment: SchoolSkillEnrollment, student: SchoolStudent, batch: SchoolSkillBatch, attendance: dict, scores: list[dict]) -> dict:
    return {
        "id": enrollment.id,
        "batch_id": enrollment.batch_id,
        "school_student_id": enrollment.school_student_id,
        "student_name": student.full_name,
        "status": enrollment.status,
        # D9: the student has since moved to another school -- read-only here, still their history.
        "frozen": student.school_id != batch.school_id,
        "completed_at": enrollment.completed_at,
        "certified_at": enrollment.certified_at,
        "created_at": enrollment.created_at,
        "attendance": attendance,
        "scores": scores,
    }


async def _detail(db: AsyncSession, batch: SchoolSkillBatch) -> dict:
    """The whole batch in five queries, whatever its size (bounded at MAX_ENROLMENTS_PER_BATCH)."""
    school = await db.get(School, batch.school_id)
    enrolments = (
        await db.execute(
            select(SchoolSkillEnrollment, SchoolStudent)
            .join(SchoolStudent, SchoolStudent.id == SchoolSkillEnrollment.school_student_id)
            .where(SchoolSkillEnrollment.batch_id == batch.id)
            .order_by(SchoolStudent.full_name.asc(), SchoolSkillEnrollment.id.asc())
        )
    ).all()
    sessions = (await db.scalars(select(SchoolSkillSession).where(SchoolSkillSession.batch_id == batch.id).order_by(SchoolSkillSession.session_date.asc()))).all()
    marks = (
        await db.scalars(select(SchoolSkillAttendance).join(SchoolSkillSession, SchoolSkillSession.id == SchoolSkillAttendance.session_id).where(SchoolSkillSession.batch_id == batch.id))
    ).all()
    assessments = (
        await db.scalars(select(SchoolSkillAssessment).where(SchoolSkillAssessment.batch_id == batch.id).order_by(SchoolSkillAssessment.created_at.asc(), SchoolSkillAssessment.name.asc()))
    ).all()
    scores = (
        await db.scalars(select(SchoolSkillScore).join(SchoolSkillAssessment, SchoolSkillAssessment.id == SchoolSkillScore.assessment_id).where(SchoolSkillAssessment.batch_id == batch.id))
    ).all()

    marks_by_session: dict[UUID, list] = {}
    summary: dict[UUID, dict] = {}
    for mark in marks:
        marks_by_session.setdefault(mark.session_id, []).append({"enrollment_id": mark.enrollment_id, "present": mark.present})
        counts = summary.setdefault(mark.enrollment_id, {"present": 0, "marked": 0})
        counts["marked"] += 1
        counts["present"] += int(mark.present)
    scores_by_enrolment: dict[UUID, list] = {}
    for score in scores:
        scores_by_enrolment.setdefault(score.enrollment_id, []).append({"assessment_id": score.assessment_id, "score": float(score.score), "remarks": score.remarks})

    active = sum(1 for e, _s in enrolments if e.status != "withdrawn")
    return {
        **_batch_out(batch, school.name if school else "", active),
        "enrollments": [enrollment_out(e, s, batch, summary.get(e.id, {"present": 0, "marked": 0}), scores_by_enrolment.get(e.id, [])) for e, s in enrolments],
        "sessions": [{"id": s.id, "session_date": s.session_date, "topic": s.topic, "attendance": marks_by_session.get(s.id, [])} for s in sessions],
        "assessments": [{"id": a.id, "name": a.name, "max_score": float(a.max_score)} for a in assessments],
    }


# --- Batches ----------------------------------------------------------------------------------------------------------


@router.post(f"{BASE}/skill-batches", status_code=201, response_model=SkillBatchOut)
async def create_skill_batch(payload: SkillBatchCreate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    if payload.school_id not in await _portfolio_school_ids(db, user):
        raise HTTPException(403, "This school is outside your own portfolio")
    batch = SchoolSkillBatch(**payload.model_dump(), status="open", created_by_user_id=user.id)
    db.add(batch)
    await db.flush()
    _audit(db, user, "school.skill_batch_create", "school_skill_batch", batch.id, school_id=str(batch.school_id), module_type=batch.module_type)
    await db.commit()
    await db.refresh(batch)
    logger.info("skill_batch_created", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id), "school_id": str(batch.school_id), "module_type": batch.module_type}})
    school = await db.get(School, batch.school_id)
    return _batch_out(batch, school.name if school else "", 0)


@router.get(f"{BASE}/skill-batches", response_model=SkillBatchPage)
async def list_skill_batches(
    module_type: SkillModule | None = None,
    status: SkillBatchStatus | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_career_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Newest first. `{items, total, limit, offset}` like ENH-005's lists (its D6)."""
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    filters: list[ColumnElement[bool]] = [SchoolSkillBatch.school_id.in_(portfolio)]
    if module_type:
        filters.append(SchoolSkillBatch.module_type == module_type)
    if status:
        filters.append(SchoolSkillBatch.status == status)
    total = await db.scalar(select(func.count()).select_from(SchoolSkillBatch).where(*filters))
    counts = _active_counts()
    rows = (
        await db.execute(
            select(SchoolSkillBatch, School.name, func.coalesce(counts.c.n, 0))
            .join(School, School.id == SchoolSkillBatch.school_id)
            .outerjoin(counts, counts.c.batch_id == SchoolSkillBatch.id)
            .where(*filters)
            .order_by(SchoolSkillBatch.created_at.desc(), SchoolSkillBatch.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"items": [_batch_out(b, name, n) for b, name, n in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get(f"{BASE}/skill-batches/{{batch_id}}", response_model=SkillBatchDetail)
async def get_skill_batch(batch_id: UUID, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """Not paginated: bounded by MAX_ENROLMENTS_PER_BATCH (spec §5.1)."""
    return await _detail(db, await _batch_in_portfolio(db, user, batch_id))


@router.patch(f"{BASE}/skill-batches/{{batch_id}}", response_model=SkillBatchOut)
async def update_skill_batch(batch_id: UUID, payload: SkillBatchUpdate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """Partial edit. Closing takes the batch row lock, so it waits for any in-flight child write (spec §5.4)."""
    batch = await _batch_in_portfolio(db, user, batch_id, lock="update")
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is None:
        raise HTTPException(422, "title must not be blank")
    start, end = changes.get("start_date", batch.start_date), changes.get("end_date", batch.end_date)
    if start is None or (end is not None and end < start):
        raise HTTPException(422, "end_date must be on or after start_date")
    for field, value in changes.items():
        setattr(batch, field, value)
    _audit(db, user, "school.skill_batch_update", "school_skill_batch", batch.id, fields=sorted(changes))
    await db.commit()
    await db.refresh(batch)
    logger.info("skill_batch_updated", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id), "fields": sorted(changes)}})
    counts = await db.scalar(select(func.count()).select_from(SchoolSkillEnrollment).where(SchoolSkillEnrollment.batch_id == batch.id, SchoolSkillEnrollment.status != "withdrawn"))
    school = await db.get(School, batch.school_id)
    return _batch_out(batch, school.name if school else "", counts or 0)


# --- Enrolment and completion ---------------------------------------------------------------------------------------


async def _notify_after_commit(db: AsyncSession, notices: list[tuple[UUID, str, str]]) -> None:
    """Parent notices for writes that have ALREADY committed (a rolled-back write never tells anyone). A failure is logged
    and swallowed: it must never undo or fail the write (SCH-007-AC04, spec §5.4). Notices carry the student's id, not the
    row: a rollback after one failure expires every loaded object, so each student is re-read inside its own attempt."""
    for student_id, title, body in notices:
        try:
            student = await db.get(SchoolStudent, student_id, populate_existing=True)
            if student is not None:
                await _notify_student_parents(db, student, title=title, body=body, action_url=f"/school/parent/children/{student_id}")
            await db.commit()
        except Exception:  # noqa: BLE001 -- the write has committed; see docstring
            await db.rollback()
            logger.warning("skill_notification_failed", extra={"extra_fields": {"student_id": str(student_id)}}, exc_info=True)


def _status_notice(student: SchoolStudent, batch: SchoolSkillBatch, status: str) -> tuple[UUID, str, str]:
    label = MODULE_LABEL[batch.module_type]
    if status == "enrolled":
        return student.id, f"{student.full_name} enrolled in {batch.title}", f'{student.full_name} has been enrolled in the {label} batch "{batch.title}".'
    if status == "completed":
        return student.id, f"{student.full_name} completed {batch.title}", f'{student.full_name} has completed the {label} batch "{batch.title}".'
    return student.id, f"{student.full_name} certified in {batch.title}", f'{student.full_name} has been certified in the {label} batch "{batch.title}".'


async def _enrolment_summary(db: AsyncSession, enrollment_id: UUID) -> tuple[dict, list[dict]]:
    marks = (await db.scalars(select(SchoolSkillAttendance.present).where(SchoolSkillAttendance.enrollment_id == enrollment_id))).all()
    scores = (await db.scalars(select(SchoolSkillScore).where(SchoolSkillScore.enrollment_id == enrollment_id))).all()
    return (
        {"present": sum(1 for present in marks if present), "marked": len(marks)},
        [{"assessment_id": s.assessment_id, "score": float(s.score), "remarks": s.remarks} for s in scores],
    )


@router.post(f"{BASE}/skill-batches/{{batch_id}}/enrollments", status_code=201, response_model=list[SkillEnrollmentOut])
async def enrol_students(batch_id: UUID, payload: SkillEnrollCreate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """All or nothing. The batch row is locked first, so the cap and the open check cannot be raced; the unique index
    turns a concurrent duplicate into a 409 (spec §5.4)."""
    batch = await _batch_in_portfolio(db, user, batch_id, lock="update")
    if batch.status != "open":
        raise HTTPException(409, BATCH_CLOSED)
    students = [await _student_in_portfolio(db, user, student_id) for student_id in payload.school_student_ids]
    if any(s.school_id != batch.school_id for s in students):
        raise HTTPException(422, "A student in this request is at a different school than this batch")
    existing = set((await db.scalars(select(SchoolSkillEnrollment.school_student_id).where(SchoolSkillEnrollment.batch_id == batch.id))).all())
    if existing & {s.id for s in students}:
        raise HTTPException(409, "A student in this request is already enrolled in this batch")
    if len(existing) + len(students) > MAX_ENROLMENTS_PER_BATCH:
        logger.warning("skill_batch_cap_reached", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id)}})
        raise HTTPException(409, f"A batch can hold at most {MAX_ENROLMENTS_PER_BATCH} students")
    rows = [SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s.id, status="enrolled", enrolled_by_user_id=user.id) for s in students]
    db.add_all(rows)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("skill_enrolment_conflict", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch_id)}})
        raise HTTPException(409, "A student in this request is already enrolled in this batch") from exc
    _audit(db, user, "school.skill_enrollment_create", "school_skill_batch", batch.id, count=len(rows))
    await db.commit()
    for row in rows:
        await db.refresh(row)
    logger.info("skill_students_enrolled", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id), "count": len(rows)}})
    out = [enrollment_out(row, student, batch, {"present": 0, "marked": 0}, []) for row, student in zip(rows, students, strict=True)]
    await _notify_after_commit(db, [_status_notice(s, batch, "enrolled") for s in students])
    return out


@router.patch(f"{BASE}/skill-enrollments/{{enrollment_id}}", response_model=SkillEnrollmentOut)
async def update_enrolment_status(enrollment_id: UUID, payload: SkillEnrollmentUpdate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """The enrolment row is locked, so two concurrent "certify" clicks give one transition and one notice. Allowed on a
    closed batch: certifying after the last session is the normal case."""
    portfolio = await _portfolio_school_ids(db, user)
    row = None
    if portfolio:
        row = await db.scalar(
            select(SchoolSkillEnrollment)
            .join(SchoolSkillBatch, SchoolSkillBatch.id == SchoolSkillEnrollment.batch_id)
            .where(SchoolSkillEnrollment.id == enrollment_id, SchoolSkillBatch.school_id.in_(portfolio))
            .with_for_update(of=SchoolSkillEnrollment)
        )
    if row is None:
        raise HTTPException(404, ENROLMENT_NOT_FOUND)
    batch = await db.get(SchoolSkillBatch, row.batch_id)
    student = await db.get(SchoolStudent, row.school_student_id)
    if batch is None or student is None:
        raise HTTPException(404, ENROLMENT_NOT_FOUND)
    if student.school_id != batch.school_id:
        raise HTTPException(409, STUDENT_MOVED)
    old, new = row.status, payload.status
    if new == old:
        # Nothing changed and nobody is told. Commit (not rollback) to release the row lock: a rollback would expire the
        # loaded rows that the response is built from.
        await db.commit()
    else:
        if new not in TRANSITIONS[old]:
            raise HTTPException(409, f"An enrolment cannot change from {old} to {new}")
        now = datetime.now(UTC)
        row.status = new
        if new == "completed" and row.completed_at is None:
            row.completed_at = now
        if new == "certified":
            row.certified_at = now
        _audit(db, user, "school.skill_enrollment_status_change", "school_skill_enrollment", row.id, from_status=old, to_status=new)
        await db.commit()
        await db.refresh(row)
        logger.info("skill_enrolment_status_changed", extra={"extra_fields": {"actor_id": str(user.id), "enrollment_id": str(row.id), "from": old, "to": new}})
    attendance, scores = await _enrolment_summary(db, row.id)
    out = enrollment_out(row, student, batch, attendance, scores)
    if new != old and new in {"completed", "certified"}:
        await _notify_after_commit(db, [_status_notice(student, batch, new)])
    return out


# --- Sessions, attendance, assessments, scores (shared rules) ---------------------------------------------------------


def _require_open(batch: SchoolSkillBatch) -> None:
    if batch.status != "open":
        raise HTTPException(409, BATCH_CLOSED)


async def _require_editable(db: AsyncSession, batch: SchoolSkillBatch, enrollment_ids: list[UUID]) -> None:
    """Every listed enrolment must belong to this batch (else 422) and still take marks: not withdrawn, not certified
    (D11 -- a certificate is not quietly re-scored) and not frozen by a transfer (D9) -- else 409."""
    rows = (
        await db.execute(
            select(SchoolSkillEnrollment.status, SchoolStudent.school_id)
            .join(SchoolStudent, SchoolStudent.id == SchoolSkillEnrollment.school_student_id)
            .where(SchoolSkillEnrollment.batch_id == batch.id, SchoolSkillEnrollment.id.in_(enrollment_ids))
        )
    ).all()
    if len(rows) != len(enrollment_ids):
        raise HTTPException(422, "An enrolment in this request is not in this batch")
    if any(school_id != batch.school_id for _status, school_id in rows):
        raise HTTPException(409, STUDENT_MOVED)
    if any(status in {"withdrawn", "certified"} for status, _school in rows):
        raise HTTPException(409, "A withdrawn or certified enrolment cannot be changed")


# --- Sessions and attendance --------------------------------------------------------------------------------------------


async def _session_out(db: AsyncSession, session: SchoolSkillSession) -> dict:
    marks = (await db.scalars(select(SchoolSkillAttendance).where(SchoolSkillAttendance.session_id == session.id))).all()
    return {"id": session.id, "session_date": session.session_date, "topic": session.topic, "attendance": [{"enrollment_id": m.enrollment_id, "present": m.present} for m in marks]}


@router.post(f"{BASE}/skill-batches/{{batch_id}}/sessions", status_code=201, response_model=SkillSessionOut)
async def create_skill_session(batch_id: UUID, payload: SkillSessionCreate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    batch = await _batch_in_portfolio(db, user, batch_id, lock="share")
    _require_open(batch)
    if payload.session_date < batch.start_date or (batch.end_date is not None and payload.session_date > batch.end_date):
        raise HTTPException(422, "The session date must be within the batch's dates")
    session = SchoolSkillSession(batch_id=batch.id, session_date=payload.session_date, topic=payload.topic, created_by_user_id=user.id)
    db.add(session)
    try:
        await db.flush()
    except IntegrityError as exc:  # D10: uq_skill_session_batch_date
        await db.rollback()
        raise HTTPException(409, f"This batch already has a session on {payload.session_date.isoformat()}") from exc
    _audit(db, user, "school.skill_session_create", "school_skill_session", session.id, batch_id=str(batch.id))
    await db.commit()
    logger.info("skill_session_created", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id), "session_id": str(session.id)}})
    return {"id": session.id, "session_date": session.session_date, "topic": session.topic, "attendance": []}


@router.put(f"{BASE}/skill-sessions/{{session_id}}/attendance", response_model=SkillSessionOut)
async def mark_skill_attendance(session_id: UUID, payload: SkillAttendanceIn, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """Upserts the listed marks only (unlisted ones are untouched), so a retry is harmless. The batch is held FOR SHARE,
    so a concurrent close waits for this write to finish (spec §5.4)."""
    session = await db.get(SchoolSkillSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    batch = await _batch_in_portfolio(db, user, session.batch_id, lock="share")
    _require_open(batch)
    await _require_editable(db, batch, [r.enrollment_id for r in payload.records])
    stmt = pg_insert(SchoolSkillAttendance).values(
        [{"id": uuid4(), "session_id": session.id, "enrollment_id": r.enrollment_id, "present": r.present, "marked_by_user_id": user.id} for r in payload.records]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_skill_attendance_session_enrollment",
            set_={"present": stmt.excluded.present, "marked_by_user_id": stmt.excluded.marked_by_user_id, "updated_at": func.now()},
        )
    )
    _audit(db, user, "school.skill_attendance_mark", "school_skill_session", session.id, count=len(payload.records))
    await db.commit()
    logger.info("skill_attendance_marked", extra={"extra_fields": {"actor_id": str(user.id), "session_id": str(session.id), "count": len(payload.records)}})
    return await _session_out(db, session)


# --- Assessments and scores -----------------------------------------------------------------------------------------


@router.post(f"{BASE}/skill-batches/{{batch_id}}/assessments", status_code=201, response_model=SkillAssessmentOut)
async def create_skill_assessment(batch_id: UUID, payload: SkillAssessmentCreate, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    batch = await _batch_in_portfolio(db, user, batch_id, lock="share")
    _require_open(batch)
    assessment = SchoolSkillAssessment(batch_id=batch.id, name=payload.name, max_score=payload.max_score, created_by_user_id=user.id)
    db.add(assessment)
    try:
        await db.flush()
    except IntegrityError as exc:  # uq_skill_assessment_batch_name
        await db.rollback()
        raise HTTPException(409, "This batch already has an assessment with that name") from exc
    _audit(db, user, "school.skill_assessment_create", "school_skill_assessment", assessment.id, batch_id=str(batch.id))
    await db.commit()
    logger.info("skill_assessment_created", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id), "assessment_id": str(assessment.id)}})
    return {"id": assessment.id, "name": assessment.name, "max_score": float(assessment.max_score)}


@router.put(f"{BASE}/skill-assessments/{{assessment_id}}/scores", response_model=SkillAssessmentScoresOut)
async def record_skill_scores(assessment_id: UUID, payload: SkillScoresIn, user: User = Depends(_require_career_counselor), db: AsyncSession = Depends(get_db)):
    """Upserts the listed scores only, all or nothing; same locking as attendance."""
    assessment = await db.get(SchoolSkillAssessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "Assessment not found")
    batch = await _batch_in_portfolio(db, user, assessment.batch_id, lock="share")
    _require_open(batch)
    if any(s.score > assessment.max_score for s in payload.scores):
        raise HTTPException(422, f"Scores must be out of {float(assessment.max_score):g}")
    await _require_editable(db, batch, [s.enrollment_id for s in payload.scores])
    stmt = pg_insert(SchoolSkillScore).values(
        [{"id": uuid4(), "assessment_id": assessment.id, "enrollment_id": s.enrollment_id, "score": s.score, "remarks": s.remarks, "recorded_by_user_id": user.id} for s in payload.scores]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_skill_score_assessment_enrollment",
            set_={"score": stmt.excluded.score, "remarks": stmt.excluded.remarks, "recorded_by_user_id": stmt.excluded.recorded_by_user_id, "updated_at": func.now()},
        )
    )
    _audit(db, user, "school.skill_scores_record", "school_skill_assessment", assessment.id, count=len(payload.scores))
    await db.commit()
    logger.info("skill_scores_recorded", extra={"extra_fields": {"actor_id": str(user.id), "assessment_id": str(assessment.id), "count": len(payload.scores)}})
    rows = (await db.scalars(select(SchoolSkillScore).where(SchoolSkillScore.assessment_id == assessment.id))).all()
    return {
        "id": assessment.id,
        "name": assessment.name,
        "max_score": float(assessment.max_score),
        "scores": [{"enrollment_id": r.enrollment_id, "score": float(r.score), "remarks": r.remarks} for r in rows],
    }
