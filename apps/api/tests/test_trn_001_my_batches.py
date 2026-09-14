"""TRN-001 -- My Batches.

The base codebase's own `GET /portal/it/trainer/dashboard` already lists the
authenticated trainer's own batches (Batch.trainer_id == user.id) via the same
DataTable-payload pattern used elsewhere -- no crude text panel to replace here. This
file adds the dedicated coverage that was missing: cross-trainer isolation, the
empty-state case, and RBAC at the API layer (division/role route dispatch), tying real
test evidence to this Feature ID for the first time.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Batch Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch(db_session, trainer: User | None, *, name: str | None = None) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Trainer Batches Test Program {uuid.uuid4().hex[:6]}",
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
        trainer_id=trainer.id if trainer else None,
        name=name or f"Batch-{uuid.uuid4().hex[:6]}",
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
async def test_trainer_sees_only_their_own_batches(client, db_session):
    trainer_a = await _create_trainer(db_session)
    trainer_b = await _create_trainer(db_session)
    own_batch = await _create_batch(db_session, trainer_a, name=f"Trainer A Batch {uuid.uuid4().hex[:6]}")
    other_batch = await _create_batch(db_session, trainer_b, name=f"Trainer B Batch {uuid.uuid4().hex[:6]}")
    await _login(client, trainer_a.email)

    response = await client.get("/api/v1/portal/it/trainer/dashboard")
    assert response.status_code == 200
    names = [row["batch"] for row in response.json()["rows"]]
    assert own_batch.name in names
    assert other_batch.name not in names


@pytest.mark.asyncio
async def test_trainer_with_no_assigned_batches_sees_empty_state_not_an_error(client, db_session):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)

    response = await client.get("/api/v1/portal/it/trainer/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["rows"] == []
    assert data["metrics"][0] == {"label": "Assigned batches", "value": 0}


@pytest.mark.asyncio
async def test_a_student_cannot_view_the_trainer_batch_list(client, db_session):
    trainer = await _create_trainer(db_session)
    await _create_batch(db_session, trainer)
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

    response = await client.get("/api/v1/portal/it/trainer/dashboard")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_my_batches_requires_authentication(client):
    response = await client.get("/api/v1/portal/it/trainer/dashboard")
    assert response.status_code == 401
