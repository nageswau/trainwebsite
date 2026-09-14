"""ADM-009 -- Resources/recordings oversight.

Promoted out of `Unscheduled/BLOCKED` on 2026-09-03 (`DEC-SCOPE-008` --
`docs/decisions/PRODUCT_DECISION_REGISTER.md` Group 11) -- its dependency, `TRN-004`, was
already done. Trainer-side resource upload/list (`LearningResource`, `POST /workflows/it/
trainer/materials`) already existed, self-scoped to the trainer's own batch (`TRN-004`).
No cross-trainer admin oversight existed anywhere -- added a `resources` section to the
existing `it_admin`/`super_admin` portal dispatcher (`services/portal.py`), reusing
`LearningResource`/`Batch`/`User` directly (no new model/migration), mirroring the
trainer's own "materials" section's query shape but unscoped across every batch/trainer.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, LearningResource, Program, User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}", role=role, division="it", active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_batch_with_resource(db_session, trainer: User, *, title: str) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}", category="Software Development", title=f"ADM-009 Test Program {uuid.uuid4().hex[:6]}",
        summary="Test", duration="8 weeks", eligibility="None", fees=10000, certification="Test cert",
        curriculum=["Module 1"], placement_assistance="Yes", trainer_name="Test Trainer", active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id, trainer_id=trainer.id, name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(), end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm", capacity=20, enrollment_open=True, status="active",
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add(LearningResource(batch_id=batch.id, title=title, resource_type="recording", url="https://example.com/recording.mp4"))
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_it_admin_sees_resources_across_batches_they_do_not_personally_manage(client, db_session):
    trainer_one = await _create_user(db_session, "trainer")
    trainer_two = await _create_user(db_session, "trainer")
    unique_one = f"Resource One {uuid.uuid4().hex[:8]}"
    unique_two = f"Resource Two {uuid.uuid4().hex[:8]}"
    await _create_batch_with_resource(db_session, trainer_one, title=unique_one)
    await _create_batch_with_resource(db_session, trainer_two, title=unique_two)
    admin = await _create_user(db_session, "it_admin")

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/it/admin/resources")
    assert response.status_code == 200
    rows = response.json()["rows"]
    titles = {row["resource"] for row in rows}
    assert unique_one in titles
    assert unique_two in titles
    trainers = {row["trainer"] for row in rows}
    assert trainer_one.full_name in trainers
    assert trainer_two.full_name in trainers


@pytest.mark.asyncio
async def test_a_batch_with_no_resources_is_an_honest_empty_state(client, db_session):
    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/it/admin/resources")
    assert response.status_code == 200
    assert isinstance(response.json()["rows"], list)


@pytest.mark.asyncio
async def test_non_admin_role_is_rejected(client, db_session):
    trainer = await _create_user(db_session, "trainer")
    await _login(client, trainer.email)
    response = await client.get("/api/v1/portal/it/admin/resources")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_has_no_resources_section_batches_are_it_only(client, db_session):
    overseas_admin = User(
        email=f"overseas-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(overseas_admin)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={"email": overseas_admin.email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert login.status_code == 200
    response = await client.get("/api/v1/portal/overseas/admin/resources")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resources_oversight_requires_authentication(client):
    response = await client.get("/api/v1/portal/it/admin/resources")
    assert response.status_code == 401
