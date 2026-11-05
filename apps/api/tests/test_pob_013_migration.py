"""pob-013 -- migration 0288_college_placement (DEC-SCOPE-410): the chain, the frozen CHECK copies and the round trip, in a throwaway
database (the pob-003 0283 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import PLACEMENT_CHECKS, PLACEMENT_CONTACT_METHOD_CHECK
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_013_migration_0288", VERSIONS / "0288_college_placement.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0288_college_placement"
BASE = _migration.down_revision
TABLES = ("bdm_org_placement_profiles", "bdm_org_courses", "bdm_org_placement_batches", "bdm_org_placement_events", "bdm_org_tpo_interactions")
COLUMNS = ("office_details", "preferred_contact_method")


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.CHECKS == PLACEMENT_CHECKS
    assert _migration.CONTACT_METHOD_CHECK == PLACEMENT_CONTACT_METHOD_CHECK
    assert set(_migration.TABLES) == set(TABLES)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob013_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_organization_contacts'")}


def test_upgrade_adds_and_downgrade_removes_everything(isolated_db):
    """A database built at BASE by 0001's create_all already has today's tables; the downgrade proves they go, the upgrade that they return."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and set(COLUMNS) <= _columns(url)
    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url) and not set(COLUMNS) & _columns(url)
    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and set(COLUMNS) <= _columns(url)
