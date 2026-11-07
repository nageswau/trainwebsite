"""pob-014 -- migration 0306_institution_student_pool (DEC-SCOPE-425): the chain, the frozen CHECK copies and the round trip, in a
throwaway database (the pob-013 0288 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_INSTITUTION_CHECKS, INSTITUTION_PERMISSION_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_014_migration_0306", VERSIONS / "0306_institution_student_pool.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0306_institution_student_pool"
BASE = _migration.down_revision
TABLES = {"institution_data_permissions", "institution_data_permission_users"}
CANDIDATE_COLUMNS = {"institution_org_id", "institution_permission_id", "institution_notice_status"}


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.PERMISSION_CHECKS == INSTITUTION_PERMISSION_CHECKS
    assert _migration.CANDIDATE_CHECKS == CANDIDATE_INSTITUTION_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob014_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url, table: str) -> set[str]:
    return {r[0] for r in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def test_upgrade_is_guarded_and_the_downgrade_removes_everything(isolated_db):
    """0001 create_all already built today's schema, so the upgrade must skip what exists; downgrade then upgrade again round-trips."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    assert CANDIDATE_COLUMNS <= _columns(url, "candidates")
    assert "institution_permission_id" in _columns(url, "candidate_import_batches")
    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)
    assert not CANDIDATE_COLUMNS & _columns(url, "candidates")
    assert "institution_permission_id" not in _columns(url, "candidate_import_batches")
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url) and CANDIDATE_COLUMNS <= _columns(url, "candidates")
