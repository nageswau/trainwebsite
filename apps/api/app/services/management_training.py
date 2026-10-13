"""mgmt-017 (EVID-017 §12, spec TR1-TR16): the training dashboard -- the 11 Training KPIs company-wide and the 7 trainer metrics per
trainer, for an IST period. Each figure is one query grouped by `ROLLUP(batches.trainer_id)`: the trainer rows and the company-wide value
(which also covers batches with no trainer, and counts a student in two trainers' batches once) come from the same statement, so the
query count does not grow with the team. Read-only; only names, counts and shares leave."""

from datetime import date, datetime

from sqlalchemy import Select, and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assessment,
    AssessmentAttempt,
    Attendance,
    Batch,
    Certificate,
    CourseFeedback,
    Enrollment,
    JobApplication,
    JobOffer,
    PlacementProfile,
    Program,
    User,
)
from app.services.bdm_performance import _instants

NOT_TAKEN = ("pending_consent", "rejected")  # TR3: never took the seat
DROPPED = ("withdrawn", "dropped")  # TR10: left it (set by an admin's enrolment edit)
ATTENDED = ("present", "late", "excused")  # TR8: the certificate rule's attended statuses

# (key, label, definition), in §12 order.
KPIS = (
    ("total_courses", "Total courses", "Active courses in the catalogue."),
    ("active_batches", "Active batches", "Batches running now."),
    ("students", "Students", "Students who took a seat in a batch running in the period."),
    ("trainers", "Trainers", "Active trainer accounts."),
    ("attendance_pct", "Attendance", "Classes attended (present, late or excused) out of attendance marked in the period."),
    ("completion_pct", "Completion", "Seats in the period's batches whose course progress reached 100%."),
    ("dropouts", "Dropouts", "Students withdrawn or dropped from a batch running in the period."),
    ("assessments", "Assessments", "Assessments scheduled in the period."),
    ("certifications", "Certifications", "Certificates issued in the period."),
    ("placement_ready", "Placement-ready students", "Students the placement team has marked available for placement."),
    ("placements", "Placements", "Trained students who joined a job in the period."),
)
TRAINER_FIGURES = (
    ("students_trained", "Students trained", "Students who took a seat in the trainer's batches running in the period."),
    ("attendance_pct", "Attendance", "Classes attended out of attendance marked in the period, in the trainer's batches."),
    ("completion_pct", "Completion", "Seats in the trainer's period batches whose course progress reached 100%."),
    ("feedback_avg", "Student feedback", "Average course rating (out of 5) students gave the trainer's period batches."),
    ("assessment_pass_pct", "Assessment results", "Students who passed (best graded attempt at or above the pass mark) the period's assessments."),
    ("batch_performance", "Batch performance", "Average course progress of the seats in the trainer's period batches."),
    ("placements", "Placement outcomes", "Students of any of the trainer's batches who joined a job in the period."),
)

counted = Enrollment.status.not_in(NOT_TAKEN + DROPPED)
not_cancelled = Batch.status != "cancelled"


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _one_decimal(value) -> float | None:
    return None if value is None else round(float(value), 1)


async def _rolled(db: AsyncSession, stmt: Select) -> tuple[dict, tuple]:
    """`stmt` selects (grouping, trainer_id, *values); returns ({trainer_id: values}, company-wide values). ROLLUP always yields the
    company-wide row, even over no rows."""
    per, total = {}, ()
    for grouped, trainer, *values in await db.execute(stmt.group_by(func.rollup(Batch.trainer_id))):
        if grouped:
            total = tuple(values)
        elif trainer is not None:
            per[trainer] = tuple(values)
    return per, total


def _by_trainer(*columns) -> Select:
    return select(func.grouping(Batch.trainer_id), Batch.trainer_id, *columns)


