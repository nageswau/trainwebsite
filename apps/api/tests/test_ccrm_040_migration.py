"""ccrm-040 -- migration 0193_student_archive_consent (DEC-SCOPE-275): the chain, the archive table, the agreement `kind` column with
the CN1 seed (idempotent), and the round trip, in a throwaway database (the ccrm-030 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_040_migration_0193", VERSIONS / "0193_student_archive_consent.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0193_student_archive_consent", "0192_calendar_feeds"


def test_migration_chains_after_0192():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_seed_covers_the_service_catalogue():
    from app.services.overseas_consents import KINDS

    assert tuple(_migration.SEED) == KINDS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm040_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url, table: str) -> set[str]:
    return {r[0] for r in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def test_table_column_seed_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "overseas_student_archives" not in _tables(url) and "kind" not in _columns(url, "agreements")
    command.upgrade(cfg, HEAD)
    assert "overseas_student_archives" in _tables(url) and "kind" in _columns(url, "agreements")
    seeded = _sql(url, "SELECT kind, version, active FROM agreements WHERE division = 'overseas' ORDER BY kind")
    assert [tuple(r) for r in seeded] == [("data_processing", "v1", True), ("document_sharing", "v1", True)]
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)  # the seed is not repeated
    assert _sql(url, "SELECT count(*) FROM agreements WHERE division = 'overseas'")[0][0] == 2
    command.downgrade(cfg, BASE)
    assert "overseas_student_archives" not in _tables(url) and "kind" not in _columns(url, "agreements")
    assert _sql(url, "SELECT count(*) FROM agreements WHERE division = 'overseas'")[0][0] == 0
