"""User-requested join-experience fix (`docs/decisions/PENDING_ZOHO_LIVE_CLASSES.md` §1b
items a/b/c, 2026-09-09): the raw join URL on the trainer's own generic "Live Sessions"
table rendered as inert text -- no button, no time-window gating. `_payload()` now
accepts an optional per-column `type` (kept a plain serializable string, never a
function, since this crosses a JSON boundary) and the trainer's `live-sessions` section
declares its "meeting" column as `type: "join"`, carrying `ends_at`/`host_url` as extra
row data for the frontend's `JoinSessionButton` to gate on. Also fixed a related,
adjacent inconsistency found while touching this row: the "meeting" cell now prefers
`host_url` when present, matching `LiveClassesPanel`'s own already-established
"host gets the host link" precedent -- previously this table showed the plain
participant link even to the trainer who owns the session.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, LiveSession, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"join-btn-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Join Button Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch_with_session(db_session, trainer: User, **session_overrides) -> LiveSession:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Join Button Test Program {uuid.uuid4().hex[:6]}",
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
    defaults = dict(
        batch_id=batch.id,
        title=f"Join Button Test Session {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        ends_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1, hours=1),
        provider="google_meet",
        status="scheduled",
    )
    defaults.update(session_overrides)
    session = LiveSession(**defaults)
    db_session.add(session)
    await db_session.commit()
    return session


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_live_sessions_meeting_column_is_declared_as_a_join_type(client, db_session):
    trainer = await _create_trainer(db_session)
    await _create_batch_with_session(db_session, trainer, meeting_url="https://meet.example.com/session")
    await _login(client, trainer.email)

    response = await client.get("/api/v1/portal/it/trainer/live-sessions")
    assert response.status_code == 200
    body = response.json()
    meeting_column = next(c for c in body["columns"] if c["key"] == "meeting")
    assert meeting_column["type"] == "join"


@pytest.mark.asyncio
async def test_meeting_cell_prefers_host_url_over_the_plain_meeting_url(client, db_session):
    trainer = await _create_trainer(db_session)
    await _create_batch_with_session(
        db_session, trainer,
        meeting_url="https://meet.example.com/participant",
        host_url="https://meet.example.com/host",
    )
    await _login(client, trainer.email)

    response = await client.get("/api/v1/portal/it/trainer/live-sessions")
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["meeting"] == "https://meet.example.com/host"
    assert row["host_url"] == "https://meet.example.com/host"


@pytest.mark.asyncio
async def test_meeting_cell_falls_back_to_the_plain_meeting_url_when_no_host_url_exists(client, db_session):
    trainer = await _create_trainer(db_session)
    await _create_batch_with_session(db_session, trainer, meeting_url="https://meet.example.com/participant", host_url=None)
    await _login(client, trainer.email)

    response = await client.get("/api/v1/portal/it/trainer/live-sessions")
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["meeting"] == "https://meet.example.com/participant"


@pytest.mark.asyncio
async def test_row_carries_ends_at_for_client_side_time_window_gating(client, db_session):
    trainer = await _create_trainer(db_session)
    session = await _create_batch_with_session(db_session, trainer, meeting_url="https://meet.example.com/session")
    await _login(client, trainer.email)

    response = await client.get("/api/v1/portal/it/trainer/live-sessions")
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["ends_at"] is not None
    assert row["starts"] is not None
