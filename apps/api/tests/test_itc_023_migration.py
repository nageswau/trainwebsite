"""itc-023 -- migration 0236_it_at_risk: chain, the CHECKs, one open flag per enrolment, and a round trip, in a throwaway database (the
tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_itc_023_migration_0236", VERSIONS / "0236_it_at_risk.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0236_it_at_risk"
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name IN ('it_risk_thresholds', 'student_risk_flags') ORDER BY 1"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc023_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0236 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_constraints_open_flag_index_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == [("it_risk_thresholds",), ("student_risk_flags",)]
    with pytest.raises(Exception, match="ck_it_risk_thresholds_percent"):
        _sql(url, f"INSERT INTO it_risk_thresholds (program_id, min_attendance_percent) VALUES ('{uuid.uuid4()}', 101)")
    with pytest.raises(Exception, match="ck_it_risk_thresholds_counts"):
        _sql(url, f"INSERT INTO it_risk_thresholds (program_id, min_sessions) VALUES ('{uuid.uuid4()}', 0)")
    index = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_student_risk_flags_open'")
    assert "UNIQUE" in index[0][0] and "cleared_at IS NULL" in index[0][0]

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == [("it_risk_thresholds",), ("student_risk_flags",)]
