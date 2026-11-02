"""nehn-010 (DEC-SCOPE-305): the set-based progress calculator shared by the training reports and certificate eligibility.

Each builder returns a subquery grouped by seat (student, batch) or by batch, so a report joins them once instead of one query per student,
and `_certificate_eligibility` reads one seat's figures from the same SQL -- the two can never disagree (nehn-010 AC2). The optional
`student_id`/`batch_id` narrow a builder to one seat (eligibility); a report leaves them out and scopes through its own joins."""

from datetime import date
from uuid import UUID

from sqlalchemy import Numeric, Subquery, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Assessment, AssessmentAttempt, Assignment, Attendance, CertificateRule, Submission

LEAVE = "excused"  # itc-021 (DEC-SCOPE-349 L1): the stored value of "Approved leave"


def shown_status(status: str) -> str:
    """itc-021 L1: an IT attendance status as the portal tables print it ("excused" reads "approved leave")."""
    return "approved leave" if status == LEAVE else status
COUNTED_ASSESSMENTS = ("scheduled", "open", "closed", "published")


def percent(part, whole, places: int = 2) -> ColumnElement:
    """part / whole as a percentage; NULL when `whole` is 0 or missing (0/0 is "—", not 0 %)."""
    return case((func.coalesce(whole, 0) > 0, func.round(cast(func.coalesce(part, 0), Numeric) * 100 / whole, places)))


def leave_policy() -> ColumnElement:
    """itc-021 (L2/L7): the configured approved-leave policy as a scalar subquery, so every reader of the % shares one definition and
    none gains a query; 'attended' (the rule before 0232) when no rule row exists."""
    return func.coalesce(select(CertificateRule.leave_policy).where(CertificateRule.division == "it").scalar_subquery(), "attended")


def attended() -> ColumnElement:
    """An attendance row counted as attended: present or late, and approved leave when the policy says so (mgmt-017 TR8)."""
    return or_(Attendance.status.in_(("present", "late")), and_(Attendance.status == LEAVE, leave_policy() == "attended"))


def counted() -> ColumnElement:
    """An attendance row in the % denominator: every row, except approved leave under the 'excluded' policy."""
    return or_(Attendance.status != LEAVE, leave_policy() != "excluded")


def attendance(student_id: UUID | None = None, batch_id: UUID | None = None, date_from: date | None = None, date_to: date | None = None) -> Subquery:
    """(student_id, batch_id, marked, present, absent, late, excused, attended, counted) per seat with any attendance marked. The % is
    attended / counted; `marked` stays the rows marked (the "classes marked" figure)."""
    stmt = select(
        Attendance.student_id, Attendance.batch_id, func.count().label("marked"),
        *(func.count().filter(Attendance.status == status).label(status) for status in ("present", "absent", "late", "excused")),
        func.count().filter(attended()).label("attended"), func.count().filter(counted()).label("counted"),
    ).group_by(Attendance.student_id, Attendance.batch_id)
    if student_id:
        stmt = stmt.where(Attendance.student_id == student_id)
    if batch_id:
        stmt = stmt.where(Attendance.batch_id == batch_id)
    if date_from:
        stmt = stmt.where(Attendance.session_date >= date_from)
    if date_to:
        stmt = stmt.where(Attendance.session_date <= date_to)
    return stmt.subquery()


def assignments(batch_id: UUID | None = None) -> Subquery:
    """(batch_id, total) published assignments per batch."""
    stmt = select(Assignment.batch_id, func.count().label("total")).where(Assignment.published.is_(True)).group_by(Assignment.batch_id)
    return (stmt.where(Assignment.batch_id == batch_id) if batch_id else stmt).subquery()


def graded(student_id: UUID | None = None, batch_id: UUID | None = None) -> Subquery:
    """(student_id, batch_id, graded) graded submissions per seat."""
    stmt = (
        select(Submission.student_id, Assignment.batch_id, func.count().label("graded"))
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(Submission.status == "graded")
        .group_by(Submission.student_id, Assignment.batch_id)
    )
    if student_id:
        stmt = stmt.where(Submission.student_id == student_id)
    if batch_id:
        stmt = stmt.where(Assignment.batch_id == batch_id)
    return stmt.subquery()


def assessments(batch_id: UUID | None = None) -> Subquery:
    """(batch_id, total) counted assessments per batch."""
    stmt = select(Assessment.batch_id, func.count().label("total")).where(Assessment.status.in_(COUNTED_ASSESSMENTS)).group_by(Assessment.batch_id)
    return (stmt.where(Assessment.batch_id == batch_id) if batch_id else stmt).subquery()


