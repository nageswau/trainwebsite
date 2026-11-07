"""pob-009 -- migration 0304_po_targets_reports: the chain, the frozen checks and the round trip, in a throwaway database (the pob-010
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import (
    PO_TARGET_KPIS,
    RECRUITER_ACTIVITY_REPORT_CHECKS,
    RECRUITER_PLAN_ITEM_CHECKS,
    RECRUITER_TARGET_CHECKS,
    RECRUITER_TARGET_COMPANY_CHECKS,
)
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_009_migration", VERSIONS / "0304_po_targets_reports.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
KEPT = "00000000-0000-4000-8000-000000000009"


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.KPIS == PO_TARGET_KPIS
    assert _migration.TARGET_CHECKS == RECRUITER_TARGET_CHECKS and _migration.TARGET_COMPANY_CHECKS == RECRUITER_TARGET_COMPANY_CHECKS
    assert _migration.PLAN_ITEM_CHECKS == RECRUITER_PLAN_ITEM_CHECKS and _migration.REPORT_CHECKS == RECRUITER_ACTIVITY_REPORT_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob009_migration_{uuid.uuid4().hex[:8]}"
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


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'recruiter_%'")}


def _territory(url) -> int:
    return _sql(url, "SELECT count(*) FROM information_schema.columns WHERE column_name = 'territory' AND table_name IN ('companies', 'recruiter_profiles')")[0][0]


def test_the_round_trip_keeps_companies(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "recruiter_targets" not in _tables(url) and _territory(url) == 0
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{KEPT}', 'Pob 009 Kept', 'recruiter', 'internal')", autocommit=True)

    command.upgrade(cfg, HEAD)
    assert {"recruiter_targets", "recruiter_target_companies", "recruiter_plan_items", "recruiter_activity_reports"} <= _tables(url)
    assert _territory(url) == 2
    assert _sql(url, f"SELECT territory FROM companies WHERE id = '{KEPT}'") == [(None,)]

    command.downgrade(cfg, BASE)
    assert "recruiter_targets" not in _tables(url) and _territory(url) == 0
    assert _sql(url, f"SELECT count(*) FROM companies WHERE id = '{KEPT}'") == [(1,)]
    command.upgrade(cfg, HEAD)
