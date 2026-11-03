"""itc-031 (DEC-SCOPE-358) -- the derived lifecycle stage of an IT enrolment (`services/it_lifecycle.py`): each component computed from
its source record (fee account, enrolment dates, risk flag, certificate, HR review, job application), the display precedence (L3), the
two hand-set facts (L4) and the history writer (L6: a row with actor and time when the stage changes, none when it does not)."""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.models import (
    Batch,
    Certificate,
    Company,
    Enrollment,
    EnrollmentLifecycleHistory,
    HrReviewTask,
    Job,
    JobApplication,
    Payment,
    Program,
    StudentRiskFlag,
    User,
)  # fmt: skip
from app.services import it_lifecycle
from app.services.applications import candidate_for_student
from tests.tel004_helpers import make_user

pytestmark = pytest.mark.asyncio

TODAY = datetime.date.today()
FUTURE = TODAY + datetime.timedelta(days=30)
PAST = TODAY - datetime.timedelta(days=30)


async def enrolled(db, *, student: User | None = None, start: datetime.date = FUTURE, fee: float | None = 40000, status: str = "active") -> Enrollment:
    """An IT enrolment in a fresh batch starting on `start`; `fee` billed as one pending `enrollment_fee` (None bills nothing)."""
    tag = uuid.uuid4().hex[:8]
    student = student or await make_user(db, "it_student", "it")
    program = Program(slug=f"i031-{tag}", title=f"I031 Course {tag}", category="Testing", summary="-", duration="3 months", eligibility="-",
                      fees=fee or 0, certification="-", placement_assistance="-", trainer_name="-")  # fmt: skip
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"I031-{tag}", start_date=start, end_date=start + datetime.timedelta(days=90), schedule="-", capacity=40,
                  enrollment_open=True, status="active")  # fmt: skip
    db.add(batch)
    await db.flush()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"I031-{tag}", status=status)
    db.add(enrollment)
    await db.flush()
    if fee:
        db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=fee, status="pending", is_manual=True))
    await db.commit()
    return enrollment


async def pay(db, enrollment: Enrollment, amount: float) -> None:
    """Splits the pending bill the way `record_payment` does: the bill keeps the rest, a paid row holds `amount`."""
    bill = await db.scalar(select(Payment).where(Payment.reference_id == enrollment.id, Payment.status == "pending"))
    bill.amount = float(bill.amount) - amount
    if float(bill.amount) == 0:
        bill.status, bill.amount = "paid", amount
    else:
        db.add(Payment(user_id=enrollment.student_id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=amount, status="paid"))
    await db.commit()


async def stage(db, enrollment: Enrollment) -> str:
    return (await it_lifecycle.derive_many(db, [enrollment.id]))[enrollment.id]["stage"]


async def components(db, enrollment: Enrollment) -> dict:
    return (await it_lifecycle.derive_many(db, [enrollment.id]))[enrollment.id]["components"]


async def flag(db, enrollment: Enrollment) -> None:
    db.add(StudentRiskFlag(enrollment_id=enrollment.id, student_id=enrollment.student_id, batch_id=enrollment.batch_id, reasons=["attendance"],
                           raised_at=datetime.datetime.now(datetime.UTC)))  # fmt: skip
    await db.commit()


async def hr_task(db, student_id, stage_name: str) -> None:
    db.add(HrReviewTask(student_user_id=student_id, stage=stage_name, resume_version=1, checklist=[]))
    await db.commit()


async def application(db, student: User, status: str) -> JobApplication:
    creator = await make_user(db, "placement_team", "it")
    company = Company(name=f"I031 Co {uuid.uuid4().hex[:6]}", created_by_user_id=creator.id)
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title="Java", location="Pune", description="-", skills=[], status="sourcing", created_by_user_id=creator.id)
    db.add(job)
    await db.flush()
    candidate = await candidate_for_student(db, student)
    row = JobApplication(job_id=job.id, candidate_id=candidate.id, student_id=student.id, added_by_user_id=creator.id, status=status)
    db.add(row)
    await db.commit()
    return row


