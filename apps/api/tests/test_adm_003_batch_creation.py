"""ADM-003 -- Batch creation and trainer assignment.

The base codebase's `BatchCreate` schema allowed `capacity` up to 500 with no enforcement
of the approved 20-per-slot limit (`DATA_MODEL.md` §3.3's own "capacity <= 20, enforced at
write time (ADM-003-AC02)", `API_CONTRACT.md`'s own "422 if capacity > 20") -- a real,
confirmed AC02 violation, not a test-coverage gap. Fixed on both the create schema and the
previously-unchecked `PATCH /admin/batches/{id}` path. Covers that, trainer assignment at
creation, the created batch becoming student-selectable, and RBAC.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Program, User


async def _create_admin(db_session) -> User:
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Batch Admin",
        role="it_admin",
        division="it",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Assignable Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_program(db_session) -> Program:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"ADM-003 Test Program {uuid.uuid4().hex[:6]}",
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
    await db_session.commit()
    return program


def _batch_payload(program_id, trainer_id=None, **overrides):
    payload = {
        "program_id": str(program_id),
        "trainer_id": str(trainer_id) if trainer_id else None,
        "name": f"Batch-{uuid.uuid4().hex[:6]}",
        "start_date": datetime.date.today().isoformat(),
        "end_date": (datetime.date.today() + datetime.timedelta(days=90)).isoformat(),
        "schedule": "Mon-Fri 7pm",
        "capacity": 20,
    }
    payload.update(overrides)
    return payload


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_creates_a_batch_with_a_trainer_assigned(client, db_session):
    admin = await _create_admin(db_session)
    trainer = await _create_trainer(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    response = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id, trainer.id))
    assert response.status_code == 201
    assert response.json()["capacity"] == 20


@pytest.mark.asyncio
async def test_creating_a_batch_with_capacity_above_20_is_rejected(client, db_session):
    """ADM-003-AC02: capacity exceeding 20 rejected."""
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    response = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id, capacity=21))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_created_batch_becomes_student_selectable(client, db_session):
    """ADM-003-AC01: batch becomes student-selectable."""
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    created = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id))
    assert created.status_code == 201
    batch_id = created.json()["id"]

    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Prospective Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    await _login(client, student.email)

    available = await client.get("/api/v1/workflows/it/batches/available")
    assert available.status_code == 200
    assert any(b["id"] == batch_id for b in available.json())


@pytest.mark.asyncio
async def test_raising_an_existing_batchs_capacity_above_20_is_rejected(client, db_session):
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    created = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id, capacity=15))
    batch_id = created.json()["id"]

    response = await client.patch(f"/api/v1/admin/batches/{batch_id}", json={"capacity": 25})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_raising_capacity_within_the_20_limit_succeeds(client, db_session):
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    created = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id, capacity=10))
    batch_id = created.json()["id"]

    response = await client.patch(f"/api/v1/admin/batches/{batch_id}", json={"capacity": 20})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_non_admin_cannot_create_a_batch(client, db_session):
    trainer = await _create_trainer(db_session)
    program = await _create_program(db_session)
    await _login(client, trainer.email)

    response = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_creating_a_batch_requires_authentication(client, db_session):
    program = await _create_program(db_session)
    response = await client.post("/api/v1/admin/batches", json=_batch_payload(program.id))
    assert response.status_code == 401
