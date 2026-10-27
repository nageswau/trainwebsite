"""nehn-027 -- migration 0202_learning_resource_files (DEC-SCOPE-294 M1): the chain and the round trip, in a throwaway database (the
nehn-003/nehn-024 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_027_migration_0202", VERSIONS / "0202_learning_resource_files.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0202_learning_resource_files", "0201_coordinator_role"
NEW = {"stored_file_id", "sort_order", "deleted_at"}


def test_migration_chains_after_0201():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn027_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> dict[str, str]:
    return {r[0]: r[1] for r in _sql(url, "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'learning_resources'")}


def test_columns_round_trip_and_existing_rows_survive(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _columns(url)
    assert not NEW & set(before) and before["url"] == "NO"
    command.upgrade(cfg, HEAD)
    after = _columns(url)
    assert NEW <= set(after) and after["url"] == "YES"
    indexes = {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename = 'learning_resources'")}
    assert "uq_learning_resources_stored_file" in indexes
    command.downgrade(cfg, BASE)
    restored = _columns(url)
    assert not NEW & set(restored) and restored["url"] == "NO"
