"""pob-027 -- migration 0317_intake_automation (DEC-SCOPE-434 I11): the chain, the frozen checks, the seeded template and the round trip,
in a throwaway database (the pob-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import json
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import ESCALATION_RULE_CHECKS, REQUIREMENT_TASK_CHECKS
from app.services.requirement_intake import DEFAULT_TEMPLATE
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_027_migration", VERSIONS / "0317_intake_automation.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
TABLES = ("escalation_events", "escalation_rules", "requirement_tasks", "requirement_automation_settings")


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_and_the_template_are_frozen_copies():
    assert _migration.TASK_CHECKS == REQUIREMENT_TASK_CHECKS
    assert _migration.RULE_CHECKS == ESCALATION_RULE_CHECKS
    assert _migration.DEFAULT_TEMPLATE == DEFAULT_TEMPLATE


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob027_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_the_round_trip_seeds_the_template_once(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so remove what 0317 adds first: the guarded upgrade must add it back
    for table in TABLES:
        _sql(url, f"DROP TABLE IF EXISTS {table}", autocommit=True)
    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url)
    [(template,)] = _sql(url, "SELECT task_template FROM requirement_automation_settings WHERE id = 1")
    assert (json.loads(template) if isinstance(template, str) else template) == DEFAULT_TEMPLATE
    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url)
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM requirement_automation_settings") == [(1,)]
