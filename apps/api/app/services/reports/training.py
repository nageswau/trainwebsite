"""nehn-009 (DEC-SCOPE-303): the training reports. The `enrollments` pilot -- one row per enrolment -- proves the framework; nehn-010
(DEC-SCOPE-305) registers the training pack: (a) student-wise course report, (b) students per trainer, (c) course completion,
(d) completions in a period, (e) attendance, (f) trainer report, (g) course-wise report. Their field lists are provisional until the
client's admin report template arrives.

Scope (which rows): super_admin and it_admin every enrolment (the roles `/admin/enrollments` serves); a trainer the batches they train,
in every report; HR (nehn-017) the seats of the HR population (services/hr_students). Any other role that is granted `reports.training.view` sees no rows until its own scope rule is written (deny by
default). A filter only narrows the scope: a trainer naming another trainer, batch or course gets an empty result, never a hint that it
exists.

Definitions (nehn-010 C1-C6): a seat is *completed* at progress 100 and its completion date is the batch end; `pending_consent` /
`rejected` never took the seat and `withdrawn` / `dropped` left it, so neither is *counted*; the attendance, assignment and assessment
figures are `training_progress`'s, the same SQL certificate eligibility reads; revenue is the course seats' paid enrolment-fee payments."""

from sqlalchemy import Select, and_, distinct, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.payments import PAID_STATUSES
from app.models import Assignment, Batch, Certificate, Enrollment, Payment, Program, Submission, User
from app.services import hr_students
from app.services import training_progress as progress
from app.services.management_it_revenue import ENROLMENT_REFERENCES
from app.services.management_training import DROPPED, NOT_TAKEN
from app.services.reports.registry import Column, Filters, Report, register

ALL_ROWS = {"super_admin", "it_admin"}
Student = aliased(User)
Trainer = aliased(User)
counted = Enrollment.status.not_in(NOT_TAKEN + DROPPED)
completed = and_(counted, Enrollment.progress_percent >= 100)
SEAT_FILTERS = ("course_id", "batch_id", "trainer_id", "student", "status")


def _scope(user: User) -> list:
    """The caller's batches. HR (nehn-017 H1): a batch holding a seat of the HR population; `_seats` keeps HR rows to those seats."""
    if user.role in ALL_ROWS:
        return []
    if user.role == "trainer":
        return [Batch.trainer_id == user.id]
    if user.role in hr_students.HR_ROLES:
        seat = aliased(Enrollment)
        return [Batch.id.in_(select(seat.batch_id).where(seat.student_id.in_(hr_students.population())))]
    return [false()]


def _seat_scope(user: User) -> list:
    return _scope(user) + ([Enrollment.student_id.in_(hr_students.population())] if user.role in hr_students.HR_ROLES else [])


def _narrow(stmt: Select, f: Filters, *, enrolled_dates: bool = True) -> Select:
    """Apply the filters the caller set. A report only receives the filters it declares (registry.parse refuses the rest), so each
    condition here runs only where it means something; `from`/`to` are the enrolment date unless the report reads them otherwise."""
    conditions = [
        Batch.end_date >= f.completion_from if f.completion_from else None,
        Batch.end_date <= f.completion_to if f.completion_to else None,
        Batch.program_id == f.course_id if f.course_id else None,
        Batch.id == f.batch_id if f.batch_id else None,
        Batch.trainer_id == f.trainer_id if f.trainer_id else None,
        Enrollment.status == f.status if f.status else None,
    ]
    if enrolled_dates:
        conditions += [Enrollment.enrolled_on >= f.date_from if f.date_from else None, Enrollment.enrolled_on <= f.date_to if f.date_to else None]
    if f.student:
        conditions.append(or_(
            func.lower(Student.student_code) == f.student.lower(),
            Student.full_name.icontains(f.student, autoescape=True), Student.email.icontains(f.student, autoescape=True),
        ))
    return stmt.where(*(c for c in conditions if c is not None))


