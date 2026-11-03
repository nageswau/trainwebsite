"""itc-016 -- migration 0240_fee_reminders: chain, the CHECKs, the one-reminder-per-day unique key, the sweep index and a round trip, in a
throwaway database (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_016_migration_0240", VERSIONS / "0240_fee_reminders.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0240_fee_reminders"
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name IN ('fee_reminder_log', 'fee_reminder_settings') ORDER BY 1"
INDEX = "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_payments_status_due_date'"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc016_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0240 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_constraints_unique_key_index_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == [("fee_reminder_log",), ("fee_reminder_settings",)]
    with pytest.raises(Exception, match="ck_fee_reminder_settings_days_before"):
        _sql(url, "INSERT INTO fee_reminder_settings (id, days_before, overdue_days) VALUES (1, 31, '[]')")
    with pytest.raises(Exception, match="ck_fee_reminder_settings_one_row"):
        _sql(url, "INSERT INTO fee_reminder_settings (id, days_before, overdue_days) VALUES (2, 3, '[]')")
    unique = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_fee_reminder_log_rule_day'")
    assert "UNIQUE" in unique[0][0] and "reminder_date" in unique[0][0]
    assert "(status, due_date)" in _sql(url, INDEX)[0][0]

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLES) == [] and _sql(url, INDEX) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == [("fee_reminder_log",), ("fee_reminder_settings",)] and _sql(url, INDEX)
