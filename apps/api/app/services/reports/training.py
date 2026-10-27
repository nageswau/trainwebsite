"""nehn-009 (DEC-SCOPE-303): the training reports. The `enrollments` pilot -- one row per enrolment -- proves the framework; nehn-010
registers the rest of the training pack here.

Scope (which rows): super_admin and it_admin every enrolment (the roles `/admin/enrollments` serves); a trainer the batches they train.
Any other role that is granted `reports.training.view` sees no rows until its own scope rule is written (deny by default). A filter only
narrows the scope: a trainer naming another trainer, batch or course gets an empty result, never a hint that it exists."""

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Batch, Enrollment, Program, User
from app.services.reports.registry import Column, Filters, Report, register

ALL_ROWS = {"super_admin", "it_admin"}
Student = aliased(User)
Trainer = aliased(User)


def _scope(user: User) -> list:
    if user.role in ALL_ROWS:
        return []
    if user.role == "trainer":
        return [Batch.trainer_id == user.id]
    return [false()]


def _enrollments(user: User, f: Filters):
    stmt = (
        select(
            Enrollment.enrollment_code.label("enrollment_code"), Student.student_code.label("student_code"), Student.full_name.label("student"),
            Program.title.label("course"), Batch.name.label("batch"), Trainer.full_name.label("trainer"), Enrollment.enrolled_on.label("enrolled_on"),
            Batch.end_date.label("batch_ends"), Enrollment.status.label("status"), Enrollment.progress_percent.label("progress"),
        )
        .join(Student, Student.id == Enrollment.student_id)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
        .where(*_scope(user))
    )
    if f.date_from:
        stmt = stmt.where(Enrollment.enrolled_on >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Enrollment.enrolled_on <= f.date_to)
    if f.completion_from:
        stmt = stmt.where(Batch.end_date >= f.completion_from)
    if f.completion_to:
        stmt = stmt.where(Batch.end_date <= f.completion_to)
    if f.course_id:
        stmt = stmt.where(Batch.program_id == f.course_id)
    if f.batch_id:
        stmt = stmt.where(Enrollment.batch_id == f.batch_id)
    if f.trainer_id:
        stmt = stmt.where(Batch.trainer_id == f.trainer_id)
    if f.status:
        stmt = stmt.where(Enrollment.status == f.status)
    if f.student:
        stmt = stmt.where(or_(
            func.lower(Student.student_code) == f.student.lower(),
            Student.full_name.icontains(f.student, autoescape=True), Student.email.icontains(f.student, autoescape=True),
        ))
    return stmt.order_by(Enrollment.enrolled_on.desc(), Enrollment.enrollment_code)


def _choices(rows) -> list[dict]:
    """Distinct {value, label} pairs in label order."""
    seen = {str(value): label for value, label in rows if value is not None}
    return [{"value": value, "label": label} for value, label in sorted(seen.items(), key=lambda pair: (pair[1].lower(), pair[0]))]


async def _options(db: AsyncSession, user: User) -> dict:
    """The pickers, within the caller's scope: no other trainer's batch, course or name reaches a trainer."""
    batches = (
        await db.execute(
            select(Batch.id, Batch.name, Program.id, Program.title, Trainer.id, Trainer.full_name)
            .join(Program, Program.id == Batch.program_id).outerjoin(Trainer, Trainer.id == Batch.trainer_id).where(*_scope(user))
        )
    ).all()
    statuses = (await db.scalars(select(Enrollment.status).distinct().join(Batch, Batch.id == Enrollment.batch_id).where(*_scope(user)))).all()
    return {
        "courses": _choices((row[2], row[3]) for row in batches),
        "batches": _choices((row[0], row[1]) for row in batches),
        "trainers": _choices((row[4], row[5]) for row in batches),
        "statuses": [{"value": s, "label": s} for s in sorted(statuses)],
    }


ENROLLMENTS = register(Report(
    id="enrollments",
    title="Enrollments",
    description="One row per student enrolment: course, batch, trainer, enrolment date, status and progress.",
    resource="reports.training",
    columns=(
        Column("enrollment_code", "Enrollment code"), Column("student_code", "Student code"), Column("student", "Student"),
        Column("course", "Course"), Column("batch", "Batch"), Column("trainer", "Trainer"), Column("enrolled_on", "Enrolled on"),
        Column("batch_ends", "Batch ends"), Column("status", "Status"), Column("progress", "Progress %"),
    ),
    filters=("from", "to", "course_id", "batch_id", "trainer_id", "student", "status", "latest", "completion_from", "completion_to"),
    query=_enrollments,
    options=_options,
))
