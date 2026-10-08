"""upc-003 -- migration 0105_university_master (spec §2). Round trip, backfill and the downgrade refusal run in a throwaway database built
from scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_003_migration_0105", VERSIONS / "0105_university_master.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0104_skills_master", "0105_university_master"
NEW_COLUMNS = {
    "university_code",
    "institution_type",
    "ownership_type",
    "state_region",
    "website",
    "course_levels",
    "popular_programs",
    "international_office",
    "existing_relationship",
    "primary_manager_user_id",
    "backup_manager_user_id",
    "priority",
    "partnership_potential",
    "active",
    "catalogue_visible",
}
CATALOGUE = "SELECT id, slug, name, country_id, city, overview FROM universities ORDER BY slug"


def test_migration_chains_after_0104_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_CHECKS, University, UniversityAssignmentHistory, UniversityRanking

    table = University.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.university_code.nullable and not table.c.institution_type.nullable
    assert UNIVERSITY_CHECKS == _migration.CHECKS  # the migration repeats the model's CHECK strings
    assert {c.name for c in UniversityRanking.__table__.columns} == {"id", "university_id", "system", "other_name", "year", "rank", "created_at"}
    assert {c.name for c in UniversityAssignmentHistory.__table__.columns} == {"id", "university_id", "slot", "from_user_id", "to_user_id", "actor_user_id", "created_at"}


@pytest.mark.asyncio
async def test_columns_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, indexes, uniques = await conn.run_sync(
        lambda sync: (
            {c["name"] for c in inspect(sync).get_columns("universities")},
            {i["name"] for i in inspect(sync).get_indexes("universities")},
            {u["name"] for u in inspect(sync).get_unique_constraints("universities")},
        )
    )
    assert NEW_COLUMNS <= columns
    assert {"ix_universities_primary_manager", "ix_universities_backup_manager", "ix_universities_priority"} <= indexes
    assert "uq_universities_code" in uniques


@pytest.fixture
def isolated_db():
    """A fresh database at 0103 holding two catalogue universities."""
    cfg = _config()
    original = settings.database_url
    name = f"upc003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
        for slug in ("zeta-university", "alpha-university"):
            _sql(
                url,
                "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
                "VALUES (gen_random_uuid(), :country, :slug, :slug, 'London', 'An overview', '', '[]', '[]', '[]')",
                {"country": country, "slug": slug},
            )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_codes_keeps_rows_public_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, CATALOGUE)
    command.upgrade(cfg, HEAD)
    rows = _sql(url, "SELECT slug, university_code, institution_type, active, catalogue_visible FROM universities ORDER BY university_code")
    assert [r[0] for r in rows] == ["zeta-university", "alpha-university"]  # created_at order (inserted first = first code)
    assert all(r[1].startswith("UNV-") and len(r[1]) == 10 and r[2] == "university" and r[3] and r[4] for r in rows)
    assert _sql(url, CATALOGUE) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, CATALOGUE) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, CATALOGUE) == before


def test_constraints_hold_and_downgrade_refuses_while_master_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_universities_institution_type"):
        _sql(url, "UPDATE universities SET institution_type = 'school'")
    with pytest.raises(Exception, match="ck_universities_priority"):
        _sql(url, "UPDATE universities SET priority = 'D'")
    _sql(url, "UPDATE universities SET catalogue_visible = false WHERE slug = 'alpha-university'")
    with pytest.raises(Exception, match="internal universities exist"):
        command.downgrade(cfg, BASE)
