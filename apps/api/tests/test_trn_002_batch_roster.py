"""TRN-002 -- Batch detail (roster and schedule).

`GET /workflows/it/trainer/context` already returned the trainer's own batches and
active enrolments (untested until now); it was missing schedule/status detail
(start/end date, status, mode, timezone) beyond what the batch-picker dropdowns
elsewhere needed. Covers: roster strictly scoped per batch (a student in one batch never
leaks into another batch's roster, even for the same trainer), schedule/status fields are
present, and RBAC (own batches only, auth required).
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Roster Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch(db_session, trainer: User, *, name: str) -> Batch:
    # RAID.md I-25: `title` was a plain hardcoded string (only `slug` was uuid-suffixed)
    # and every caller passed a plain "Batch A"/"Batch B"/"Detail Batch" `name` too --
    # `enrollment_open=True` with a perpetually-future `end_date` (today+90 days) means
    # every run of this file left a real, permanently-bookable, near-identical-looking
    # batch in the shared dev DB (same class of gap as `RAID.md` I-09, surfaced directly
    # by a user screenshot of the student's own slot picker showing many duplicate cards).
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Roster Test Program {uuid.uuid4().hex[:6]}",
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
        name=f"{name} {uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        timezone="Asia/Kolkata",
        capacity=20,
        enrollment_open=True,
        status="active",
        mode="Online",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _enroll_student(db_session, batch: Batch, *, name: str) -> User:
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=name,
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()
    return student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_roster_is_scoped_strictly_to_its_own_batch(client, db_session):
    trainer = await _create_trainer(db_session)
    batch_a = await _create_batch(db_session, trainer, name="Batch A")
    batch_b = await _create_batch(db_session, trainer, name="Batch B")
    student_a = await _enroll_student(db_session, batch_a, name="Student In A")
    student_b = await _enroll_student(db_session, batch_b, name="Student In B")
    await _login(client, trainer.email)

    response = await client.get("/api/v1/workflows/it/trainer/context")
    assert response.status_code == 200
    data = response.json()

    roster_a = [e["student"] for e in data["enrollments"] if e["batch_id"] == str(batch_a.id)]
    roster_b = [e["student"] for e in data["enrollments"] if e["batch_id"] == str(batch_b.id)]
    assert roster_a == [student_a.full_name]
    assert roster_b == [student_b.full_name]


@pytest.mark.asyncio
async def test_batch_entries_include_schedule_and_status_detail(client, db_session):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer, name="Detail Batch")
    await _enroll_student(db_session, batch, name="Enrolled Student")
    await _login(client, trainer.email)

    response = await client.get("/api/v1/workflows/it/trainer/context")
    assert response.status_code == 200
    listed = next(b for b in response.json()["batches"] if b["id"] == str(batch.id))
    assert listed["status"] == "active"
    assert listed["mode"] == "Online"
    assert listed["capacity"] == 20
    assert listed["enrolled_count"] == 1
    assert listed["start_date"] and listed["end_date"]


@pytest.mark.asyncio
async def test_trainer_does_not_see_another_trainers_batch_or_roster(client, db_session):
    trainer_a = await _create_trainer(db_session)
    trainer_b = await _create_trainer(db_session)
    own_batch = await _create_batch(db_session, trainer_a, name="Own Batch")
    other_batch = await _create_batch(db_session, trainer_b, name="Other Trainer Batch")
    await _enroll_student(db_session, other_batch, name="Should Not Be Visible")
    await _login(client, trainer_a.email)

    response = await client.get("/api/v1/workflows/it/trainer/context")
    assert response.status_code == 200
    data = response.json()
    batch_ids = {b["id"] for b in data["batches"]}
    assert str(own_batch.id) in batch_ids
    assert str(other_batch.id) not in batch_ids
    assert all(e["batch_id"] != str(other_batch.id) for e in data["enrollments"])


@pytest.mark.asyncio
async def test_a_student_cannot_view_trainer_batch_context(client, db_session):
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Not A Trainer",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    await _login(client, student.email)

    response = await client.get("/api/v1/workflows/it/trainer/context")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_trainer_context_requires_authentication(client):
    response = await client.get("/api/v1/workflows/it/trainer/context")
    assert response.status_code == 401
