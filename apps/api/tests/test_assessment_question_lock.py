"""RAID.md I-18 sub-item 3: a question could previously be added to an assessment even
after a student had already started (or finished) an attempt against it -- unfair to
whoever already took it, since the new question was never part of what they saw. Adds a
lock: once any `AssessmentAttempt` row exists for an assessment, `POST
.../questions`/`.../questions/bulk` are rejected (409), and `GET
/workflows/it/trainer/assessments` now reports a real `attempt_count` per assessment so
the trainer UI can disable the option before the trainer even tries.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"lock-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Lock Test Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session) -> User:
    student = User(
        email=f"lock-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Lock Test Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_batch(db_session, trainer: User) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Lock Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


async def _setup_assessment(client, db_session, trainer: User) -> tuple[str, Batch, User]:
    batch = await _create_batch(db_session, trainer)
    await _login(client, trainer.email)
    created = await client.post(
        "/api/v1/workflows/it/trainer/assessments",
        json={"batch_id": str(batch.id), "title": "Lock Test Quiz", "scheduled_at": "2027-06-01T10:00:00Z", "status": "scheduled"},
    )
    assert created.status_code == 201
    return created.json()["id"], batch, trainer


@pytest.mark.asyncio
async def test_a_question_can_be_added_before_any_attempt_exists(client, db_session):
    trainer = await _create_trainer(db_session)
    assessment_id, _batch, _trainer = await _setup_assessment(client, db_session, trainer)

    response = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Before any attempt.", "max_score": 5, "position": 1},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_adding_a_question_after_a_student_started_an_attempt_is_rejected(client, db_session):
    trainer = await _create_trainer(db_session)
    assessment_id, batch, _trainer = await _setup_assessment(client, db_session, trainer)
    student = await _create_student(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    # An assessment needs at least one question before a student can meaningfully start
    # it in the real product, but the lock itself must trigger purely off attempt
    # existence -- add one question first (still unlocked), then start the attempt.
    first = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Original question.", "max_score": 5, "position": 1},
    )
    assert first.status_code == 201

    await _login(client, student.email)
    start = await client.post(f"/api/v1/workflows/it/assessments/{assessment_id}/attempts")
    assert start.status_code == 201

    await _login(client, trainer.email)
    blocked = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Sneaked in after the student started.", "max_score": 5, "position": 2},
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_bulk_add_is_also_rejected_once_an_attempt_exists(client, db_session):
    trainer = await _create_trainer(db_session)
    assessment_id, batch, _trainer = await _setup_assessment(client, db_session, trainer)
    student = await _create_student(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Original question.", "max_score": 5, "position": 1},
    )
    await _login(client, student.email)
    await client.post(f"/api/v1/workflows/it/assessments/{assessment_id}/attempts")

    await _login(client, trainer.email)
    response = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions/bulk",
        json=[{"question_type": "text", "prompt": "Bulk sneak-in.", "max_score": 5, "position": 2}],
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_assessment_list_reports_a_real_attempt_count(client, db_session):
    trainer = await _create_trainer(db_session)
    assessment_id, batch, _trainer = await _setup_assessment(client, db_session, trainer)
    student = await _create_student(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()
    await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Q1.", "max_score": 5, "position": 1},
    )

    before = await client.get("/api/v1/workflows/it/trainer/assessments")
    row_before = next(a for a in before.json() if a["id"] == assessment_id)
    assert row_before["attempt_count"] == 0

    await _login(client, student.email)
    await client.post(f"/api/v1/workflows/it/assessments/{assessment_id}/attempts")

    await _login(client, trainer.email)
    after = await client.get("/api/v1/workflows/it/trainer/assessments")
    row_after = next(a for a in after.json() if a["id"] == assessment_id)
    assert row_after["attempt_count"] == 1