async def history(db, enrollment: Enrollment) -> list[tuple]:
    rows = await db.scalars(select(EnrollmentLifecycleHistory).where(EnrollmentLifecycleHistory.enrollment_id == enrollment.id)
                            .order_by(EnrollmentLifecycleHistory.created_at, EnrollmentLifecycleHistory.id))  # fmt: skip
    return [(r.from_stage, r.to_stage, r.cause, r.actor_user_id) for r in rows.all()]


# --- fee track (before training starts) -------------------------------------------------------------------------------------------


async def test_the_fee_track_moves_enrolled_fee_pending_partially_paid_paid(db_session):
    assert await stage(db_session, await enrolled(db_session, fee=None)) == "enrolled"
    enrollment = await enrolled(db_session)
    assert await stage(db_session, enrollment) == "fee_pending"
    await pay(db_session, enrollment, 10000)
    assert await stage(db_session, enrollment) == "partially_paid"
    await pay(db_session, enrollment, 30000)  # the final payment confirmed: Partially Paid -> Paid
    assert await stage(db_session, enrollment) == "paid"


async def test_an_unbilled_enrolment_has_no_fee_component_but_reads_enrolled(db_session):
    """QA31-01: "Not billed" is no fee state -- the component is empty (the card says "Not billed"), the stage still reads Enrolled."""
    enrollment = await enrolled(db_session, fee=None, start=PAST)
    assert await components(db_session, enrollment) == {"fee": None, "training": "training_active", "placement": None}
    assert await stage(db_session, await enrolled(db_session, fee=None)) == "enrolled"


async def test_a_pending_consent_enrolment_follows_the_fee_track(db_session):
    assert await stage(db_session, await enrolled(db_session, status="pending_consent")) == "fee_pending"


# --- training track ---------------------------------------------------------------------------------------------------------------