def passed(student_id: UUID | None = None, batch_id: UUID | None = None) -> Subquery:
    """(student_id, batch_id, passed) counted assessments whose best graded attempt reached the pass mark, per seat."""
    attempts = select(AssessmentAttempt.student_id, AssessmentAttempt.assessment_id, func.max(AssessmentAttempt.percentage).label("best")).where(
        AssessmentAttempt.status == "graded"
    )
    if student_id:
        attempts = attempts.where(AssessmentAttempt.student_id == student_id)
    best = attempts.group_by(AssessmentAttempt.student_id, AssessmentAttempt.assessment_id).subquery()
    stmt = (
        select(best.c.student_id, Assessment.batch_id, func.count().label("passed"))
        .join(Assessment, Assessment.id == best.c.assessment_id)
        .where(Assessment.status.in_(COUNTED_ASSESSMENTS), best.c.best >= Assessment.pass_percent)
        .group_by(best.c.student_id, Assessment.batch_id)
    )
    return (stmt.where(Assessment.batch_id == batch_id) if batch_id else stmt).subquery()


def assessment_average(batch_id: UUID) -> Subquery:
    """itc-023 (DEC-SCOPE-352 R3): (student_id, average) -- the mean of each student's best graded attempt % over the batch's counted
    assessments they have a graded attempt for (an assessment never graded for them is not averaged in)."""
    best = (
        select(AssessmentAttempt.student_id, func.max(AssessmentAttempt.percentage).label("best"))
        .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
        .where(Assessment.batch_id == batch_id, Assessment.status.in_(COUNTED_ASSESSMENTS), AssessmentAttempt.status == "graded", AssessmentAttempt.percentage.is_not(None))
        .group_by(AssessmentAttempt.student_id, AssessmentAttempt.assessment_id)
        .subquery()
    )
    return select(best.c.student_id, func.round(func.avg(best.c.best), 2).label("average")).group_by(best.c.student_id).subquery()


async def seat(db: AsyncSession, student_id: UUID, batch_id: UUID) -> dict:
    """One seat's figures: attendance_percent (None when nothing is marked), assignments graded/total, assessments passed/total."""
    att, done, tasks, won, tests = attendance(student_id, batch_id), graded(student_id, batch_id), assignments(batch_id), passed(student_id, batch_id), assessments(batch_id)
    row = (
        await db.execute(
            select(
                percent(select(att.c.attended).scalar_subquery(), select(att.c.counted).scalar_subquery()).label("attendance_percent"),
                func.coalesce(select(done.c.graded).scalar_subquery(), 0).label("assignments_graded"),
                func.coalesce(select(tasks.c.total).scalar_subquery(), 0).label("assignments_total"),
                func.coalesce(select(won.c.passed).scalar_subquery(), 0).label("assessments_passed"),
                func.coalesce(select(tests.c.total).scalar_subquery(), 0).label("assessments_total"),
            )
        )
    ).one()
    return dict(row._mapping)


async def seats(db: AsyncSession, batch_id: UUID, student_ids: list[UUID]) -> dict[UUID, dict]:
    """nehn-028 (DEC-SCOPE-308): `seat()` for every listed student of one batch, from the same builders in five queries whatever the
    class size, plus `attendance_marked` (sessions marked) so a seat with none can show "—"."""
    if not student_ids:
        return {}
    att, done, won = attendance(batch_id=batch_id), graded(batch_id=batch_id), passed(batch_id=batch_id)
    tasks = await db.scalar(select(assignments(batch_id).c.total)) or 0
    tests = await db.scalar(select(assessments(batch_id).c.total)) or 0
    marks = {
        student_id: (marked, pct)
        for student_id, marked, pct in await db.execute(select(att.c.student_id, att.c.marked, percent(att.c.attended, att.c.counted)).where(att.c.student_id.in_(student_ids)))
    }
    graded_by = dict((await db.execute(select(done.c.student_id, done.c.graded).where(done.c.student_id.in_(student_ids)))).all())
    passed_by = dict((await db.execute(select(won.c.student_id, won.c.passed).where(won.c.student_id.in_(student_ids)))).all())
    result = {}
    for student_id in student_ids:
        marked, pct = marks.get(student_id, (0, None))
        result[student_id] = {
            "attendance_percent": pct, "attendance_marked": marked,
            "assignments_graded": graded_by.get(student_id, 0), "assignments_total": tasks,
            "assessments_passed": passed_by.get(student_id, 0), "assessments_total": tests,
        }
    return result
