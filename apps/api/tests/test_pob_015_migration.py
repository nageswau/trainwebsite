"""pob-015 -- migration 0307_institution_vacancy_shares (DEC-SCOPE-426): the chain, the frozen CHECK copies and the round trip, in a
throwaway database (the pob-013 0288 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import VACANCY_SHARE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_015_migration_0307", VERSIONS / "0307_institution_vacancy_shares.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0307_institution_vacancy_shares"
BASE = _migration.down_revision
TABLES = {"institution_vacancy_shares"}


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.CHECKS == VACANCY_SHARE_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob015_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_upgrade_is_guarded_and_the_downgrade_removes_everything(isolated_db):
    """0001 create_all already built today's schema, so the upgrade must skip what exists; downgrade then upgrade again round-trips."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
