"""nehn-031 -- migration 0203_certificate_workflow (DEC-SCOPE-296): the chain and the round trip, in a throwaway database (the nehn-003
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_031_migration_0203", VERSIONS / "0203_certificate_workflow.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0203_certificate_workflow", "0202_learning_resource_files"
GRANTS = "SELECT role, resource, action FROM role_permissions WHERE resource = 'certificates' ORDER BY 1, 3"


def test_migration_chains_after_0202():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"nehn031_migration_{uuid.uuid4().hex[:8]}"
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
    assert not {"certificate_rules", "certificate_requests"} & _tables(url)
    assert [tuple(r) for r in _sql(url, GRANTS)] == [("coordinator", "certificates", "view")]
    command.upgrade(cfg, HEAD)
    assert {"certificate_rules", "certificate_requests"} <= _tables(url)
    assert [tuple(r) for r in _sql(url, "SELECT division, min_progress_percent, min_attendance_percent FROM certificate_rules")] == [("it", 100, 75)]
    assert [tuple(r) for r in _sql(url, GRANTS)] == [
        ("coordinator", "certificates", "issue"),
        ("coordinator", "certificates", "override"),
        ("coordinator", "certificates", "view"),
        ("it_admin", "certificates", "configure"),
    ]
    command.downgrade(cfg, BASE)
    assert not {"certificate_rules", "certificate_requests"} & _tables(url)
    assert [tuple(r) for r in _sql(url, GRANTS)] == [("coordinator", "certificates", "view")]
