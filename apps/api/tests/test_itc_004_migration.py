"""itc-004 -- migration 0223_lead_nurture_stage (DEC-SCOPE-338 N2): Nurture in the `enquiries` status CHECK. Round trip in a throwaway
database built from scratch (the csc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py
calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_004_migration_0223", VERSIONS / "0223_lead_nurture_stage.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0223_lead_nurture_stage"
BASE = _migration.down_revision
INSERT = (
    "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json, created_at, updated_at) "
    "VALUES (:id, 'it', 'Lead', 'l@example.com', 'S', '', 'website', :status, 'pending', '{}', now(), now())"
)


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.lead_stages import STAGES
    from app.models import LEAD_STATUS_CHECK

    assert _migration.STAGES == STAGES and _migration.STATUS_CHECK == LEAD_STATUS_CHECK
    assert _migration.OLD_STAGES == tuple(s for s in STAGES if s != "nurture")


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc004_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_allows_nurture_and_the_downgrade_parks_it_at_follow_up(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    with pytest.raises(IntegrityError):
        _sql(url, INSERT, {"id": str(uuid.uuid4()), "status": "nurture"})
    command.upgrade(cfg, HEAD)
    parked = str(uuid.uuid4())
    _sql(url, INSERT, {"id": parked, "status": "nurture"})
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT status FROM enquiries WHERE id = :id", {"id": parked})[0][0] == "follow_up"
