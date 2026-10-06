"""tel-022 -- migration 0080_tel_targets (spec §3). Round trip, constraints and downgrade refusal run in a throwaway database built from
scratch (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_tel_022_migration_0080", VERSIONS / "0080_tel_targets.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0079_bdm_mous", "0080_tel_targets"
INSERT = "INSERT INTO tel_targets (id, scope, team, user_id, period, kpi, value, effective_from, set_by_user_id) VALUES (:id, :scope, :team, :user, :period, :kpi, :value, :from, :by)"


def test_migration_chains_after_0079_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import TelTarget

    table = TelTarget.__table__
    assert {c.name for c in table.columns} == {
        "id",
        "scope",
        "team",
        "user_id",
        "period",
        "kpi",
        "value",
        "effective_from",
        "set_by_user_id",
        "created_at",
        "updated_at",
    }
    assert table.c.team.nullable and table.c.user_id.nullable and table.c.value.nullable and not table.c.effective_from.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {
        "uq_tel_targets_team",
        "uq_tel_targets_user",
        "ck_tel_targets_scope",
        "ck_tel_targets_subject",
        "ck_tel_targets_period",
        "ck_tel_targets_kpi",
        "ck_tel_targets_team",
        "ck_tel_targets_value",
        "ck_tel_targets_value_null_user_only",
        "ck_tel_targets_monthly_first",
    } <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel022_migration_{uuid.uuid4().hex[:8]}"
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


def _user(url) -> uuid.UUID:
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'T', 'telecaller', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "email": f"{user_id.hex[:10]}@example.com"},
    )
    return user_id


def _row(url, by, **overrides):
    row = {"id": uuid.uuid4(), "scope": "team", "team": "it", "user": None, "period": "daily", "kpi": "calls", "value": 80, "from": date(2026, 11, 2), "by": by}
    row.update(overrides)
    _sql(url, INSERT, row)


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    by = _user(url)
    _row(url, by)
    with pytest.raises(Exception, match="uq_tel_targets_team"):
        _row(url, by, value=90)
    _row(url, by, scope="user", team=None, user=by, value=None)  # NULL = override removed
    with pytest.raises(Exception, match="uq_tel_targets_user"):
        _row(url, by, scope="user", team=None, user=by)
    cases = {
        "ck_tel_targets_subject": {"scope": "team", "team": None, "user": by},
        "ck_tel_targets_scope": {"scope": "division"},
        "ck_tel_targets_period": {"period": "weekly", "from": date(2027, 1, 1)},
        "ck_tel_targets_kpi": {"kpi": "emails"},
        "ck_tel_targets_team": {"team": "global"},
        "ck_tel_targets_value": {"value": -1},
        "ck_tel_targets_value_null_user_only": {"value": None, "from": date(2026, 11, 3)},
        "ck_tel_targets_monthly_first": {"period": "monthly", "from": date(2026, 11, 2)},
    }
    for constraint, overrides in cases.items():
        with pytest.raises(Exception, match=constraint):
            _row(url, by, **{"from": date(2026, 11, 9), **overrides})
    _row(url, by, period="monthly", **{"from": date(2026, 12, 1)})
    with pytest.raises(Exception, match="Cannot downgrade 0080_tel_targets"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM tel_targets")
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'tel_targets'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM tel_targets") == [(0,)]
