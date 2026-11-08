"""pob-018 -- migration 0308_candidate_sourcing (DEC-SCOPE-427): the chain, the frozen CHECK copies, the round trip and the
AC1 backfill, in a throwaway database (the pob-014 0306 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_SOURCING_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_018_migration_0308", VERSIONS / "0308_candidate_sourcing.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0308_candidate_sourcing"
BASE = _migration.down_revision
COLUMNS = {
    "source_date", "referrer_name", "referrer_candidate_id", "vendor_id", "portal_import_reference", "last_verified_on", "last_verified_by_user_id",
    "outreach_status", "outreach_status_changed_at", "outreach_permission_method", "outreach_permission_on", "outreach_permission_note",
    "outreach_permission_by_user_id",
}  # fmt: skip


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.CHECKS == CANDIDATE_SOURCING_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob018_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidates'")}


def _sources(url) -> set[str]:
    return {r[0].lower() for r in _sql(url, "SELECT name FROM rec_candidate_sources")}


def test_upgrade_backfills_seeds_and_round_trips(isolated_db):
    """A candidate that predates the column gets its created_at date (IST); the four sources exist once; downgrade then upgrade works."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)  # 0001's create_all already built today's columns: the guarded upgrade skips them
    assert COLUMNS <= _columns(url)
    command.downgrade(cfg, BASE)  # back to the pre-0308 shape
    assert not COLUMNS & _columns(url)
    source = _sql(url, "SELECT id FROM rec_candidate_sources ORDER BY sort_order LIMIT 1")[0][0]
    cid = uuid.uuid4()
    _sql(url, "INSERT INTO candidates (id, candidate_code, name, email, source_id, preferred_locations, created_at, updated_at) "
              f"VALUES ('{cid}', 'MIG-{cid.hex[:6]}', 'Old', 'old-{cid.hex[:6]}@example.com', '{source}', '[]', "
              "'2026-01-10 20:30:00+00', now())", autocommit=True)  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert COLUMNS <= _columns(url)
    row = _sql(url, f"SELECT source_date::text, outreach_status FROM candidates WHERE id = '{cid}'")[0]
    assert row == ("2026-01-11", "not_contacted")  # 20:30 UTC is the next day in IST
    assert {"vendor", "website", "community", "institution"} <= _sources(url)
    command.upgrade(cfg, HEAD)  # idempotent
    assert _sql(url, "SELECT count(*) FROM rec_candidate_sources WHERE lower(name) = 'vendor'")[0][0] == 1
