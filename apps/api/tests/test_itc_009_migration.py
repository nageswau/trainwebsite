"""itc-009 -- migration 0226_follow_up_escalation: chain, the 0-168 CHECK, existing teams off, and a round trip, in a throwaway database
(the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_itc_009_migration_0226", VERSIONS / "0226_follow_up_escalation.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0224_tel_source_workload", "0226_follow_up_escalation"
COLUMNS = "SELECT table_name, column_name FROM information_schema.columns WHERE (table_name, column_name) IN (('tel_settings', 'escalate_after_hours'), ('lead_follow_ups', 'escalated_at')) ORDER BY 1"


def test_migration_chains_after_0224_and_keeps_the_limit_in_step():
    from app.models import TEL_SETTING_MAX_HOURS

    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert HEAD in {r.revision for r in ScriptDirectory.from_config(_config()).walk_revisions()}
    assert _migration.MAX_HOURS == TEL_SETTING_MAX_HOURS


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0226 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_constraint_default_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT DISTINCT escalate_after_hours FROM tel_settings") == [(0,)]
    for bad in (-1, 169):
        with pytest.raises(Exception, match="ck_tel_settings_escalate_after_hours"):
            _sql(url, f"UPDATE tel_settings SET escalate_after_hours = {bad}")
    _sql(url, "UPDATE tel_settings SET escalate_after_hours = 168 WHERE team = 'it'")

    command.downgrade(cfg, BASE)
    assert _sql(url, COLUMNS) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, COLUMNS) == [("lead_follow_ups", "escalated_at"), ("tel_settings", "escalate_after_hours")]
    assert _sql(url, "SELECT DISTINCT escalate_after_hours FROM tel_settings") == [(0,)]  # re-added off: escalation is opt-in