async def dashboard(db: AsyncSession, start: date, end: date, now: datetime) -> dict:
    """Every trainer, active or not (TR15), for the inclusive IST dates `start`..`end`."""
    lo, hi = _instants(start, end)
    in_period = and_(not_cancelled, Batch.start_date <= end, Batch.end_date >= start)  # TR2

    seats = await _rolled(db, _by_trainer(
        func.count(distinct(Batch.id)), func.count(distinct(Enrollment.student_id)).filter(counted), func.count(Enrollment.id).filter(counted),
        func.count(Enrollment.id).filter(counted, Enrollment.progress_percent >= 100), func.count(Enrollment.id).filter(Enrollment.status.in_(DROPPED)),
        func.avg(Enrollment.progress_percent).filter(counted),
    ).select_from(Batch).outerjoin(Enrollment, Enrollment.batch_id == Batch.id).where(in_period))  # fmt: skip
    attendance = await _rolled(db, _by_trainer(func.count(), func.count().filter(Attendance.status.in_(ATTENDED)))
                               .join(Attendance, Attendance.batch_id == Batch.id)
                               .where(in_period, Attendance.session_date >= start, Attendance.session_date <= end))  # fmt: skip
    feedback = await _rolled(db, _by_trainer(func.avg(CourseFeedback.rating), func.count()).join(CourseFeedback, CourseFeedback.batch_id == Batch.id).where(in_period))
    best = (
        select(AssessmentAttempt.assessment_id, AssessmentAttempt.student_id, func.max(AssessmentAttempt.percentage).label("best"))
        .where(AssessmentAttempt.status == "graded", AssessmentAttempt.percentage.is_not(None))
        .group_by(AssessmentAttempt.assessment_id, AssessmentAttempt.student_id)
        .subquery()
    )
    results = await _rolled(db, _by_trainer(func.count(), func.count().filter(best.c.best >= Assessment.pass_percent))
                            .join(Assessment, Assessment.batch_id == Batch.id).join(best, best.c.assessment_id == Assessment.id)
                            .where(in_period, Assessment.status != "draft", Assessment.scheduled_at >= lo, Assessment.scheduled_at < hi))  # fmt: skip
    placed = await _rolled(db, _by_trainer(func.count(distinct(Enrollment.student_id)))
                           .join(Enrollment, Enrollment.batch_id == Batch.id)
                           .join(JobApplication, JobApplication.student_id == Enrollment.student_id)
                           .join(JobOffer, JobOffer.application_id == JobApplication.id)
                           .where(not_cancelled, counted, JobOffer.joining_status == "joined", JobOffer.actual_joining_date >= start,
                                  JobOffer.actual_joining_date <= end))  # fmt: skip

    counts = (
        select(func.count()).where(Program.active.is_(True)),  # TR4
        select(func.count()).where(Batch.status == "active"),  # TR5
        select(func.count()).where(User.role == "trainer", User.active.is_(True)),  # TR7
        select(func.count()).select_from(Assessment).where(Assessment.status != "draft", Assessment.scheduled_at >= lo, Assessment.scheduled_at < hi),  # TR11
        select(func.count()).where(Certificate.status == "issued", Certificate.issued_on >= start, Certificate.issued_on <= end),  # TR12
        select(func.count()).select_from(PlacementProfile).join(User, User.id == PlacementProfile.student_id)
        .where(PlacementProfile.available.is_(True), PlacementProfile.withdrawn.is_(False), User.active.is_(True)),  # TR13
    )  # fmt: skip
    courses, active_batches, trainers, assessments, certifications, ready = (await db.execute(select(*(c.scalar_subquery() for c in counts)))).one()
    _, students, taken, completed, dropouts, _ = seats[1]
    marked, attended = attendance[1]

    people = (await db.execute(select(User.id, User.full_name, User.active).where(User.role == "trainer").order_by(func.lower(User.full_name), User.id))).all()
    rows = []
    for p in people:
        batches, trained, own_taken, own_completed, _, progress = seats[0].get(p.id, (0, 0, 0, 0, 0, None))
        own_marked, own_attended = attendance[0].get(p.id, (0, 0))
        rating, responses = feedback[0].get(p.id, (None, 0))
        graded, passed = results[0].get(p.id, (0, 0))
        rows.append({
            "id": p.id, "full_name": p.full_name, "active": p.active, "batches": batches, "students_trained": trained,
            "attendance_pct": _pct(own_attended, own_marked), "completion_pct": _pct(own_completed, own_taken),
            "feedback_avg": _one_decimal(rating), "feedback_count": responses, "assessment_pass_pct": _pct(passed, graded),
            "batch_performance": _one_decimal(progress), "placements": placed[0].get(p.id, (0,))[0],
        })  # fmt: skip

    values = {
        "total_courses": courses, "active_batches": active_batches, "students": students, "trainers": trainers,
        "attendance_pct": _pct(attended, marked), "completion_pct": _pct(completed, taken), "dropouts": dropouts, "assessments": assessments,
        "certifications": certifications, "placement_ready": ready, "placements": placed[1][0],
    }  # fmt: skip
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "kpis": [{"key": key, "label": label, "definition": text, "value": values[key]} for key, label, text in KPIS],
        "trainer_figures": [{"key": key, "label": label, "definition": text} for key, label, text in TRAINER_FIGURES],
        "trainers": rows,
    }
