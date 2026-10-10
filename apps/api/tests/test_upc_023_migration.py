"""upc-023 -- migration 0143_university_probability (spec §3, EX2). Round trip and the downgrade refusal run in a throwaway database built
from scratch (the upc-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql
from tests.test_upc_008_migration import _university

_spec = importlib.util.spec_from_file_location("_upc_023_migration_0143", VERSIONS / "0143_university_probability.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0142_profile_shares", "0143_university_probability"
COLUMNS = {"probability_override", "probability_override_reason"}


def test_migration_chains_after_0142_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_PROBABILITY_CHECKS, University

    assert UNIVERSITY_PROBABILITY_CHECKS == _migration.CHECKS
    assert COLUMNS <= {c.name for c in University.__table__.columns}


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, checks = await conn.run_sync(lambda sync: ({c["name"] for c in inspect(sync).get_columns("universities")}, {c["name"] for c in inspect(sync).get_check_constraints("universities")}))
    assert COLUMNS <= columns and set(_migration.CHECKS) <= checks


@pytest.fixture
def isolated_db():
    """A fresh database at 0142."""
    cfg = _config()
    original = settings.database_url
    name = f"upc023_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_an_override_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'universities' AND column_name = 'probability_override'")
    command.upgrade(cfg, HEAD)
    uni = _university(url)
    set_override = "UPDATE universities SET probability_override = :p, probability_override_reason = :r WHERE id = :u"
    with pytest.raises(Exception, match="ck_universities_probability_override"):
        _sql(url, set_override, {"p": 101, "r": "too high", "u": uni})
    with pytest.raises(Exception, match="ck_universities_probability_reason"):
        _sql(url, set_override, {"p": 50, "r": None, "u": uni})
    _sql(url, set_override, {"p": 0, "r": "Ministry approval frozen", "u": uni})
    with pytest.raises(Exception, match="probability overrides exist"):
        command.downgrade(cfg, BASE)
    _sql(url, set_override, {"p": None, "r": None, "u": uni})
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'universities' AND column_name = 'probability_override'")
