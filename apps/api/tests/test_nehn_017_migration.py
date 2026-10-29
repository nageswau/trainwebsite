"""nehn-017 -- migration 0218_hr_student_grants (DEC-SCOPE-310 H3): the chain, the seed and the round trip, in a throwaway database
(the nehn-009 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_017_migration_0216", VERSIONS / "0218_hr_student_grants.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0218_hr_student_grants", "0217_course_agent_commission"
RESOURCES = "('student_progress', 'attendance', 'student_documents')"


def test_migration_chains_after_0217():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_seed_is_a_frozen_copy_of_the_new_default_grants():
    holders = {(role, *rbac.parse_key(key)) for role, keys in rbac.DEFAULT_GRANTS.items() for key in keys if key.split(".")[0] in _migration.RESOURCES}
    assert set(_migration.SEED) == holders and {role for role, _, _ in holders} == {"hr_team"} and len(holders) == 6


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _grants(url) -> set[tuple]:
    return {tuple(r) for r in _sql(url, f"SELECT role, resource, action FROM role_permissions WHERE resource IN {RESOURCES}")}


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
