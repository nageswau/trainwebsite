"""hrc-014 -- migration 0256_candidate_duplicates (DEC-SCOPE-377): the chain, the frozen checks and grant, and the round trip in a
throwaway database (the hrc-011 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from app.models import CANDIDATE_DUPLICATE_CHECKS, CANDIDATE_MERGE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_014_migration_0256", VERSIONS / "0256_candidate_duplicates.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0256_candidate_duplicates", "0255_candidate_documents"


def test_migration_chains_after_0255():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_and_seed_are_frozen_copies():
    assert _migration.MERGE_CHECKS == CANDIDATE_MERGE_CHECKS
    assert _migration.DUPLICATE_CHECKS == CANDIDATE_DUPLICATE_CHECKS
    assert {f"{r}.{a}" for role, r, a in _migration.SEED} == {k for k in rbac.DEFAULT_GRANTS["placement_manager"] if k.startswith("candidates.merge")}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc014_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidates'")}


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _grants(url) -> int:
    return _sql(url, "SELECT count(*) FROM role_permissions WHERE resource = 'candidates' AND action = 'merge' AND role = 'placement_manager'")[0][0]


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "merged_into_id" not in _columns(url) and "candidate_duplicates" not in _tables(url) and _grants(url) == 0
    command.upgrade(cfg, HEAD)
    assert {"merged_into_id", "merged_at", "merged_by_user_id"} <= _columns(url)
    assert "candidate_duplicates" in _tables(url) and _grants(url) == 1
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert "merged_into_id" not in _columns(url) and "candidate_duplicates" not in _tables(url) and _grants(url) == 0
    command.upgrade(cfg, HEAD)