async def test_a_started_enrolment_is_training_active_and_keeps_its_fee_component(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    assert await stage(db_session, enrollment) == "training_active"  # E: concurrent with Fee Pending -- the component keeps it visible
    assert await components(db_session, enrollment) == {"fee": "fee_pending", "training": "training_active", "placement": None}


async def test_a_student_start_date_override_decides_when_training_starts(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    enrollment.start_date = FUTURE
    await db_session.commit()
    assert await stage(db_session, enrollment) == "fee_pending"


async def test_an_open_risk_flag_makes_it_at_risk_and_a_certificate_completes_it(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    await flag(db_session, enrollment)
    assert await stage(db_session, enrollment) == "at_risk"
    db_session.add(Certificate(student_id=enrollment.student_id, program_id=await db_session.scalar(select(Batch.program_id).where(Batch.id == enrollment.batch_id)),
                               enrollment_id=enrollment.id, certificate_no=f"C-{uuid.uuid4().hex[:10]}", verification_code=uuid.uuid4().hex,
                               issued_on=TODAY, status="issued"))  # fmt: skip
    await db_session.commit()
    assert await stage(db_session, enrollment) == "completed"


async def test_a_completed_status_completes_it(db_session):
    assert await stage(db_session, await enrolled(db_session, start=PAST, status="completed")) == "completed"


# --- placement track (the student's newest seated enrolment) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hr_stage", "expected"),
    [("resume_received", "resume_submitted"), ("under_review", "hr_screening"), ("changes_requested", "hr_screening"), ("screening", "hr_screening"),
     ("interview_ready", "interview"), ("completed", "interview"), ("withdrawn", "training_active")],
)  # fmt: skip
async def test_the_hr_review_stage_maps_to_the_placement_track(db_session, hr_stage, expected):
    enrollment = await enrolled(db_session, start=PAST)
    await hr_task(db_session, enrollment.student_id, hr_stage)
    assert await stage(db_session, enrollment) == expected


async def test_applications_give_interview_then_placed_and_only_the_newest_enrolment_carries_them(db_session):
    older = await enrolled(db_session, start=PAST)
    student = await db_session.get(User, older.student_id)
    newer = await enrolled(db_session, student=student, start=PAST)
    app_row = await application(db_session, student, "interview")
    assert await stage(db_session, newer) == "interview" and await stage(db_session, older) == "training_active"
    app_row.status = "joined"
    await db_session.commit()
    assert await stage(db_session, newer) == "placed"


# --- precedence and the hand-set facts (L3, L4) -----------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["rejected", "withdrawn", "dropped"])
async def test_an_enrolment_that_ended_is_closed(db_session, status):
    assert await stage(db_session, await enrolled(db_session, start=PAST, status=status)) == "closed"


async def test_overrides_closed_beats_everything_and_not_placed_yields_to_a_joining(db_session):
    enrollment = await enrolled(db_session, start=PAST)
    enrollment.lifecycle_override = "not_placed"
    await db_session.commit()
    assert await stage(db_session, enrollment) == "not_placed"
    await application(db_session, await db_session.get(User, enrollment.student_id), "joined")
    assert await stage(db_session, enrollment) == "placed"  # the source record wins over the hand-set "Not Placed"
    enrollment.lifecycle_override = "closed"
    await db_session.commit()
    assert await stage(db_session, enrollment) == "closed"


def test_the_student_safe_view_hides_at_risk():
    assert it_lifecycle.view("at_risk") == {"stage": "at_risk", "stage_label": "At risk"}
    assert it_lifecycle.view("at_risk", safe=True) == {"stage": "training_active", "stage_label": "Training active"}
    assert it_lifecycle.view("paid", safe=True) == {"stage": "paid", "stage_label": "Paid"}
    assert set(it_lifecycle.LABELS) == set(it_lifecycle.STAGES)


async def test_derivation_is_batched_for_many_enrolments(db_session):
    rows = [await enrolled(db_session) for _ in range(3)] + [await enrolled(db_session, start=PAST)]
    out = await it_lifecycle.derive_many(db_session, [r.id for r in rows])
    assert [out[r.id]["stage"] for r in rows] == ["fee_pending", "fee_pending", "fee_pending", "training_active"]
    assert await it_lifecycle.derive_many(db_session, []) == {}


# --- the history writer (L6) ------------------------------------------------------------------------------------------------------


async def test_sync_writes_a_row_only_when_the_stage_changes_with_actor_and_cause(db_session):
    actor = await make_user(db_session, "it_admin", "it")
    enrollment = await enrolled(db_session)
    await it_lifecycle.sync(db_session, [enrollment.id], actor=None, cause="enrolment")
    await db_session.commit()
    await it_lifecycle.sync(db_session, [enrollment.id], actor=actor, cause="fee")  # nothing changed: no row
    await db_session.commit()
    assert await history(db_session, enrollment) == [(None, "fee_pending", "enrolment", None)]
    await pay(db_session, enrollment, 40000)
    await it_lifecycle.sync(db_session, [enrollment.id], actor=actor, cause="fee")
    await db_session.commit()
    assert await history(db_session, enrollment) == [(None, "fee_pending", "enrolment", None), ("fee_pending", "paid", "fee", actor.id)]


async def test_sync_students_and_sync_all_reach_every_enrolment(db_session):
    first = await enrolled(db_session)
    student = await db_session.get(User, first.student_id)
    second = await enrolled(db_session, student=student, start=PAST)
    await it_lifecycle.sync_students(db_session, [student.id], actor=None, cause="hr_review")
    await db_session.commit()
    assert [h[1] for h in await history(db_session, first)] == ["fee_pending"] and [h[1] for h in await history(db_session, second)] == ["training_active"]
    third = await enrolled(db_session, start=PAST)
    await it_lifecycle.sync_all(db_session)
    assert await history(db_session, third) == [(None, "training_active", "daily_check", None)]
