"""pob-010 -- migration 0300_vendor_master (DEC-SCOPE-420): the chain, the frozen checks, the grants and the round trip, in a throwaway database
(the pob-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import COMPANY_DOCUMENT_KINDS, COMPANY_VENDOR_CHECKS, RECRUITER_CONTRACT_VENDOR_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_010_migration", VERSIONS / "0300_vendor_master.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
KEPT = "00000000-0000-4000-8000-000000000010"


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.COMPANY_CHECKS == COMPANY_VENDOR_CHECKS and _migration.CONTRACT_CHECKS == RECRUITER_CONTRACT_VENDOR_CHECKS
    assert _migration.KINDS == COMPANY_DOCUMENT_KINDS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob010_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # builds today's models, then runs every guarded step
        command.downgrade(cfg, BASE)  # so the base really lacks what 0300 adds
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _company_columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'companies'")}


def test_the_round_trip_keeps_rows_and_normalises_an_unknown_type(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "vendor_status" not in _company_columns(url)
    assert _sql(url, "SELECT count(*) FROM role_permissions WHERE resource = 'commercials.vendor'") == [(0,)]
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{KEPT}', 'Pob 010 Kept', 'odd-value', 'internal')", autocommit=True)

    command.upgrade(cfg, HEAD)
    assert _sql(url, f"SELECT partner_type, vendor_status FROM companies WHERE id = '{KEPT}'") == [("recruiter", None)]
    grants = {tuple(r) for r in _sql(url, "SELECT role, action FROM role_permissions WHERE resource = 'commercials.vendor'")}
    assert grants == {("placement_team", "view"), ("placement_team", "edit"), ("placement_manager", "view"), ("placement_manager", "edit")}
    assert _sql(url, "SELECT count(*) FROM information_schema.tables WHERE table_name = 'company_vendor_status_history'") == [(1,)]

    command.downgrade(cfg, BASE)
    assert "vendor_status" not in _company_columns(url)
    assert _sql(url, f"SELECT count(*) FROM companies WHERE id = '{KEPT}'") == [(1,)]
    command.upgrade(cfg, HEAD)


def test_the_downgrade_refuses_while_a_vendor_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type, vendor_status) VALUES ('{KEPT}', 'Pob 010 V', 'vendor', 'internal', 'prospect')", autocommit=True)
    with pytest.raises(RuntimeError, match="vendors exist"):
        command.downgrade(cfg, BASE)
