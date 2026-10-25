"""ccrm-038 -- migration 0190_calendar_feeds (DEC-SCOPE-272): the chain, the feed table with its unique hash, the appointments SEQUENCE
column (existing rows read 0) and the round trip, in a throwaway database (the ccrm-030 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_038_migration_0190", VERSIONS / "0190_calendar_feeds.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0190_calendar_feeds", "0189_counselor_reminders"


def test_migration_chains_after_0189_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm038_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def _columns(url, table: str) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = :t", {"t": table})}


def test_feed_table_sequence_column_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "calendar_feeds" not in _tables(url) and "calendar_sequence" not in _columns(url, "appointments")
    user = uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, created_at, updated_at) "
              "VALUES (:id, :e, 'x', 'Mig User', 'counselor', 'overseas', true, true, 'en', '{}', now(), now())", {"id": user, "e": f"{user.hex}@example.local"})
    appt = uuid.uuid4()
    _sql(url, "INSERT INTO appointments (id, division, student_id, scheduled_at, appointment_type, mode, status, created_at, updated_at) "
              "VALUES (:id, 'overseas', :u, now(), 'Career Counseling', 'Online', 'scheduled', now(), now())", {"id": appt, "u": user})
    command.upgrade(cfg, HEAD)
    assert "calendar_feeds" in _tables(url)
    assert _sql(url, "SELECT calendar_sequence FROM appointments WHERE id = :id", {"id": appt})[0][0] == 0  # existing rows start at 0
    _sql(url, "INSERT INTO calendar_feeds (user_id, token_hash) VALUES (:u, 'h1')", {"u": user})
    with pytest.raises(sa.exc.IntegrityError):  # one feed per user
        _sql(url, "INSERT INTO calendar_feeds (user_id, token_hash) VALUES (:u, 'h2')", {"u": user})
    command.downgrade(cfg, BASE)
    assert "calendar_feeds" not in _tables(url) and "calendar_sequence" not in _columns(url, "appointments")
