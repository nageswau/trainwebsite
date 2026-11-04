"""hrc-009 -- migration 0267_application_review (DEC-SCOPE-390 R3): the chain and the round trip, in a throwaway database (the hrc-001
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_009_migration_0267", VERSIONS / "0267_application_review.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0267_application_review", "0266_website_intake"


def test_migration_chains_after_its_base():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc009_migration_{uuid.uuid4().hex[:8]}"
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


def _has_column(url) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'job_applications' AND column_name = 'needs_review_since'"))


def test_round_trip_adds_the_flag_and_its_index(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not _has_column(url)
    command.upgrade(cfg, HEAD)
    assert _has_column(url)
    assert _sql(url, "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_job_applications_needs_review'")
    command.downgrade(cfg, BASE)
    assert not _has_column(url)
    assert not _sql(url, "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_job_applications_needs_review'")
