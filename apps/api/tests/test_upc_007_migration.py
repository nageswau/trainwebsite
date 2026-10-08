"""upc-007 -- migration 0106_university_pipeline (spec §2, M1). Round trip, backfill and the downgrade refusal run in a throwaway database
built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_007_migration_0106", VERSIONS / "0106_university_pipeline.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0105_university_master", "0106_university_pipeline"
NEW_COLUMNS = {"stage", "stage_changed_at", "lost_at", "lost_reason"}
HISTORY_COLUMNS = {"id", "university_id", "actor_user_id", "kind", "from_stage", "to_stage", "note", "position", "created_at"}
CATALOGUE = "SELECT id, slug, name, university_code, catalogue_visible FROM universities ORDER BY slug"


def test_migration_chains_after_0105_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_PIPELINE_CHECKS, UNIVERSITY_STAGE_HISTORY_CHECKS, University, UniversityStageHistory

    table = University.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.stage.nullable and not table.c.stage_changed_at.nullable
    assert UNIVERSITY_PIPELINE_CHECKS == _migration.CHECKS
    assert UNIVERSITY_STAGE_HISTORY_CHECKS == _migration.HISTORY_CHECKS
    assert {c.name for c in UniversityStageHistory.__table__.columns} == HISTORY_COLUMNS


@pytest.mark.asyncio
async def test_columns_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, indexes, tables = await conn.run_sync(
        lambda sync: (
            {c["name"] for c in inspect(sync).get_columns("universities")},
            {i["name"] for i in inspect(sync).get_indexes("universities")},
            set(inspect(sync).get_table_names()),
        )
    )
    assert NEW_COLUMNS <= columns
    assert "ix_universities_stage" in indexes
    assert "university_stage_history" in tables


@pytest.fixture
def isolated_db():
    """A fresh database at 0105 holding two universities."""
    cfg = _config()
    original = settings.database_url
    name = f"upc007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
        for slug, created in (("zeta-university", datetime(2024, 1, 2, tzinfo=UTC)), ("alpha-university", datetime(2025, 6, 7, tzinfo=UTC))):
            _sql(
                url,
                "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships, created_at) "
                "VALUES (gen_random_uuid(), :country, :slug, :slug, 'London', 'An overview', '', '[]', '[]', '[]', :created)",
                {"country": country, "slug": slug, "created": created},
            )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_target_and_changed_at_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, CATALOGUE)
    command.upgrade(cfg, HEAD)
    rows = _sql(url, "SELECT stage, stage_changed_at = created_at, lost_at, lost_reason FROM universities ORDER BY slug")
    assert rows == [("target_university", True, None, None)] * 2  # PS2: everyone starts at Target University
    assert _sql(url, "SELECT count(*) FROM university_stage_history") == [(0,)]
    assert _sql(url, CATALOGUE) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, CATALOGUE) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, CATALOGUE) == before


def test_constraints_hold_and_downgrade_refuses_while_pipeline_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_universities_stage"):
        _sql(url, "UPDATE universities SET stage = 'signed'")
    with pytest.raises(Exception, match="ck_universities_lost"):
        _sql(url, "UPDATE universities SET lost_at = now()")
    _sql(url, "UPDATE universities SET stage = 'interested' WHERE slug = 'alpha-university'")
    with pytest.raises(Exception, match="stage history, lost or moved universities exist"):
        command.downgrade(cfg, BASE)
