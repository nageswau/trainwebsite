"""nehn-028 (DEC-SCOPE-305): the certificate completion criteria of many enrolments at once -- one grouped query per factor, whatever the
number of enrolments. Certificate eligibility (one enrolment), the coordinator's queue and the trainer's batch progress view all read it,
so the numbers a trainer sees are the numbers a certificate is issued on."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, AssessmentAttempt, Assignment, Attendance, Enrollment, Payment, Submission

PRESENT = ("present", "late", "excused")
COUNTED_ASSESSMENTS = ("scheduled", "open", "closed", "published")


async def criteria(db: AsyncSession, enrollments: list[Enrollment], rules: dict) -> dict[UUID, dict]:
    """{enrollment_id: criteria} -- the dict `_certificate_eligibility` has always returned, minus its `batch_id`."""
    if not enrollments:
        return {}
    batch_ids = {e.batch_id for e in enrollments}
    student_ids = {e.student_id for e in enrollments}

    attendance = {
        (batch_id, student_id): (total, present)
        for batch_id, student_id, total, present in await db.execute(
            select(Attendance.batch_id, Attendance.student_id, func.count(), func.count().filter(Attendance.status.in_(PRESENT)))
            .where(Attendance.batch_id.in_(batch_ids), Attendance.student_id.in_(student_ids))
            .group_by(Attendance.batch_id, Attendance.student_id)
        )
    }
    assignment_totals = dict(
        (await db.execute(select(Assignment.batch_id, func.count()).where(Assignment.batch_id.in_(batch_ids), Assignment.published.is_(True)).group_by(Assignment.batch_id))).all()
    )
    graded = {
        (batch_id, student_id): count
        for batch_id, student_id, count in await db.execute(
            select(Assignment.batch_id, Submission.student_id, func.count())
            .select_from(Submission)
            .join(Assignment)
            .where(Assignment.batch_id.in_(batch_ids), Submission.student_id.in_(student_ids), Submission.status == "graded")
            .group_by(Assignment.batch_id, Submission.student_id)
        )
    }
    assessments: dict[UUID, list[tuple[UUID, int]]] = defaultdict(list)
    for assessment_id, batch_id, pass_percent in await db.execute(
        select(Assessment.id, Assessment.batch_id, Assessment.pass_percent).where(Assessment.batch_id.in_(batch_ids), Assessment.status.in_(COUNTED_ASSESSMENTS))
    ):
        assessments[batch_id].append((assessment_id, pass_percent))
    assessment_ids = [assessment_id for rows in assessments.values() for assessment_id, _ in rows]
    best = (
        {
            (assessment_id, student_id): percentage
            for assessment_id, student_id, percentage in await db.execute(
                select(AssessmentAttempt.assessment_id, AssessmentAttempt.student_id, func.max(AssessmentAttempt.percentage))
                .where(AssessmentAttempt.assessment_id.in_(assessment_ids), AssessmentAttempt.student_id.in_(student_ids), AssessmentAttempt.status == "graded")
                .group_by(AssessmentAttempt.assessment_id, AssessmentAttempt.student_id)
            )
        }
        if assessment_ids
        else {}
    )
    pending_fees = dict(
        (
            await db.execute(
                select(Payment.user_id, func.sum(Payment.amount))
                .where(Payment.user_id.in_(student_ids), Payment.division == "it", Payment.status.in_(["pending", "overdue"]))
                .group_by(Payment.user_id)
            )
        ).all()
    )

    result = {}
    for enrollment in enrollments:
        total, present = attendance.get((enrollment.batch_id, enrollment.student_id), (0, 0))
        attendance_percent = round(present * 100 / total, 2) if total else 0
        assignment_total = assignment_totals.get(enrollment.batch_id, 0)
        assignment_graded = graded.get((enrollment.batch_id, enrollment.student_id), 0)
        batch_assessments = assessments.get(enrollment.batch_id, [])
        passed = sum(1 for assessment_id, pass_percent in batch_assessments if (score := best.get((assessment_id, enrollment.student_id))) is not None and float(score) >= pass_percent)
        pending_fee = float(pending_fees.get(enrollment.student_id) or 0)
        result[enrollment.id] = {
            "progress_percent": enrollment.progress_percent,
            "attendance_percent": attendance_percent,
            "attendance_sessions": total,
            "assignments_graded": assignment_graded,
            "assignments_total": assignment_total,
            "assessments_passed": passed,
            "assessments_total": len(batch_assessments),
            "pending_fee": pending_fee,
            "rules": rules,
            "eligible": bool(
                enrollment.progress_percent >= rules["min_progress_percent"]
                and attendance_percent >= rules["min_attendance_percent"]
                and assignment_graded >= assignment_total
                and passed >= len(batch_assessments)
                and pending_fee == 0
            ),
        }
    return result
