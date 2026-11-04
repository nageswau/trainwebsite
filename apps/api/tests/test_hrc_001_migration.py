"""hrc-001 -- migration 0250_compensation_grant (DEC-SCOPE-371 H2): the chain, the seed and the round trip, in a throwaway database
(the ccrm-040 / nehn-008 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_001_migration_0250", VERSIONS / "0250_compensation_grant.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0250_compensation_grant", "0249_it_training_progress"
KEY = "candidates.compensation.view"


def test_migration_chains_after_0249():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_seed_is_a_frozen_copy_of_the_new_default_grants():
    holders = {(role, "candidates.compensation", "view") for role, keys in rbac.DEFAULT_GRANTS.items() if KEY in keys}
    assert set(_migration.SEED) == holders == {("placement_team", "candidates.compensation", "view"), ("placement_manager", "candidates.compensation", "view")}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc001_migration_{uuid.uuid4().hex[:8]}"
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


def _grants(url) -> set[tuple]:
    return {tuple(r) for r in _sql(url, "SELECT role, resource, action FROM role_permissions WHERE resource = 'candidates.compensation'")}


def test_round_trip_keeps_other_grants(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    others = _sql(url, "SELECT count(*) FROM role_permissions WHERE resource <> 'candidates.compensation'")[0][0]
    assert _grants(url) == set()
    command.upgrade(cfg, HEAD)
    assert _grants(url) == set(_migration.SEED)
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert _grants(url) == set()
    assert _sql(url, "SELECT count(*) FROM role_permissions WHERE resource <> 'candidates.compensation'")[0][0] == others
    command.upgrade(cfg, HEAD)
    assert _grants(url) == set(_migration.SEED)
