"""ccrm-031 -- migration 0190_overdue_escalation (DEC-SCOPE-272): the chain, the CHECK and keys it repeats, the E1 seed and the round
trip, in a throwaway database (the ccrm-030 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_031_migration_0190", VERSIONS / "0190_overdue_escalation.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0190_overdue_escalation", "0189_counselor_reminders"


def test_migration_chains_after_0189():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_and_catalogue():
    from app.models import COUNSELOR_REMINDER_CHECKS, COUNSELOR_REMINDER_RULE_KEYS
    from app.services.counselor_reminders import RULES

    assert _migration.RULE_KEYS == COUNSELOR_REMINDER_RULE_KEYS == tuple(RULES)
    assert _migration._key_check(_migration.RULE_KEYS) == COUNSELOR_REMINDER_CHECKS[_migration.KEY_CHECK]
    rule = RULES["overdue_escalation"]
    assert _migration.DEFAULT == ("overdue_escalation", rule.offset, bool(rule.student))


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm031_migration_{uuid.uuid4().hex[:8]}"
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


def _rules(url) -> dict:
    return {r[0]: (r[1], r[2], r[3]) for r in _sql(url, "SELECT rule_key, enabled, offset_days, notify_student FROM counselor_reminder_rules")}


def test_seed_check_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "overdue_escalation" not in _rules(url)
    with pytest.raises(sa.exc.IntegrityError):  # 0189's ten keys are back after the downgrade
        _sql(url, "INSERT INTO counselor_reminder_rules (rule_key, offset_days) VALUES ('overdue_escalation', 2)")
    command.upgrade(cfg, HEAD)
    assert _rules(url)["overdue_escalation"] == (True, 2, False) and len(_rules(url)) == 11
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "INSERT INTO counselor_reminder_rules (rule_key, offset_days) VALUES ('nope', 2)")
    _sql(url, "INSERT INTO counselor_reminder_log (id, rule_key, dedupe_key, subject_id, summary) VALUES (:id, 'overdue_escalation', 'k31', :s, 'x')", {"id": uuid.uuid4(), "s": uuid.uuid4()})
    command.downgrade(cfg, BASE)
    assert "overdue_escalation" not in _rules(url) and len(_rules(url)) == 10
    assert not _sql(url, "SELECT 1 FROM counselor_reminder_log WHERE rule_key = 'overdue_escalation'")
    command.upgrade(cfg, HEAD)  # re-runnable
    assert _rules(url)["overdue_escalation"] == (True, 2, False)
