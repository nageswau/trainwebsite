"""pob-025 -- migration 0318_placement_guarantee (DEC-SCOPE-436): the chain, the frozen checks and the round trip, in a throwaway database
(the pob-024 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_GUARANTEE_CHECKS, PLACEMENT_GUARANTEE_CHECKS, RECRUITER_CONTRACT_GUARANTEE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_025_migration", VERSIONS / "0318_placement_guarantee.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.JOB_CHECKS == JOB_GUARANTEE_CHECKS
    assert _migration.CONTRACT_CHECKS == RECRUITER_CONTRACT_GUARANTEE_CHECKS
    assert _migration.PLACEMENT_CHECKS == PLACEMENT_GUARANTEE_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob025_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url, table: str) -> set[str]:
    return {r[0] for r in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def test_the_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.stamp(cfg, HEAD)  # 0001 builds today's models: drop the columns so the guarded upgrade must add them back
    command.downgrade(cfg, BASE)
    assert "guarantee_days" not in _columns(url, "placements")
    command.upgrade(cfg, HEAD)
    assert set(_migration.PLACEMENT_COLUMNS) <= _columns(url, "placements")
    assert "guarantee_days" in _columns(url, "jobs") and "guarantee_days" in _columns(url, "recruiter_contracts")
    checks = {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE contype = 'c'")}
    assert {*PLACEMENT_GUARANTEE_CHECKS, *JOB_GUARANTEE_CHECKS, *RECRUITER_CONTRACT_GUARANTEE_CHECKS} <= checks
    command.upgrade(cfg, HEAD)  # a rerun is a no-op
    command.downgrade(cfg, BASE)
    assert "guarantee_days" not in _columns(url, "placements") and "guarantee_days" not in _columns(url, "jobs")
