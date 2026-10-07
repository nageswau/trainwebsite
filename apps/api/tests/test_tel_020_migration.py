"""tel-020 -- migration 0099_tel_settings (spec §3; DEC-SCOPE-111 AL1). Round trip, the seeded 24 h / 4 h defaults and the 1-168 checks run
in a throwaway database built from scratch (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_tel_020_migration_0099", VERSIONS / "0099_tel_settings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0098_bdm_agent_link", "0099_tel_settings"


def test_migration_chains_after_0098_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import TEL_SETTING_DEFAULTS, TelSetting

    table = TelSetting.__table__
    assert {c.name for c in table.columns} == {"team", "not_contacted_hours", "hot_pending_hours", "updated_by_user_id", "created_at", "updated_at"}
    assert [c.name for c in table.primary_key.columns] == ["team"] and table.c.updated_by_user_id.nullable
    assert {"ck_tel_settings_team", "ck_tel_settings_not_contacted_hours", "ck_tel_settings_hot_pending_hours"} <= {c.name for c in table.constraints}
    assert TEL_SETTING_DEFAULTS == {"not_contacted_hours": 24, "hot_pending_hours": 4} == _migration.DEFAULTS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel020_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_seeds_both_teams_and_checks_the_range(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT team, not_contacted_hours, hot_pending_hours, updated_by_user_id FROM tel_settings ORDER BY team") == [
        ("it", 24, 4, None), ("overseas", 24, 4, None)]
    for sql, constraint in (
        ("UPDATE tel_settings SET not_contacted_hours = 0", "ck_tel_settings_not_contacted_hours"),
        ("UPDATE tel_settings SET hot_pending_hours = 169", "ck_tel_settings_hot_pending_hours"),
        ("INSERT INTO tel_settings (team, not_contacted_hours, hot_pending_hours) VALUES ('global', 24, 4)", "ck_tel_settings_team"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, sql)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'tel_settings'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM tel_settings") == [(2,)]
