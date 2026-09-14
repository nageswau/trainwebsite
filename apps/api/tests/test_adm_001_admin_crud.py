"""ADM-001 -- User/course/batch administration.

The base codebase already had working create+update endpoints for users and programs
(`POST`/`PATCH /admin/users`, `POST`/`PATCH /admin/programs`), but `update_program` and
`update_user` let `active` flip to `False` with zero check for active dependents --
ADM-001-AC02's own approved wording ("e.g. a course with active batches... never a silent
cascade") was violated outright. Covers the new dependent-check (block, then allow with
`confirm_cascade`) for both programs and trainers, and RBAC.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Program, User


async def _create_admin(db_session, *, division: str = "it") -> User:
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test IT Admin",
        role="it_admin",
        division=division,
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Managed Trainer",
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
        title=f"ADM-001 Test Program {uuid.uuid4().hex[:6]}",
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


async def _create_active_batch(db_session, program: Program, trainer: User | None = None) -> Batch:
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id if trainer else None,
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
async def test_deactivating_a_program_with_active_batches_is_blocked(client, db_session):
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _create_active_batch(db_session, program)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/programs/{program.id}", json={"active": False})
    assert response.status_code == 409

    await db_session.refresh(program)
    assert program.active is True  # unchanged


@pytest.mark.asyncio
async def test_deactivating_a_program_succeeds_with_explicit_cascade_confirmation(client, db_session):
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _create_active_batch(db_session, program)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/programs/{program.id}", json={"active": False, "confirm_cascade": True})
    assert response.status_code == 200

    await db_session.refresh(program)
    assert program.active is False


@pytest.mark.asyncio
async def test_deactivating_a_program_with_no_active_batches_needs_no_confirmation(client, db_session):
    admin = await _create_admin(db_session)
    program = await _create_program(db_session)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/programs/{program.id}", json={"active": False})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_deactivating_a_trainer_with_active_batches_is_blocked(client, db_session):
    admin = await _create_admin(db_session)
    trainer = await _create_trainer(db_session)
    program = await _create_program(db_session)
    await _create_active_batch(db_session, program, trainer)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/users/{trainer.id}", json={"active": False})
    assert response.status_code == 409

    await db_session.refresh(trainer)
    assert trainer.active is True


@pytest.mark.asyncio
async def test_deactivating_a_trainer_succeeds_with_explicit_cascade_confirmation(client, db_session):
    admin = await _create_admin(db_session)
    trainer = await _create_trainer(db_session)
    program = await _create_program(db_session)
    await _create_active_batch(db_session, program, trainer)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/users/{trainer.id}", json={"active": False, "confirm_cascade": True})
    assert response.status_code == 200

    await db_session.refresh(trainer)
    assert trainer.active is False


@pytest.mark.asyncio
async def test_deactivating_a_trainer_with_no_batches_needs_no_confirmation(client, db_session):
    admin = await _create_admin(db_session)
    trainer = await _create_trainer(db_session)
    await _login(client, admin.email)

    response = await client.patch(f"/api/v1/admin/users/{trainer.id}", json={"active": False})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_non_admin_cannot_manage_users_or_programs(client, db_session):
    trainer = await _create_trainer(db_session)
    program = await _create_program(db_session)
    await _login(client, trainer.email)

    assert (await client.get("/api/v1/admin/users")).status_code == 403
    assert (await client.patch(f"/api/v1/admin/programs/{program.id}", json={"active": False})).status_code == 403


@pytest.mark.asyncio
async def test_admin_management_requires_authentication(client):
    assert (await client.get("/api/v1/admin/users")).status_code == 401
    assert (await client.get("/api/v1/admin/programs")).status_code == 401
