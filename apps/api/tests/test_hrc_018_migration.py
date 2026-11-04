"""hrc-018 -- migration 0269_match_engine (DEC-SCOPE-392 E2/E6; AC1). The round trip runs in a throwaway database built from scratch (the
rec-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_hrc_017_migration import _config, _sql

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_hrc_018_migration_0269", API_ROOT / "alembic" / "versions" / "0269_match_engine.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0268_candidate_imports", "0269_match_engine"
HARD = [f"match_hard_{k}" for k in ("experience", "qualification", "location", "salary")]


def test_migration_chains_after_candidate_imports_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import MATCH_DEFAULT_WEIGHTS, MATCH_FACTORS, MATCH_SETTING_CHECKS, Job, MatchSetting

    assert (MATCH_FACTORS, MATCH_DEFAULT_WEIGHTS) == (_migration.FACTORS, _migration.DEFAULT_WEIGHTS) and sum(MATCH_DEFAULT_WEIGHTS) == 100
    assert MATCH_SETTING_CHECKS == _migration.CHECKS
    assert {c.name for c in MatchSetting.__table__.constraints} >= set(MATCH_SETTING_CHECKS)
    assert all(not Job.__table__.columns[c].nullable for c in HARD)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc018_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_the_sum_check_and_existing_jobs_keep_no_hard_filter(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    values = "1, 40, 20, 15, 10, 10, 5"
    _sql(url, f"INSERT INTO match_settings (id, skills_weight, experience_weight, qualification_weight, location_weight, role_weight, salary_weight) VALUES ({values})")
    with pytest.raises(Exception, match="ck_match_settings_total"):
        _sql(url, "UPDATE match_settings SET skills_weight = 41")
    with pytest.raises(Exception, match="ck_match_settings_one_row"):
        _sql(url, f"INSERT INTO match_settings (id, skills_weight, experience_weight, qualification_weight, location_weight, role_weight, salary_weight) VALUES (2{values[1:]})")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'match_settings'") == []
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")}
    assert columns.isdisjoint(HARD)
    command.upgrade(cfg, HEAD)
    defaults = _sql(url, "SELECT column_default FROM information_schema.columns WHERE table_name = 'jobs' AND column_name = 'match_hard_salary'")
    assert defaults == [("false",)]
