"""nehn-016 (DEC-SCOPE-309): the recruiter's read-only view of training -- (1) students completing soon, (2) the student placement report,
both in the nehn-009 registry under `reports.placement`, and (3) the training panel on the recruiter candidate page.

Population (P1, OD-08 builder's default): IT students in the placement pool only -- the candidate linked to the student opted in (rec-010,
DEC-SCOPE-138) and is not archived, the student an active IT student. A student who has not opted in is never a row, for anyone.
Scope: placement_team, placement_manager, it_admin and super_admin read that population; any other role granted the resource sees nothing
(deny by default; HR is nehn-017's).

One row per student (P3): their counted seat (nehn-010 C2) with the latest batch end -- the expected completion (P2). The figures are
`training_progress`'s, the same SQL as the training reports and certificate eligibility. No fee, discount or payment is ever selected."""

from sqlalchemy import Date, Select, and_, cast, exists, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Batch, Candidate, Enrollment, Interview, JobApplication, JobOffer, PlacementProfile, Program, User
from app.services import training_progress as progress
from app.services.management_training import DROPPED, NOT_TAKEN
from app.services.reports.registry import Column, Filters, Report, register
from app.services.reports.training import CERTIFICATE, STUDENT_COLUMNS, Student, Trainer, _choices, _narrow, _on_seat, counted

ROWS = {"placement_team", "placement_manager", "it_admin", "super_admin"}
DEFAULT_DAYS = 15  # "complete their course within the next 15 days" (§12 L274); the `days` filter changes it
READINESS_DEFAULT = "preparation"  # a student with no placement profile reads as the model default (as /workflows does)
Later, LaterBatch = aliased(Enrollment), aliased(Batch)
TODAY = cast(func.timezone("Asia/Kolkata", func.now()), Date)  # the database clock, as an IST calendar day
POOL = [
    Candidate.opted_in.is_(True), Candidate.archived_at.is_(None), Student.role == "it_student", Student.division == "it", Student.active.is_(True),
]
LATEST_SEAT = ~exists().where(
    Later.student_id == Enrollment.student_id, Later.status.not_in(NOT_TAKEN + DROPPED), LaterBatch.id == Later.batch_id,
    LaterBatch.end_date > Batch.end_date,
)
READINESS = func.coalesce(PlacementProfile.readiness_status, READINESS_DEFAULT).label("readiness")


def _scope(user: User) -> list:
    return [] if user.role in ROWS else [false()]


