"""hrc-034 -- migration 0293_portal_events (DEC-SCOPE-415 I1/I3): the table, the grant, the chain and the round trip, in a throwaway database (the
hrc-020 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.core.rbac import DEFAULT_GRANTS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

HEAD = "0293_portal_events"
_spec = importlib.util.spec_from_file_location("_hrc_034_migration", VERSIONS / f"{HEAD}.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
BASE = _migration.down_revision
GRANT = "SELECT role FROM role_permissions WHERE resource = 'reports.recruitment_insights' AND action = 'view' ORDER BY role"
TABLE = "SELECT to_regclass('public.portal_events')::text"
INDEXES = "SELECT indexname FROM pg_indexes WHERE tablename = 'portal_events' ORDER BY 1"


def test_migration_chains_and_there_is_one_head():
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def test_the_seed_matches_the_default_grants():
    assert _migration.ROLES == ("hr_manager", "partner", "placement_manager")
    assert all("reports.recruitment_insights.view" in DEFAULT_GRANTS[role] for role in _migration.ROLES)


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc034_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert _sql(url, TABLE)[0][0] == "portal_events"
        assert [r[0] for r in _sql(url, GRANT)] == list(_migration.ROLES)
        command.downgrade(cfg, BASE)
        assert _sql(url, TABLE)[0][0] is None and _sql(url, GRANT) == []
        command.upgrade(cfg, HEAD)  # replays cleanly, now really creating the table
        assert _sql(url, TABLE)[0][0] == "portal_events"
        assert {"ix_portal_events_day", "uq_portal_events_once"} <= {r[0] for r in _sql(url, INDEXES)}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
