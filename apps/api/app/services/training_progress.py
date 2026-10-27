"""nehn-010 (DEC-SCOPE-305): the set-based progress calculator shared by the training reports and certificate eligibility.

Each builder returns a subquery grouped by seat (student, batch) or by batch, so a report joins them once instead of one query per student,
and `_certificate_eligibility` reads one seat's figures from the same SQL -- the two can never disagree (nehn-010 AC2). The optional
`student_id`/`batch_id` narrow a builder to one seat (eligibility); a report leaves them out and scopes through its own joins."""

from datetime import date
from uuid import UUID

from sqlalchemy import Numeric, Subquery, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Assessment, AssessmentAttempt, Assignment, Attendance, Submission

ATTENDED = ("present", "late", "excused")  # the certificate rule's attended statuses (mgmt-017 TR8)
COUNTED_ASSESSMENTS = ("scheduled", "open", "closed", "published")


def percent(part, whole, places: int = 2) -> ColumnElement:
    """part / whole as a percentage; NULL when `whole` is 0 or missing (0/0 is "—", not 0 %)."""
    return case((func.coalesce(whole, 0) > 0, func.round(cast(func.coalesce(part, 0), Numeric) * 100 / whole, places)))


def attendance(student_id: UUID | None = None, batch_id: UUID | None = None, date_from: date | None = None, date_to: date | None = None) -> Subquery:
    """(student_id, batch_id, marked, present, absent, late, excused, attended) per seat with any attendance marked."""
    stmt = select(
        Attendance.student_id, Attendance.batch_id, func.count().label("marked"),
        *(func.count().filter(Attendance.status == status).label(status) for status in ("present", "absent", "late", "excused")),
        func.count().filter(Attendance.status.in_(ATTENDED)).label("attended"),
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


async def seat(db: AsyncSession, student_id: UUID, batch_id: UUID) -> dict:
    """One seat's figures: attendance_percent (None when nothing is marked), assignments graded/total, assessments passed/total."""
    att, done, tasks, won, tests = attendance(student_id, batch_id), graded(student_id, batch_id), assignments(batch_id), passed(student_id, batch_id), assessments(batch_id)
    row = (
        await db.execute(
            select(
                percent(select(att.c.attended).scalar_subquery(), select(att.c.marked).scalar_subquery()).label("attendance_percent"),
                func.coalesce(select(done.c.graded).scalar_subquery(), 0).label("assignments_graded"),
                func.coalesce(select(tasks.c.total).scalar_subquery(), 0).label("assignments_total"),
                func.coalesce(select(won.c.passed).scalar_subquery(), 0).label("assessments_passed"),
                func.coalesce(select(tests.c.total).scalar_subquery(), 0).label("assessments_total"),
            )
        )
    ).one()
    return dict(row._mapping)
