"""nehn-029 -- migration 0198_live_session_cancel_reason (DEC-SCOPE-286). The round trip runs in a throwaway database built from scratch
(the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_029_migration_0198", VERSIONS / "0198_live_session_cancel_reason.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0197_course_icons", "0198_live_session_cancel_reason"
COLUMNS = "SELECT column_name FROM information_schema.columns WHERE table_name = 'live_sessions' AND column_name = 'cancel_reason'"


def test_migration_chains_after_0197_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


@pytest.mark.asyncio
async def test_column_exists_and_is_nullable_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("live_sessions")})
    assert columns["cancel_reason"]["nullable"]


def test_upgrade_and_downgrade_round_trip_keep_existing_sessions():
    cfg = _config()
    original = settings.database_url
    name = f"nehn029_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        assert _sql(url, COLUMNS) == []
        program = _sql(
            url,
            "INSERT INTO programs (id, slug, category, title, summary, duration, eligibility, fees, certification, curriculum, placement_assistance, trainer_name, active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'n029', 'IT', 'P', 'S', '8w', 'None', 1, 'C', '[]', 'Yes', 'T', true, now(), now()) RETURNING id",
        )[0][0]
        batch = _sql(
            url,
            "INSERT INTO batches (id, program_id, name, start_date, end_date, schedule, timezone, capacity, enrollment_open, mode, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :program, 'B', current_date, current_date, 'Mon', 'Asia/Kolkata', 20, true, 'Online', 'active', now(), now()) RETURNING id",
            {"program": program},
        )[0][0]
        _sql(
            url,
            "INSERT INTO live_sessions (id, batch_id, title, starts_at, provider, recording_status, sync_status, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :batch, 'Kept', now(), 'manual', 'not_available', 'manual', 'scheduled', now(), now())",
            {"batch": batch},
        )
        command.upgrade(cfg, HEAD)
        assert _sql(url, COLUMNS) == [("cancel_reason",)]
        assert _sql(url, "SELECT title, status, cancel_reason FROM live_sessions") == [("Kept", "scheduled", None)]
        command.downgrade(cfg, BASE)
        assert _sql(url, COLUMNS) == []
        assert _sql(url, "SELECT title FROM live_sessions") == [("Kept",)]
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
