"""hrc-032 -- migration 0291_recruitment_notices (DEC-SCOPE-412 N6/N7/N10): the two markers, today's open records stamped so the first sweep tells
nobody about old ones, the grant, the chain and the round trip, in a throwaway database (the hrc-020 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.core.rbac import DEFAULT_GRANTS
from app.models import JOB_OPEN_STATUSES
from tests.test_upc_001_migration import VERSIONS, _config, _sql

HEAD = "0291_recruitment_notices"
BASE = "0290_contact_status"
_spec = importlib.util.spec_from_file_location("_hrc_032_migration", VERSIONS / f"{HEAD}.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
GRANT = "SELECT role FROM role_permissions WHERE resource = 'notifications' AND action = 'retry' ORDER BY role"
COLUMNS = "SELECT column_name FROM information_schema.columns WHERE column_name IN ('overdue_notified_at', 'match_notified_at') ORDER BY 1"


def test_migration_chains_and_there_is_one_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def test_the_seed_matches_the_default_grants_and_the_stamp_names_every_open_status():
    assert _migration.SEED == (("hr_manager", "notifications", "retry"), ("placement_manager", "notifications", "retry"))
    assert all("notifications.retry" in DEFAULT_GRANTS[role] for role, _, _ in _migration.SEED)
    source = (VERSIONS / f"{HEAD}.py").read_text(encoding="utf-8")
    assert all(f"'{status}'" in source for status in JOB_OPEN_STATUSES)


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc032_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert [r[0] for r in _sql(url, COLUMNS)] == ["match_notified_at", "overdue_notified_at"]
        assert [r[0] for r in _sql(url, GRANT)] == ["hr_manager", "placement_manager"]
        command.downgrade(cfg, BASE)
        assert _sql(url, COLUMNS) == [] and _sql(url, GRANT) == []
        command.upgrade(cfg, HEAD)  # replays cleanly, now really adding the columns
        assert [r[0] for r in _sql(url, COLUMNS)] == ["match_notified_at", "overdue_notified_at"]
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
