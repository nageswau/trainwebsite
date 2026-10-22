"""ccrm-003 -- migration 0169_lead_next_action (DEC-SCOPE-243): `enquiries.next_action` / `next_action_due`. Round trip in a throwaway
database built from scratch (the csc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py
calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_003_migration_0169", VERSIONS / "0169_lead_next_action.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0168_application_sub_status", "0169_lead_next_action"
COLUMNS = {"next_action", "next_action_due"}


def test_migration_chains_after_0168_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_NEXT_ACTION_MAX, Enquiry

    assert LEAD_NEXT_ACTION_MAX == _migration.MAX == 200
    assert COLUMNS <= {c.name for c in Enquiry.__table__.columns}
    assert "ck_enquiries_next_action_len" in {c.name for c in Enquiry.__table__.constraints}


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    names = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("enquiries")})
    assert COLUMNS <= names


@pytest.fixture
def isolated_db():
    """A fresh database at 0168_application_sub_status."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'enquiries'")}


def test_round_trip_adds_and_drops_the_columns_and_checks_the_length(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not COLUMNS & _columns(url)
    command.upgrade(cfg, HEAD)
    assert COLUMNS <= _columns(url)
    insert = ("INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json, next_action) "
              "VALUES (gen_random_uuid(), 'overseas', 'Lead', 'l@example.com', 'S', '', 'website', 'new', 'pending', '{}', :a)")
    with pytest.raises(Exception, match="ck_enquiries_next_action_len"):
        _sql(url, insert, {"a": ""})
    _sql(url, insert, {"a": "Call about the IELTS date"})
    command.downgrade(cfg, BASE)
    assert not COLUMNS & _columns(url)
