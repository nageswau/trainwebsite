"""hrc-033 -- migration 0293_recruitment_report_grants (DEC-SCOPE-415 D7): a seed only. The frozen copy equals `rbac.DEFAULT_GRANTS`, the chain and
the round trip hold, in a throwaway database (the hrc-020 pattern). Plain sync tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_033_migration_0293", VERSIONS / "0293_recruitment_report_grants.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0293_recruitment_report_grants", "0292_screening_sessions"
HOLDERS = ("placement_team", "placement_manager", "hr_manager", "placement_officer", "it_admin", "partner")
SEEDED = {(role, "reports.recruitment", action) for role in HOLDERS for action in ("view", "download")}
GRANTS = "SELECT role, resource, action FROM role_permissions WHERE resource = 'reports.recruitment'"


def test_migration_chains_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def test_the_frozen_seed_equals_the_default_grants():
    assert set(_migration.SEED) == SEEDED
    holders = {(role, *rbac.parse_key(key)) for role, keys in rbac.DEFAULT_GRANTS.items() for key in keys if key.startswith("reports.recruitment.")}
    assert holders == SEEDED


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc033_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert {tuple(row) for row in _sql(url, GRANTS)} == SEEDED
        command.downgrade(cfg, BASE)
        assert _sql(url, GRANTS) == []
        command.upgrade(cfg, HEAD)
        assert {tuple(row) for row in _sql(url, GRANTS)} == SEEDED
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
