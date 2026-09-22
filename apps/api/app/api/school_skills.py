"""ENH-011 -- School skills tracker: Soft Skills / Digital Skills batches run by a Career Counselor
(docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md, `DEC-SCOPE-023`).

Its own router, like ENH-005's, so `schools.py` does not grow. The portfolio and parent-notification helpers are reused
unchanged from `schools.py`. A batch belongs to one school in the counselor's `SchoolStaffAssignment` portfolio; anything
outside that portfolio is a 404 (existence is not revealed), except a student, which keeps `_student_in_portfolio`'s 403 so
this matches SCH-004/009. Every route depends on `_require_career_counselor`, so a wrong role is a 403 before any lookup."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _portfolio_school_ids
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
from app.schemas import SkillBatchCreate, SkillBatchDetail, SkillBatchOut, SkillBatchPage, SkillBatchStatus, SkillBatchUpdate, SkillModule

router = APIRouter(prefix="/school", tags=["school-skills"])
logger = get_logger("app.school.skills")

BASE = "/career-counselor"
BATCH_NOT_FOUND = "Skills batch not found"


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
