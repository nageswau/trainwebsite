"""itc-007 -- migration 0224_lead_merge (DEC-SCOPE-339): `enquiries.merged_at` / `merged_by_user_id` and their CHECK. Round trip in a
throwaway database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import Enquiry
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_007_migration_0223", VERSIONS / "0224_lead_merge.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0224_lead_merge"
BASE = "0223_lead_nurture_stage"
CHECK = "ck_enquiries_merged"
COLUMNS = "SELECT column_name FROM information_schema.columns WHERE table_name = 'enquiries' AND column_name LIKE 'merged%' ORDER BY 1"
CHECKS = f"SELECT conname FROM pg_constraint WHERE conname = '{CHECK}'"


def test_migration_chains_after_0223_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert {"merged_at", "merged_by_user_id"} <= {c.name for c in Enquiry.__table__.columns}
    assert CHECK in {c.name for c in Enquiry.__table__.constraints}


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    names = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("enquiries")})
    assert {"merged_at", "merged_by_user_id"} <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc007_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_adds_and_drops_the_columns_and_check(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, COLUMNS) == [] and _sql(url, CHECKS) == []
    command.upgrade(cfg, HEAD)
    assert [r[0] for r in _sql(url, COLUMNS)] == ["merged_at", "merged_by_user_id"] and len(_sql(url, CHECKS)) == 1
    command.downgrade(cfg, BASE)
    assert _sql(url, COLUMNS) == []
    command.upgrade(cfg, HEAD)
    assert len(_sql(url, CHECKS)) == 1
