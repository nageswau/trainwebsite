"""hrc-015 -- migration 0255_candidate_documents (DEC-SCOPE-379): the chain, the frozen checks and the round trip, in a throwaway
database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_DOCUMENT_CHECKS, CANDIDATE_DOCUMENT_REQUEST_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_015_migration_0255", VERSIONS / "0255_candidate_documents.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0255_candidate_documents", "0251_candidate_compensation"


def test_migration_chains_after_0251():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_a_frozen_copy_of_the_model():
    assert _migration.DOCUMENT_CHECKS == CANDIDATE_DOCUMENT_CHECKS
    assert _migration.REQUEST_CHECKS == CANDIDATE_DOCUMENT_REQUEST_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc015_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _resume_columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidate_resumes'")}


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "candidate_documents" not in _tables(url) and "preview_status" not in _resume_columns(url)
    command.upgrade(cfg, HEAD)
    assert {"candidate_documents", "candidate_document_requests"} <= _tables(url) and {"preview_status", "preview_key"} <= _resume_columns(url)
    command.downgrade(cfg, BASE)
    assert "candidate_documents" not in _tables(url) and "preview_key" not in _resume_columns(url)
