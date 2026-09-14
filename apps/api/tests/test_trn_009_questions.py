"""TRN-009 -- Q&A response (PRD-TRN-010).

DATA_MODEL.md §4.8 describes `QuestionThread`/`QuestionReply` as "carries over" from the
reference implementation, but neither table -- nor any Q&A model -- existed anywhere in
the codebase, the same "carries over but never existed" pattern already found for
STU-005's `assigned_to_user_id` and STU-008's `CourseFeedback`. Fully net-new: models,
migration (`0013_question_threads`), student raise/list endpoints, trainer list/reply
endpoints, portal sections, and UI on both sides. Covers TRN-009-AC01 (trainer answers,
student sees the reply), TRN-009-AC02 (only the assigned trainer may reply; replies show
in order), and TRN-009-AC03 (RBAC at the API layer).
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, Program, QuestionThread, User


async def _create_trainer(db_session, *, email_prefix: str = "trn009-trainer") -> User:
    trainer = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Question Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session, *, email_prefix: str = "trn009-student") -> User:
    student = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Question Student",
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
        title=f"TRN-009 Test Program {uuid.uuid4().hex[:6]}",
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
async def test_student_raises_a_question_and_trainer_replies_in_order(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, student.email)
    raise_response = await client.post("/api/v1/workflows/it/student/questions", json={"batch_id": str(batch.id), "subject": "Deadline?", "body": "When is Assignment 2 due?"})
    assert raise_response.status_code == 201
    thread_id = raise_response.json()["id"]

    await _login(client, trainer.email)
    trainer_list = await client.get("/api/v1/workflows/it/trainer/questions")
    assert trainer_list.status_code == 200
    thread = next(t for t in trainer_list.json() if t["id"] == thread_id)
    assert thread["student"] == "Question Student"

    first_reply = await client.post(f"/api/v1/workflows/it/trainer/questions/{thread_id}/replies", json={"body": "Next Friday."})
    assert first_reply.status_code == 201
    second_reply = await client.post(f"/api/v1/workflows/it/trainer/questions/{thread_id}/replies", json={"body": "Actually, extended to Monday."})
    assert second_reply.status_code == 201

    await _login(client, student.email)
    student_list = await client.get("/api/v1/workflows/it/student/questions")
    assert student_list.status_code == 200
    student_thread = next(t for t in student_list.json() if t["id"] == thread_id)
    bodies = [r["body"] for r in student_thread["replies"]]
    assert bodies == ["Next Friday.", "Actually, extended to Monday."]


@pytest.mark.asyncio
async def test_question_for_a_batch_not_enrolled_in_is_rejected(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/it/student/questions", json={"batch_id": str(batch.id), "subject": "Hi", "body": "Can I join late?"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_only_the_assigned_trainer_can_reply(db_session, client):
    owner = await _create_trainer(db_session, email_prefix="trn009-owner")
    outsider = await _create_trainer(db_session, email_prefix="trn009-outsider")
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, owner)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    thread = QuestionThread(student_id=student.id, batch_id=batch.id, subject="Q", body="Question body")
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    await _login(client, outsider.email)
    response = await client.post(f"/api/v1/workflows/it/trainer/questions/{thread.id}/replies", json={"body": "Hijacked reply"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_student_role_cannot_raise_a_question(db_session, client):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)

    await _login(client, trainer.email)
    response = await client.post("/api/v1/workflows/it/student/questions", json={"batch_id": str(batch.id), "subject": "Hi", "body": "Test"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reply_to_unknown_thread_is_404(db_session, client):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)
    response = await client.post(f"/api/v1/workflows/it/trainer/questions/{uuid.uuid4()}/replies", json={"body": "Nope"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_question_endpoints_require_authentication(client):
    assert (await client.post("/api/v1/workflows/it/student/questions", json={"batch_id": str(uuid.uuid4()), "subject": "S", "body": "B"})).status_code == 401
    assert (await client.get("/api/v1/workflows/it/trainer/questions")).status_code == 401
    assert (await client.post(f"/api/v1/workflows/it/trainer/questions/{uuid.uuid4()}/replies", json={"body": "B"})).status_code == 401
