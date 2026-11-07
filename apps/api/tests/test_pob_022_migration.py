"""pob-022 -- migration 0301_interview_automation (DEC-SCOPE-421 A2/A7): the markers, the settings row and its checks, the no-backlog stamp, the
chain and the round trip, in a throwaway database (the hrc-020 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import INTERVIEW_AUTOMATION_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

HEAD = "0301_interview_automation"
BASE = "0300_vendor_master"
_spec = importlib.util.spec_from_file_location("_pob_022_migration", VERSIONS / f"{HEAD}.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
COLUMNS = ("SELECT column_name FROM information_schema.columns WHERE table_name = 'interviews' AND column_name IN "
           "('first_reminder_at', 'second_reminder_at', 'chase_follow_up_id', 'chase_escalated_at') ORDER BY 1")  # fmt: skip
ROW = ("SELECT first_reminder_hours, second_reminder_hours, chase_after_hours, escalate_after_hours, reminder_template_id, chase_template_id "
       "FROM interview_automation_settings WHERE id = 1")  # fmt: skip
TABLE = "SELECT count(*) FROM information_schema.tables WHERE table_name = 'interview_automation_settings'"


def test_migration_chains_and_there_is_one_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def test_the_checks_match_the_model():
    assert _migration.CHECKS == INTERVIEW_AUTOMATION_CHECKS


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"pob022_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    names = ["chase_escalated_at", "chase_follow_up_id", "first_reminder_at", "second_reminder_at"]
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert [r[0] for r in _sql(url, COLUMNS)] == names
        assert list(_sql(url, ROW)[0]) == [24, 2, 24, 24, None, None]
        command.downgrade(cfg, BASE)
        assert _sql(url, COLUMNS) == [] and _sql(url, TABLE)[0][0] == 0
        command.upgrade(cfg, HEAD)  # replays cleanly, now really adding the columns and the table
        assert [r[0] for r in _sql(url, COLUMNS)] == names and list(_sql(url, ROW)[0]) == [24, 2, 24, 24, None, None]
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
