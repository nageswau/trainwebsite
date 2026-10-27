"""nehn-028 -- the trainer's per-student progress view (DEC-SCOPE-308; spec
docs/superpowers/specs/2026-10-27-nehn-028-trainer-progress-view-design.md, API §12HF, RBAC §2.219): one row per seated enrolment of a
batch with attendance, assignments, assessments, progress and certificate eligibility -- the same numbers as the eligibility endpoint
(AC1), at-risk students flagged (AC2), an honest subtitle (AC3), and only the trainer's own batches (AC4)."""

import datetime
import uuid

import pytest

from app.models import Assessment, AssessmentAttempt, Assignment, Attendance, Batch, Certificate, Enrollment, Payment, Program, Submission, User
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role, login

DUE = datetime.datetime(2026, 1, 10, tzinfo=datetime.UTC)


def _url(batch_id) -> str:
    return f"/api/v1/workflows/it/batches/{batch_id}/progress"


async def _batch(db) -> tuple[Batch, User]:
    tag = uuid.uuid4().hex[:8]
    trainer = await make_user(db, "trainer", "it")
    program = Program(
        slug=f"n028-{tag}",
        title=f"N028 Programme {tag}",
        category="Testing",
        summary="-",
        duration="1 month",
        eligibility="-",
        fees=1000,
        certification="-",
        placement_assistance="-",
        trainer_name="-",
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"N028-{tag}",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
        schedule="-",
        capacity=40,
        enrollment_open=True,
        status="active",
    )
    db.add(batch)
    await db.commit()
    return batch, trainer


async def _student(db, batch: Batch, *, attendance: tuple[str, ...] = (), progress: int = 0, status: str = "active", name: str | None = None) -> Enrollment:
    tag = uuid.uuid4().hex[:8]
    student = await make_user(db, "it_student", "it", name=name or f"Learner {tag}")
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N028-{tag}", status=status, progress_percent=progress)
    db.add(enrollment)
    for day, mark in enumerate(attendance):
        db.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=day), status=mark))
    await db.commit()
    await db.refresh(enrollment)
    return enrollment


def _row(body: dict, enrollment: Enrollment) -> dict:
    return next(row for row in body["students"] if row["enrollment_id"] == str(enrollment.id))


# --- AC4: scope -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_own_trainer_sees_the_batch(client, db_session):
    batch, trainer = await _batch(db_session)
    enrollment = await _student(db_session, batch, attendance=("present",), name="Asha Rao")
    await login(client, trainer)
    response = await client.get(_url(batch.id))
    assert response.status_code == 200
    body = response.json()
    assert body["batch"]["id"] == str(batch.id) and body["batch"]["name"] == batch.name and body["batch"]["program"].startswith("N028 Programme")
    assert body["rules"] == {"min_progress_percent": 100, "min_attendance_percent": 75}
    row = _row(body, enrollment)
    student = await db_session.get(User, enrollment.student_id)
    assert row["student"] == "Asha Rao" and row["student_id"] == str(student.id) and row["student_code"] == student.student_code
    assert row["enrollment_code"] == enrollment.enrollment_code and row["status"] == "active"


@pytest.mark.asyncio
async def test_another_trainers_batch_is_403(client, db_session):
    batch, _ = await _batch(db_session)
    await _student(db_session, batch)
    _, other = await _batch(db_session)
    await login(client, other)
    assert (await client.get(_url(batch.id))).status_code == 403


@pytest.mark.asyncio
async def test_unknown_batch_is_404(client, db_session):
    _, trainer = await _batch(db_session)
    await login(client, trainer)
    assert (await client.get(_url(uuid.uuid4()))).status_code == 404


