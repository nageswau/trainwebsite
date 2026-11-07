"""pob-007 -- migration 0301_bd_activity (DEC-SCOPE-421): the chain, frozen check copies, and a lossless round trip for existing rows (the
downgrade removes only LinkedIn messages and turns company visits into company meetings). Runs in a throwaway database (the pob-023 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import RECRUITER_CALL_CHECKS, RECRUITER_FOLLOW_UP_CHECKS, RECRUITER_MEETING_CHECKS, RECRUITER_MESSAGE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_007_migration_0301", VERSIONS / "0301_bd_activity.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0301_bd_activity", "0300_vendor_master"
MODELS = {"recruiter_messages": RECRUITER_MESSAGE_CHECKS, "recruiter_calls": RECRUITER_CALL_CHECKS, "recruiter_meetings": RECRUITER_MEETING_CHECKS,
          "recruiter_follow_ups": RECRUITER_FOLLOW_UP_CHECKS}


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies_of_the_models():
    for table, checks in _migration.CHECKS.items():
        for name, sql in checks.items():
            assert MODELS[table][name] == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'recruiter_follow_ups'")}
    assert {"priority", "remind_at"} <= columns
    assert _sql(url, "SELECT count(*) FROM information_schema.tables WHERE table_name = 'recruiter_meeting_action_items'")[0][0] == 1
    command.downgrade(cfg, BASE)
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'recruiter_messages'")}
    assert "linkedin_action" not in columns
    command.upgrade(cfg, HEAD)
