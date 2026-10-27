"""nehn-012 -- migration 0205_enquiry_list_indexes (DEC-SCOPE-298). The round trip runs in a throwaway database built from scratch (the
upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_012_migration_0205", VERSIONS / "0205_enquiry_list_indexes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0204_certificate_workflow", "0205_enquiry_list_indexes"
INDEXES = {"ix_enquiries_created": ["created_at", "id"], "ix_enquiries_owner": ["owner_id"]}


def test_migration_chains_after_0204_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import Enquiry

    indexes = {i.name: [c.name for c in i.columns] for i in Enquiry.__table__.indexes}
    assert {name: indexes.get(name) for name in INDEXES} == INDEXES == _migration.INDEXES


@pytest.mark.asyncio
async def test_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    names = await conn.run_sync(lambda sync: {i["name"] for i in inspect(sync).get_indexes("enquiries")})
    assert set(INDEXES) <= names


def _indexes(url) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename = 'enquiries'")}


@pytest.fixture
def isolated_db():
    """A fresh database at 0204 holding one lead."""
    cfg = _config()
    original = settings.database_url
    name = f"nehn012_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        _sql(
            url,
            "INSERT INTO enquiries (id, division, name, subject, message, source, status, crm_sync_status, metadata_json) "
            "VALUES (gen_random_uuid(), 'it', 'Asha', 'Python', 'Hello', 'website', 'new', 'pending', '{}')",
        )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_adds_the_indexes_keeps_rows_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not set(INDEXES) & _indexes(url)
    command.upgrade(cfg, HEAD)
    assert set(INDEXES) <= _indexes(url)
    assert _sql(url, "SELECT count(*) FROM enquiries") == [(1,)]
    command.downgrade(cfg, BASE)
    assert not set(INDEXES) & _indexes(url)
    command.upgrade(cfg, HEAD)  # idempotent re-upgrade
    assert set(INDEXES) <= _indexes(url)
