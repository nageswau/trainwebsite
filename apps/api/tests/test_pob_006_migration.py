"""pob-006 -- migration 0297_crm_import_merge (DEC-SCOPE-418): the chain, the frozen checks, the seed and the round trip, in a throwaway database
(the pob-005 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CRM_IMPORT_BATCH_CHECKS, CRM_IMPORT_ROW_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_006_migration", VERSIONS / "0297_crm_import_merge.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
TABLES = ("crm_import_rows", "crm_import_batches")
COLUMNS = ("merged_into_id", "merged_at", "merged_by_user_id")


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_and_seed_are_frozen_copies():
    assert _migration.BATCH_CHECKS == CRM_IMPORT_BATCH_CHECKS and _migration.ROW_CHECKS == CRM_IMPORT_ROW_CHECKS
    assert set(_migration.SEED) == {("placement_manager", "crm", "import"), ("placement_manager", "crm", "merge")}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url, table) -> set[str]:
    return {r[0] for r in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_the_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so remove what 0297 adds first: the guarded upgrade must add it back
    for table in TABLES:
        _sql(url, f"DROP TABLE IF EXISTS {table}", autocommit=True)
    for table in ("companies", "company_contacts"):
        for column in COLUMNS:
            _sql(url, f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}", autocommit=True)
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('00000000-0000-4000-8000-000000000006', 'Pob 006 Kept', 'recruiter', 'internal')", autocommit=True)

    command.upgrade(cfg, HEAD)
    assert set(COLUMNS) <= _columns(url, "companies") and set(COLUMNS) <= _columns(url, "company_contacts")
    assert set(TABLES) <= _tables(url)
    grants = {r[0] for r in _sql(url, "SELECT action FROM role_permissions WHERE role = 'placement_manager' AND resource = 'crm'")}
    assert grants == {"import", "merge"}
    assert _sql(url, "SELECT merged_into_id FROM companies WHERE name = 'Pob 006 Kept'") == [(None,)]
    command.downgrade(cfg, BASE)
    assert not set(COLUMNS) & _columns(url, "companies") and not set(TABLES) & _tables(url)
    assert _sql(url, "SELECT count(*) FROM role_permissions WHERE resource = 'crm'") == [(0,)]
    assert _sql(url, "SELECT count(*) FROM companies WHERE name = 'Pob 006 Kept'") == [(1,)]
    command.upgrade(cfg, HEAD)
    assert set(COLUMNS) <= _columns(url, "companies")