def _seats(user: User, *columns) -> Select:
    """One row per enrolment in the caller's scope, with its student, batch, course and trainer joined."""
    return (
        select(*columns)
        .select_from(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
        .where(*_seat_scope(user))
    )


def _batches(user: User, f: Filters):
    """The caller's batches that pass the batch-level filters, as (id, program_id, trainer_id)."""
    return _narrow(select(Batch.id, Batch.program_id, Batch.trainer_id).where(*_scope(user)), f, enrolled_dates=False).subquery()


def _on_seat(sub) -> list:
    return [sub.c.student_id == Enrollment.student_id, sub.c.batch_id == Enrollment.batch_id]


SEAT = (
    Student.student_code.label("student_code"), Student.full_name.label("student"), Program.title.label("course"), Batch.name.label("batch"),
    Trainer.full_name.label("trainer"),
)
CERTIFICATE = func.coalesce(
    select(Certificate.status).where(Certificate.enrollment_id == Enrollment.id).order_by(Certificate.issued_on.desc()).limit(1)
    .correlate(Enrollment).scalar_subquery(),
    "Not issued",
).label("certificate")


def _enrollments(user: User, f: Filters):
    stmt = _seats(
        user, Enrollment.enrollment_code.label("enrollment_code"), *SEAT, Enrollment.enrolled_on.label("enrolled_on"), Batch.end_date.label("batch_ends"), Enrollment.status.label("status"), Enrollment.progress_percent.label("progress"),
    )
    return _narrow(stmt, f).order_by(Enrollment.enrolled_on.desc(), Enrollment.enrollment_code)


def _student_courses(user: User, f: Filters):
    """(a) one row per seat with the certificate criteria."""
    att, done, tasks, won, tests = progress.attendance(), progress.graded(), progress.assignments(), progress.passed(), progress.assessments()
    stmt = (
        _seats(
            user, *SEAT, Enrollment.enrolled_on.label("enrolled_on"), Enrollment.status.label("status"), Enrollment.progress_percent.label("progress"),
            progress.percent(att.c.attended, att.c.marked).label("attendance_pct"),
            func.coalesce(done.c.graded, 0).label("assignments_graded"), func.coalesce(tasks.c.total, 0).label("assignments_total"),
            func.coalesce(won.c.passed, 0).label("assessments_passed"), func.coalesce(tests.c.total, 0).label("assessments_total"), CERTIFICATE,
        )
        .outerjoin(att, and_(*_on_seat(att)))
        .outerjoin(done, and_(*_on_seat(done)))
        .outerjoin(won, and_(*_on_seat(won)))
        .outerjoin(tasks, tasks.c.batch_id == Enrollment.batch_id)
        .outerjoin(tests, tests.c.batch_id == Enrollment.batch_id)
    )
    return _narrow(stmt, f).order_by(Enrollment.enrolled_on.desc(), Enrollment.enrollment_code)


def _students_by_trainer(user: User, f: Filters):
    """(b) each trainer's students, seat by seat."""
    stmt = _seats(
        user, Trainer.full_name.label("trainer"), Batch.name.label("batch"), Program.title.label("course"), Student.student_code.label("student_code"),
        Student.full_name.label("student"), Enrollment.status.label("status"), Enrollment.progress_percent.label("progress"),
    )
    return _narrow(stmt, f).order_by(func.lower(Trainer.full_name), func.lower(Batch.name), func.lower(Student.full_name), Enrollment.enrollment_code)


def _course_completion(user: User, f: Filters):
    """(c) one row per batch: counted seats, completed seats, the share, certificates issued."""
    students, done = func.count(Enrollment.id).filter(counted), func.count(Enrollment.id).filter(completed)
    certificates = select(func.count(Certificate.id)).join(Enrollment, Enrollment.id == Certificate.enrollment_id).where(Enrollment.batch_id == Batch.id)
    stmt = (
        select(
            Program.title.label("course"), Batch.name.label("batch"), Trainer.full_name.label("trainer"), Batch.start_date.label("batch_starts"),
            Batch.end_date.label("batch_ends"), students.label("students"), done.label("completed"), progress.percent(done, students, 1).label("completion_pct"),
            certificates.correlate(Batch).scalar_subquery().label("certificates"),
        )
        .select_from(Batch)
        .join(Program, Program.id == Batch.program_id)
        .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
        .outerjoin(Enrollment, Enrollment.batch_id == Batch.id)
        .where(*_scope(user))
        .group_by(Batch.id, Program.title, Trainer.full_name)
    )
    return _narrow(stmt, f, enrolled_dates=False).order_by(Batch.end_date.desc(), func.lower(Batch.name), Batch.id)


def _completions(user: User, f: Filters):
    """(d) completed seats, by their batch's end date (the completion period)."""
    att = progress.attendance()
    stmt = (
        _seats(user, *SEAT, Batch.end_date.label("batch_ends"), Enrollment.progress_percent.label("progress"),
               progress.percent(att.c.attended, att.c.marked).label("attendance_pct"), CERTIFICATE)
        .outerjoin(att, and_(*_on_seat(att)))
        .where(completed)
    )
    return _narrow(stmt, f).order_by(Batch.end_date.desc(), func.lower(Student.full_name), Enrollment.enrollment_code)


def _attendance(user: User, f: Filters):
    """(e) per seat: classes marked, each status, the attendance %. `from`/`to` are class dates here."""
    att = progress.attendance(date_from=f.date_from, date_to=f.date_to)
    stmt = _seats(
        user, *SEAT, func.coalesce(att.c.marked, 0).label("marked"),
        *(func.coalesce(att.c[status], 0).label(status) for status in ("present", "absent", "late", "excused")),
        progress.percent(att.c.attended, att.c.marked).label("attendance_pct"),
    ).outerjoin(att, and_(*_on_seat(att)))
    return _narrow(stmt, f, enrolled_dates=False).order_by(func.lower(Program.title), func.lower(Batch.name), func.lower(Student.full_name), Enrollment.enrollment_code)


def _trainers(user: User, f: Filters):
    """(f) per trainer: batches, counted students, pooled attendance, average progress, submissions waiting to be graded."""
    batches, att = _batches(user, f), progress.attendance()
    seats = (
        select(
            batches.c.trainer_id, func.count(distinct(batches.c.id)).label("batches"), func.count(distinct(Enrollment.student_id)).filter(counted).label("students"),
            func.sum(att.c.attended).label("attended"), func.sum(att.c.marked).label("marked"),
            func.avg(Enrollment.progress_percent).filter(counted).label("progress"),
        )
        .select_from(batches)
        .outerjoin(Enrollment, Enrollment.batch_id == batches.c.id)
        .outerjoin(att, and_(*_on_seat(att)))
        .where(batches.c.trainer_id.is_not(None))
        .group_by(batches.c.trainer_id)
        .subquery()
    )
    pending = (
        select(batches.c.trainer_id, func.count().label("pending"))
        .select_from(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(batches, batches.c.id == Assignment.batch_id)
        .where(Submission.status == "submitted")
        .group_by(batches.c.trainer_id)
        .subquery()
    )
    return (
        select(
            Trainer.full_name.label("trainer"), seats.c.batches, seats.c.students, progress.percent(seats.c.attended, seats.c.marked).label("attendance_pct"),
            func.round(seats.c.progress, 1).label("average_progress"), func.coalesce(pending.c.pending, 0).label("pending_grading"),
        )
        .select_from(seats)
        .join(Trainer, Trainer.id == seats.c.trainer_id)
        .outerjoin(pending, pending.c.trainer_id == seats.c.trainer_id)
        .order_by(func.lower(Trainer.full_name), Trainer.id)
    )


def _courses(user: User, f: Filters):
    """(g) per course: batches, seats by state, and the seats' paid enrolment fees (`financial`). `from`/`to` narrow the seats by
    enrolment date; a course with a batch in scope still shows, with zeros."""
    batches = _batches(user, f)
    paid = (
        select(Payment.reference_id, func.sum(Payment.amount).label("amount"))
        .where(Payment.status.in_(PAID_STATUSES), Payment.reference_type.in_(ENROLMENT_REFERENCES))
        .group_by(Payment.reference_id)
        .subquery()
    )
    seat_on = [Enrollment.batch_id == batches.c.id]
    if f.date_from:
        seat_on.append(Enrollment.enrolled_on >= f.date_from)
    if f.date_to:
        seat_on.append(Enrollment.enrolled_on <= f.date_to)
    return (
        select(
            Program.title.label("course"), func.count(distinct(batches.c.id)).label("batches"),
            func.count(Enrollment.id).filter(Enrollment.status.not_in(NOT_TAKEN)).label("enrolments"),
            func.count(Enrollment.id).filter(counted, Enrollment.progress_percent < 100).label("active"),
            func.count(Enrollment.id).filter(completed).label("completed"), func.count(Enrollment.id).filter(Enrollment.status.in_(DROPPED)).label("dropped"),
            func.sum(paid.c.amount).label("revenue"),
        )
        .select_from(batches)
        .join(Program, Program.id == batches.c.program_id)
        .outerjoin(Enrollment, and_(*seat_on))
        .outerjoin(paid, paid.c.reference_id == Enrollment.id)
        .group_by(Program.id, Program.title)
        .order_by(func.lower(Program.title), Program.id)
    )


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


def _training(id: str, title: str, description: str, columns: tuple[Column, ...], filters: tuple[str, ...], query, resource: str = "reports.training") -> Report:
    return register(Report(id=id, title=title, description=description, resource=resource, columns=columns, filters=filters,
                           query=query, options=_options))


STUDENT_COLUMNS = (Column("student_code", "Student code"), Column("student", "Student"), Column("course", "Course"), Column("batch", "Batch"),
                   Column("trainer", "Trainer"))
COMPLETION = ("completion_from", "completion_to")

ENROLLMENTS = _training(
    "enrollments", "Enrollments", "One row per student enrolment: course, batch, trainer, enrolment date, status and progress.",
    (
        Column("enrollment_code", "Enrollment code"), Column("student_code", "Student code"), Column("student", "Student"),
        Column("course", "Course"), Column("batch", "Batch"), Column("trainer", "Trainer"), Column("enrolled_on", "Enrolled on"),
        Column("batch_ends", "Batch ends"), Column("status", "Status"), Column("progress", "Progress %"),
    ),
    ("from", "to", "course_id", "batch_id", "trainer_id", "student", "status", "latest", "completion_from", "completion_to"),
    _enrollments,
)
STUDENT_COURSES = _training(
    "student-courses", "Student-wise course report",
    "One row per enrolment with progress, attendance, assignments graded, assessments passed and the certificate. From/To: enrolment date.",
    STUDENT_COLUMNS + (
        Column("enrolled_on", "Enrolled on"), Column("status", "Status"), Column("progress", "Progress %"), Column("attendance_pct", "Attendance %"),
        Column("assignments_graded", "Assignments graded"), Column("assignments_total", "Assignments"), Column("assessments_passed", "Assessments passed"),
        Column("assessments_total", "Assessments"), Column("certificate", "Certificate"),
    ),
    ("from", "to", *SEAT_FILTERS, "latest", *COMPLETION),
    _student_courses,
)
STUDENTS_BY_TRAINER = _training(
    "students-by-trainer", "Students per trainer", "Each trainer's students, batch by batch, with status and progress. From/To: enrolment date.",
    (Column("trainer", "Trainer"), Column("batch", "Batch"), Column("course", "Course"), Column("student_code", "Student code"),
     Column("student", "Student"), Column("status", "Status"), Column("progress", "Progress %")),
    ("from", "to", *SEAT_FILTERS),
    _students_by_trainer,
)
COURSE_COMPLETION = _training(
    "course-completion", "Course completion",
    "One row per batch: students, how many completed (progress 100%), the completion rate and certificates issued. Completion: batch end date.",
    (Column("course", "Course"), Column("batch", "Batch"), Column("trainer", "Trainer"), Column("batch_starts", "Batch starts"),
     Column("batch_ends", "Batch ends"), Column("students", "Students"), Column("completed", "Completed"), Column("completion_pct", "Completion %"),
     Column("certificates", "Certificates")),
    ("course_id", "batch_id", "trainer_id", *COMPLETION),
    _course_completion,
)
COMPLETIONS = _training(
    "completions", "Completions in a period",
    "Students who completed a course (progress 100%) whose batch ends in the completion period, with attendance and certificate.",
    STUDENT_COLUMNS + (Column("batch_ends", "Batch ends"), Column("progress", "Progress %"), Column("attendance_pct", "Attendance %"),
                       Column("certificate", "Certificate")),
    (*COMPLETION, "course_id", "batch_id", "trainer_id", "student", "latest"),
    _completions,
)
ATTENDANCE = _training(
    "attendance", "Attendance",
    "Per student per batch: classes marked, present, absent, late, excused and the attendance % (as certificate eligibility counts it). "
    "From/To: class date.",
    STUDENT_COLUMNS + (Column("marked", "Classes marked"), Column("present", "Present"), Column("absent", "Absent"), Column("late", "Late"),
                       Column("excused", "Excused"), Column("attendance_pct", "Attendance %")),
    ("from", "to", *SEAT_FILTERS),
    _attendance,
)
TRAINERS = _training(
    "trainers", "Trainer report",
    "Per trainer: batches, students, attendance, average progress and submissions waiting to be graded. Completion: batch end date.",
    (Column("trainer", "Trainer"), Column("batches", "Batches"), Column("students", "Students"), Column("attendance_pct", "Attendance %"),
     Column("average_progress", "Average progress %"), Column("pending_grading", "Pending grading")),
    ("course_id", "trainer_id", *COMPLETION),
    _trainers,
)
COURSES = _training(
    "courses", "Course-wise report",
    "Per course: batches, enrolments, active, completed and dropped students, and fees collected. From/To: enrolment date.",
    (Column("course", "Course"), Column("batches", "Batches"), Column("enrolments", "Enrolments"), Column("active", "Active"),
     Column("completed", "Completed"), Column("dropped", "Dropped"), Column("revenue", "Revenue (INR)", "financial")),
    ("from", "to", "course_id", "trainer_id"),
    _courses,
)

# nehn-017 (DEC-SCOPE-310): HR's reports -- the student-wise, completions and attendance reports over the HR population, each gated by the
# grant for its data (`student_progress`, `attendance`), so revoking one removes its report. No financial column; payments are never read.
HR_PROGRESS = _training(
    "hr-progress", "HR student progress",
    "Per student per course: status, progress, attendance, assignments, assessments and the certificate. From/To: enrolment date.",
    STUDENT_COURSES.columns, STUDENT_COURSES.filters, _student_courses, "student_progress",
)
HR_COMPLETIONS = _training(
    "hr-completions", "HR completions",
    "Students who completed a course (progress 100%) whose batch ends in the completion period, with attendance and certificate.",
    COMPLETIONS.columns, COMPLETIONS.filters, _completions, "student_progress",
)
HR_ATTENDANCE = _training(
    "hr-attendance", "HR attendance",
    "Per student per batch: classes marked, present, absent, late, excused and the attendance %. From/To: class date.",
    ATTENDANCE.columns, ATTENDANCE.filters, _attendance, "attendance",
)
