"""nehn-005 -- migration 0196_role_permissions (DEC-SCOPE-281): the chain, the seed and the round trip, in a throwaway database (the
ccrm-040 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_005_migration_0196", VERSIONS / "0196_role_permissions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0196_role_permissions", "0195_agent_student_codes"


def test_migration_chains_after_0195():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_seeds_a_frozen_copy_of_the_default_grants():
    # The migration carries its own copy (a later edit to rbac.DEFAULT_GRANTS must not rewrite history); today they are equal.
    assert {role: set(keys) for role, keys in _migration.SEED.items()} == {role: set(keys) for role, keys in rbac.DEFAULT_GRANTS.items()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn005_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_with_seed(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "role_permissions" not in _tables(url)
    command.upgrade(cfg, HEAD)
    rows = {(r[0], f"{r[1]}.{r[2]}") for r in _sql(url, "SELECT role, resource, action FROM role_permissions")}
    assert rows == {(role, key) for role, keys in rbac.DEFAULT_GRANTS.items() for key in keys}
    command.downgrade(cfg, BASE)
    assert "role_permissions" not in _tables(url)