@pytest.mark.asyncio
async def test_it_admin_sees_any_batch(client, db_session):
    batch, _ = await _batch(db_session)
    enrollment = await _student(db_session, batch)
    await as_role(client, db_session, "it_admin", "it")
    response = await client.get(_url(batch.id))
    assert response.status_code == 200
    assert _row(response.json(), enrollment)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("counselor", "it"), ("coordinator", "it"), ("trainer", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    batch, _ = await _batch(db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(_url(batch.id))).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    batch, _ = await _batch(db_session)
    assert (await client.get(_url(batch.id))).status_code == 401


# --- AC1: the eligibility numbers ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rows_match_the_eligibility_endpoint(client, db_session):
    batch, trainer = await _batch(db_session)
    weak = await _student(db_session, batch, attendance=("present", "absent", "late", "absent"), progress=40)
    strong = await _student(db_session, batch, attendance=("present", "present", "excused", "present"), progress=100)
    graded = Assignment(batch_id=batch.id, title="A1", description="-", due_date=DUE, published=True)
    pending = Assignment(batch_id=batch.id, title="A2", description="-", due_date=DUE, published=True)
    draft = Assignment(batch_id=batch.id, title="Draft", description="-", due_date=DUE, published=False)
    exam = Assessment(batch_id=batch.id, title="Exam", scheduled_at=DUE, pass_percent=50, status="published")
    db_session.add_all([graded, pending, draft, exam])
    await db_session.flush()
    for enrollment in (weak, strong):
        db_session.add(Submission(assignment_id=graded.id, student_id=enrollment.student_id, status="graded", score=80))
    db_session.add(Submission(assignment_id=pending.id, student_id=weak.student_id, status="submitted"))
    db_session.add(Submission(assignment_id=pending.id, student_id=strong.student_id, status="graded", score=90))
    db_session.add(AssessmentAttempt(assessment_id=exam.id, student_id=weak.student_id, status="graded", percentage=30))
    db_session.add(AssessmentAttempt(assessment_id=exam.id, student_id=weak.student_id, status="graded", percentage=45, attempt_no=2))  # best of two
    db_session.add(AssessmentAttempt(assessment_id=exam.id, student_id=strong.student_id, status="graded", percentage=70))
    await db_session.commit()

    await login(client, trainer)
    body = (await client.get(_url(batch.id))).json()
    for enrollment in (weak, strong):
        eligibility = (await client.get(f"/api/v1/workflows/it/certificates/eligibility/{enrollment.id}")).json()
        row = _row(body, enrollment)
        for key in ("progress_percent", "attendance_percent", "assignments_graded", "assignments_total", "assessments_passed", "assessments_total", "eligible"):
            assert row[key] == eligibility[key], key
        assert row["certificate_issued"] == eligibility["certificate_issued"]

    weak_row, strong_row = _row(body, weak), _row(body, strong)
    assert weak_row["attendance_percent"] == 50 and weak_row["attendance_sessions"] == 4
    assert (weak_row["assignments_submitted"], weak_row["assignments_graded"], weak_row["assignments_total"]) == (2, 1, 2)  # the draft is not counted
    assert (weak_row["assessments_passed"], weak_row["assessments_total"]) == (0, 1)
    assert weak_row["eligible"] is False
    assert weak_row["reasons"] == ["Progress 40% (needs 100%)", "Attendance 50% (needs 75%)", "1 of 2 assignments not graded", "1 of 1 assessment not passed"]
    assert strong_row["eligible"] is True and strong_row["reasons"] == [] and strong_row["attendance_percent"] == 100


@pytest.mark.asyncio
async def test_pending_fee_is_a_reason_without_the_amount(client, db_session):
    batch, trainer = await _batch(db_session)
    enrollment = await _student(db_session, batch, attendance=("present",), progress=100)
    db_session.add(Payment(user_id=enrollment.student_id, division="it", reference_type="enrollment", amount=4999, status="pending"))
    await db_session.commit()
    await login(client, trainer)
    row = _row((await client.get(_url(batch.id))).json(), enrollment)
    assert row["fee_clear"] is False and row["eligible"] is False
    assert row["reasons"] == ["Fee payment pending"]
    assert "pending_fee" not in row and "4999" not in str(row)


@pytest.mark.asyncio
async def test_issued_certificate_is_marked(client, db_session):
    batch, trainer = await _batch(db_session)
    enrollment = await _student(db_session, batch, attendance=("present",), progress=100)
    db_session.add(
        Certificate(
            enrollment_id=enrollment.id,
            student_id=enrollment.student_id,
            program_id=batch.program_id,
            certificate_no=f"N028-{uuid.uuid4().hex[:8]}",
            verification_code=uuid.uuid4().hex[:16],
            issued_on=datetime.date(2026, 2, 1),
        )
    )
    await db_session.commit()
    await login(client, trainer)
    assert _row((await client.get(_url(batch.id))).json(), enrollment)["certificate_issued"] is True


# --- AC2: the attendance risk flag ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_the_threshold_is_at_risk(client, db_session):
    batch, trainer = await _batch(db_session)
    risky = await _student(db_session, batch, attendance=("present", "absent", "absent", "present"))  # 50%
    edge = await _student(db_session, batch, attendance=("present", "present", "present", "absent"))  # 75%: at the threshold, not below
    await login(client, trainer)
    body = (await client.get(_url(batch.id))).json()
    assert _row(body, risky)["at_risk"] is True
    assert _row(body, edge)["at_risk"] is False


@pytest.mark.asyncio
async def test_no_sessions_yet_is_not_at_risk(client, db_session):
    batch, trainer = await _batch(db_session)
    enrollment = await _student(db_session, batch, progress=100)
    await login(client, trainer)
    row = _row((await client.get(_url(batch.id))).json(), enrollment)
    assert row["attendance_sessions"] == 0 and row["attendance_percent"] == 0  # as the eligibility endpoint says
    assert row["at_risk"] is False
    assert row["reasons"] == ["No attendance recorded yet"]


# --- edge cases -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dropped_rows_are_returned_and_unseated_are_not(client, db_session):
    batch, trainer = await _batch(db_session)
    active = await _student(db_session, batch, name="A Active")
    dropped = await _student(db_session, batch, status="dropped", name="B Dropped")
    pending = await _student(db_session, batch, status="pending_consent")
    await login(client, trainer)
    body = (await client.get(_url(batch.id))).json()
    ids = [row["enrollment_id"] for row in body["students"]]
    assert ids == [str(active.id), str(dropped.id)]  # by name; never-seated enrolments are left out
    assert _row(body, dropped)["status"] == "dropped"
    assert str(pending.id) not in ids


@pytest.mark.asyncio
async def test_an_empty_batch(client, db_session):
    batch, trainer = await _batch(db_session)
    await login(client, trainer)
    response = await client.get(_url(batch.id))
    assert response.status_code == 200 and response.json()["students"] == []


# --- AC3: the page says what it shows ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_student_progress_section_subtitle(client, db_session):
    batch, trainer = await _batch(db_session)
    await _student(db_session, batch)
    await login(client, trainer)
    body = (await client.get("/api/v1/portal/it/trainer/student-progress")).json()
    assert body["title"] == "Student Progress"
    assert body["subtitle"] == "Attendance, assignments, assessments, progress and certificate eligibility for each student in your batches."
    assert body["rows"] == []  # header-only: the progress table reads its own endpoint
