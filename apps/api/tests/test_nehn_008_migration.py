"""nehn-008 -- migration 0207_field_financial_grant (DEC-SCOPE-300): the chain, the seed and the round trip, in a throwaway database
(the ccrm-040 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_008_migration_0207", VERSIONS / "0207_field_financial_grant.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0207_field_financial_grant", "0206_user_permission_overrides"


def test_migration_chains_after_0206():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_seed_is_a_frozen_copy_of_the_new_default_grants():
    holders = {(role, "field.financial", "view") for role, keys in rbac.DEFAULT_GRANTS.items() if "field.financial.view" in keys}
    assert set(_migration.SEED) == holders


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn008_migration_{uuid.uuid4().hex[:8]}"
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
    return {tuple(r) for r in _sql(url, "SELECT role, resource, action FROM role_permissions WHERE resource = 'field.financial'")}


def test_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _grants(url) == set()
    command.upgrade(cfg, HEAD)
    assert _grants(url) == set(_migration.SEED)
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert _grants(url) == set()
    command.upgrade(cfg, HEAD)
    assert _grants(url) == set(_migration.SEED)
