"""nehn-036 -- migration 0197_course_icons (DEC-SCOPE-285 I3). The round trip runs in a throwaway database built from scratch (the upc-001
pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_036_migration_0197", VERSIONS / "0197_course_icons.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0196_role_permissions", "0197_course_icons"
CHECK = "ck_overseas_courses_icon"


def test_migration_chains_after_0196_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COURSE_ICONS, OverseasCourse

    table = OverseasCourse.__table__
    assert _migration.ICONS == COURSE_ICONS and _migration.CHECK_SQL == str(next(c for c in table.constraints if c.name == CHECK).sqltext)
    column = table.c.icon
    assert column.nullable and column.type.length == 20


@pytest.mark.asyncio
async def test_column_and_check_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, checks = await conn.run_sync(
        lambda sync: ({c["name"]: c for c in inspect(sync).get_columns("overseas_courses")}, {c["name"] for c in inspect(sync).get_check_constraints("overseas_courses")})
    )
    assert columns["icon"]["nullable"] and CHECK in checks


def _columns(url) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'overseas_courses'")}


def _insert_course(url, icon=None):
    country = _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, work_opportunities, post_study_work, pr_opportunities, visa_process, faq) "
        "VALUES (gen_random_uuid(), :slug, 'Land', '', '', '', '', '', '', '[]', '[]') RETURNING id",
        {"slug": uuid.uuid4().hex[:10]},
    )[0][0]
    uni = _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (gen_random_uuid(), :c, :slug, 'Uni', :slug, 'City', '', '', '[]', '[]', '[]') RETURNING id",
        {"c": country, "slug": uuid.uuid4().hex[:10]},
    )[0][0]
    return _sql(
        url,
        "INSERT INTO overseas_courses (id, university_id, title, level, category, duration, tuition_fee, intake) VALUES (gen_random_uuid(), :u, 'MSc', 'PG', 'Law', '1 year', '', '') RETURNING id",
        {"u": uni},
    )[0][0]


@pytest.fixture
def isolated_db():
    """A fresh database at 0196 holding one course."""
    cfg = _config()
    original = settings.database_url
    name = f"nehn036_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url, "course": _insert_course(url)}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_makes_existing_courses_automatic_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "icon" not in _columns(url)
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT icon FROM overseas_courses WHERE id = :id", {"id": isolated_db["course"]}) == [(None,)]  # automatic
    _sql(url, "UPDATE overseas_courses SET icon = 'law' WHERE id = :id", {"id": isolated_db["course"]})
    with pytest.raises(Exception, match=CHECK):
        _sql(url, "UPDATE overseas_courses SET icon = 'rocket' WHERE id = :id", {"id": isolated_db["course"]})
    command.downgrade(cfg, BASE)
    assert "icon" not in _columns(url)
    command.upgrade(cfg, HEAD)  # idempotent re-upgrade
    assert "icon" in _columns(url)
