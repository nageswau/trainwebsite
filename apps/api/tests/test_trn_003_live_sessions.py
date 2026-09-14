"""TRN-003 -- Upcoming sessions and live-class join.

`GET /communications/it/live-sessions` already scoped trainers to their own batches and
returned `host_url` for trainer/admin roles (STU-003's own hide-from-student check
implied the opposite case existed, but nothing tested the trainer side directly). Covers:
a trainer sees the host join link for their own batch's session, sessions are scoped
strictly to the trainer's own batches (not another trainer's), a not-yet-joinable session
(no link set) is represented cleanly rather than erroring (TRN-003-AC02), and RBAC.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, LiveSession, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Live Session Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch_with_session(db_session, trainer: User, *, with_links: bool) -> LiveSession:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"TRN-003 Test Program {uuid.uuid4().hex[:6]}",
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
    await db_session.flush()
    session = LiveSession(
        batch_id=batch.id,
        title=f"Upcoming Session {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        ends_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1, hours=1),
        provider="manual",
        meeting_url="https://meet.example.com/session" if with_links else None,
        host_url="https://meet.example.com/host/session" if with_links else None,
        status="scheduled",
    )
    db_session.add(session)
    await db_session.commit()
    return session


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_trainer_sees_the_host_join_link_for_their_own_session(client, db_session):
    trainer = await _create_trainer(db_session)
    session = await _create_batch_with_session(db_session, trainer, with_links=True)
    await _login(client, trainer.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    listed = next(s for s in response.json() if s["id"] == str(session.id))
    assert listed["host_url"] == "https://meet.example.com/host/session"


@pytest.mark.asyncio
async def test_a_not_yet_joinable_session_is_represented_cleanly_not_an_error(client, db_session):
    """TRN-003-AC02: no join link set yet -- shown as such, not a broken response."""
    trainer = await _create_trainer(db_session)
    session = await _create_batch_with_session(db_session, trainer, with_links=False)
    await _login(client, trainer.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    listed = next(s for s in response.json() if s["id"] == str(session.id))
    assert listed["host_url"] is None
    assert listed["meeting_url"] is None


@pytest.mark.asyncio
async def test_trainer_never_sees_another_trainers_session(client, db_session):
    trainer_a = await _create_trainer(db_session)
    trainer_b = await _create_trainer(db_session)
    other_session = await _create_batch_with_session(db_session, trainer_b, with_links=True)
    await _login(client, trainer_a.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    assert all(s["id"] != str(other_session.id) for s in response.json())


@pytest.mark.asyncio
async def test_trainer_with_no_batches_sees_empty_list_not_an_error(client, db_session):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_role_outside_self_is_rejected(client, db_session):
    hr = User(
        email=f"hr-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="HR Team",
        role="hr_team",
        division="it",
        active=True,
    )
    db_session.add(hr)
    await db_session.commit()
    await _login(client, hr.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 403