def _students(user: User, *columns) -> Select:
    """One row per pool student: their latest counted seat, with the batch, course, trainer, candidate and placement profile joined."""
    return (
        select(*columns)
        .select_from(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .join(Candidate, Candidate.user_id == Student.id)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
        .outerjoin(PlacementProfile, PlacementProfile.student_id == Student.id)
        .where(*_scope(user), *POOL, counted, LATEST_SEAT)
    )


def _completing_soon(user: User, f: Filters):
    att = progress.attendance()
    days = f.days or DEFAULT_DAYS
    stmt = (
        _students(
            user, Student.student_code.label("student_code"), Student.full_name.label("student"), Student.phone.label("phone"),
            Student.email.label("email"), Program.title.label("course"), Batch.name.label("batch"), Trainer.full_name.label("trainer"),
            Batch.end_date.label("batch_ends"), (Batch.end_date - TODAY).label("days_left"), Enrollment.progress_percent.label("progress"),
            progress.percent(att.c.attended, att.c.marked).label("attendance_pct"), READINESS, Candidate.status.label("candidate_status"),
        )
        .outerjoin(att, and_(*_on_seat(att)))
        .where(Batch.end_date >= TODAY, Batch.end_date <= TODAY + days)
    )
    return _narrow(stmt, f).order_by(Batch.end_date, func.lower(Student.full_name), Enrollment.enrollment_code)


def _count(*where, joins=()) -> object:
    """How many of the candidate's applications (or their interviews / offers) match, as a correlated scalar."""
    stmt = select(func.count()).select_from(JobApplication)
    for model, on in joins:
        stmt = stmt.join(model, on)
    return stmt.where(JobApplication.candidate_id == Candidate.id, *where).correlate(Candidate).scalar_subquery()


def _placement_students(user: User, f: Filters):
    offer = (JobOffer, JobOffer.application_id == JobApplication.id)
    stmt = _students(
        user, Student.student_code.label("student_code"), Student.full_name.label("student"), Student.email.label("email"),
        Program.title.label("course"), Batch.end_date.label("batch_ends"), Enrollment.progress_percent.label("progress"), READINESS,
        Candidate.status.label("candidate_status"), _count().label("applications"),
        _count(joins=[(Interview, Interview.application_id == JobApplication.id)]).label("interviews"), _count(joins=[offer]).label("offers"),
        _count(JobOffer.joining_status == "joined", joins=[offer]).label("joined"),
    )
    return _narrow(stmt, f).order_by(func.lower(Student.full_name), Enrollment.enrollment_code)


async def _options(db: AsyncSession, user: User) -> dict:
    """The pickers: the courses, batches and trainers of the pool students' seats -- never a batch with no pool student."""
    rows = (await db.execute(_students(user, Batch.id, Batch.name, Program.id, Program.title, Trainer.id, Trainer.full_name))).all()
    return {
        "courses": _choices((row[2], row[3]) for row in rows),
        "batches": _choices((row[0], row[1]) for row in rows),
        "trainers": _choices((row[4], row[5]) for row in rows),
    }


def _placement(id: str, title: str, description: str, columns: tuple[Column, ...], filters: tuple[str, ...], query) -> Report:
    return register(Report(id=id, title=title, description=description, resource="reports.placement", columns=columns, filters=filters,
                           query=query, options=_options))


COMPLETING_SOON = _placement(
    "completing-soon", "Students completing soon",
    f"Placement-pool students whose batch ends within the next {DEFAULT_DAYS} days (change it with 'Completing within'), with progress, "
    "attendance and readiness, so placement can start before the course ends.",
    STUDENT_COLUMNS[:2] + (Column("phone", "Phone"), Column("email", "Email")) + STUDENT_COLUMNS[2:] + (
        Column("batch_ends", "Batch ends"), Column("days_left", "Days left"), Column("progress", "Progress %"),
        Column("attendance_pct", "Attendance %"), Column("readiness", "Readiness"), Column("candidate_status", "Candidate status"),
    ),
    ("days", "course_id", "batch_id", "trainer_id", "student"),
    _completing_soon,
)
PLACEMENT_STUDENTS = _placement(
    "placement-students", "Student placement report",
    "One row per placement-pool student: course, progress, readiness and their applications, interviews, offers and joinings.",
    (
        Column("student_code", "Student code"), Column("student", "Student"), Column("email", "Email"), Column("course", "Course"),
        Column("batch_ends", "Batch ends"), Column("progress", "Progress %"), Column("readiness", "Readiness"),
        Column("candidate_status", "Candidate status"), Column("applications", "Applications"), Column("interviews", "Interviews"),
        Column("offers", "Offers"), Column("joined", "Joined"),
    ),
    ("course_id", "batch_id", "student"),
    _placement_students,
)


async def candidate_training(db: AsyncSession, candidate: Candidate) -> dict:
    """The recruiter candidate page's read-only training panel: every seat the student took (not `pending_consent`/`rejected`), latest
    end first, with the certificate criteria, plus the placement profile's readiness. An external candidate has no training."""
    if candidate.user_id is None:
        return {"student": False, "seats": [], "readiness": None}
    student_id = candidate.user_id
    att, done, won = progress.attendance(student_id=student_id), progress.graded(student_id=student_id), progress.passed(student_id=student_id)
    tasks, tests = progress.assignments(), progress.assessments()
    rows = await db.execute(
        select(
            Program.title.label("course"), Batch.name.label("batch"), Trainer.full_name.label("trainer"), Batch.start_date.label("starts"),
            Batch.end_date.label("ends"), Enrollment.status.label("status"), Enrollment.progress_percent.label("progress"),
            progress.percent(att.c.attended, att.c.marked).label("attendance_pct"), func.coalesce(att.c.marked, 0).label("attendance_marked"),
            func.coalesce(done.c.graded, 0).label("assignments_graded"), func.coalesce(tasks.c.total, 0).label("assignments_total"),
            func.coalesce(won.c.passed, 0).label("assessments_passed"), func.coalesce(tests.c.total, 0).label("assessments_total"), CERTIFICATE,
        )
        .select_from(Enrollment)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
        .outerjoin(att, and_(*_on_seat(att)))
        .outerjoin(done, and_(*_on_seat(done)))
        .outerjoin(won, and_(*_on_seat(won)))
        .outerjoin(tasks, tasks.c.batch_id == Enrollment.batch_id)
        .outerjoin(tests, tests.c.batch_id == Enrollment.batch_id)
        .where(Enrollment.student_id == student_id, Enrollment.status.not_in(NOT_TAKEN))
        .order_by(Batch.end_date.desc(), func.lower(Batch.name), Enrollment.id)
    )
    profile = await db.scalar(select(PlacementProfile).where(PlacementProfile.student_id == student_id))
    readiness = {
        "readiness_status": profile.readiness_status if profile else READINESS_DEFAULT,
        "resume_status": profile.resume_status if profile else "pending",
        "mock_interview_status": profile.mock_interview_status if profile else "pending",
        "aptitude_status": profile.aptitude_status if profile else "pending",
        "available": bool(profile and profile.available),
    }
    return {"student": True, "seats": [dict(row._mapping) for row in rows], "readiness": readiness}
