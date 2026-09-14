"""STU-008 -- Feedback submission (PRD-STU-009).

DATA_MODEL.md §4.6 describes `CourseFeedback` as "carries over" from the reference
implementation; no such table, or any other feedback model, actually existed anywhere in
the codebase before this -- the same "doc says X carries over but never existed" pattern
already found once for STU-005's `assigned_to_user_id`. Net-new model, migration
(`0011_course_feedback`), endpoint, and `FeedbackSubmissionPanel.tsx`. An anonymous-
submission option is an explicitly unconfirmed PRD open item (PRD-STU-009) and is
deliberately not implemented here.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Batch, CourseFeedback, Enrollment, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"fb-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Feedback Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session) -> User:
    student = User(
        email=f"fb-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Feedback Student",
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
        title=f"STU-008 Test Program {uuid.uuid4().hex[:6]}",
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


@pytest.mark.asyncio
async def test_enrolled_student_submits_feedback(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(batch.id), "rating": 5, "comments": "Great trainer."})
    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 5
    assert body["comments"] == "Great trainer."

    stored = await db_session.scalar(select(CourseFeedback).where(CourseFeedback.student_id == student.id, CourseFeedback.batch_id == batch.id))
    assert stored is not None
    assert stored.rating == 5


@pytest.mark.asyncio
async def test_feedback_for_a_batch_not_enrolled_in_is_rejected(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    # deliberately no Enrollment created

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(batch.id), "rating": 4})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rating_out_of_range_is_rejected(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(batch.id), "rating": 6})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_student_role_is_rejected(db_session, client):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)

    await _login(client, trainer.email)
    response = await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(batch.id), "rating": 3})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_feedback_listing_reflects_submission_status(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, student.email)
    before = await client.get("/api/v1/portal/it/student/feedback")
    assert before.status_code == 200
    row = next(r for r in before.json()["rows"] if r["batch"] == batch.name)
    assert row["status"] == "Not yet submitted"

    await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(batch.id), "rating": 5})

    after = await client.get("/api/v1/portal/it/student/feedback")
    row = next(r for r in after.json()["rows"] if r["batch"] == batch.name)
    assert row["status"] == "Submitted"


@pytest.mark.asyncio
async def test_feedback_submission_requires_authentication(client):
    response = await client.post("/api/v1/workflows/it/student/feedback", json={"batch_id": str(uuid.uuid4()), "rating": 5})
    assert response.status_code == 401
