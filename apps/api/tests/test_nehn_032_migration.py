"""nehn-032 -- migration 0207_certificate_signatories (DEC-SCOPE-300): the chain and the round trip, in a throwaway database (the nehn-031
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_032_migration_0207", VERSIONS / "0207_certificate_signatories.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0207_certificate_signatories", "0206_user_permission_overrides"
SNAPSHOT = "SELECT 1 FROM information_schema.columns WHERE table_name = 'certificates' AND column_name = 'signatory_snapshot'"


def test_migration_chains_after_0206():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn032_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "certificate_signatories" not in _tables(url) and not _sql(url, SNAPSHOT)
    command.upgrade(cfg, HEAD)
    assert "certificate_signatories" in _tables(url) and _sql(url, SNAPSHOT)
    indexes = {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename = 'certificate_signatories'")}
    assert "uq_certificate_signatories_active_role" in indexes
    command.downgrade(cfg, BASE)
    assert "certificate_signatories" not in _tables(url) and not _sql(url, SNAPSHOT)
