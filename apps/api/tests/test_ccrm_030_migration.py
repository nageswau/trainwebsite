"""ccrm-030 -- migration 0189_counselor_reminders (DEC-SCOPE-269): the chain, the CHECKs and keys it repeats, the RM1 seed, the unique
dedupe key and the round trip, in a throwaway database (the ccrm-018 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_030_migration_0189", VERSIONS / "0189_counselor_reminders.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0189_counselor_reminders", "0188_student_document_requests"


def test_migration_chains_after_0188_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_and_catalogue():
    from app.models import COUNSELOR_REMINDER_CHECKS, COUNSELOR_REMINDER_RULE_KEYS
    from app.services.counselor_reminders import RULES

    assert _migration.CHECKS == COUNSELOR_REMINDER_CHECKS
    assert _migration.RULE_KEYS == COUNSELOR_REMINDER_RULE_KEYS == tuple(RULES)
    assert _migration.DEFAULTS == {k: (r.offset, bool(r.student)) for k, r in RULES.items()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm030_migration_{uuid.uuid4().hex[:8]}"
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


def test_tables_seed_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not {"counselor_reminder_rules", "counselor_reminder_log"} & _tables(url)
    command.upgrade(cfg, HEAD)
    assert {"counselor_reminder_rules", "counselor_reminder_log"} <= _tables(url)
    seeded = {r[0]: (r[1], r[2], r[3]) for r in _sql(url, "SELECT rule_key, enabled, offset_days, notify_student FROM counselor_reminder_rules")}
    assert seeded == {k: (True, o, s) for k, (o, s) in _migration.DEFAULTS.items()}
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "UPDATE counselor_reminder_rules SET offset_days = 61 WHERE rule_key = 'no_response'")
    insert = "INSERT INTO counselor_reminder_log (id, rule_key, dedupe_key, subject_id, summary) VALUES (:id, 'deposit_due', 'k', :s, 'x')"
    _sql(url, insert, {"id": uuid.uuid4(), "s": uuid.uuid4()})
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, insert, {"id": uuid.uuid4(), "s": uuid.uuid4()})
    command.downgrade(cfg, BASE)
    assert not {"counselor_reminder_rules", "counselor_reminder_log"} & _tables(url)
