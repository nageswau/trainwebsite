"""nehn-003 -- migration 0194_stored_files (DEC-SCOPE-279 PS5): the chain and the round trip, in a throwaway database (the ccrm-040
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_003_migration_0194", VERSIONS / "0194_stored_files.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0194_stored_files", "0193_student_archive_consent"


def test_migration_chains_after_0193():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_table_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "stored_files" not in _tables(url)
    command.upgrade(cfg, HEAD)
    assert "stored_files" in _tables(url)
    indexes = {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename = 'stored_files'")}
    assert {"uq_stored_files_key", "ix_stored_files_owner_id"} <= indexes
    command.downgrade(cfg, BASE)
    assert "stored_files" not in _tables(url)
