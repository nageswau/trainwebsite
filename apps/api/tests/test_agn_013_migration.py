"""AGN-013 -- migration 0060_agent_app_enrollment (spec §3). Round trip and downgrade refusals run in a throwaway database
built from scratch (the AGN-008 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_013_migration_0060", VERSIONS / "0060_agent_app_enrollment.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0059_agent_tasks"
HEAD = "0060_agent_app_enrollment"
APP_COLUMNS = "SELECT id, student_id, university_id, status, intake, agent_id FROM overseas_applications ORDER BY id"
NEW = ("enrollment_date", "university_student_id", "enrollment_confirmed_at")


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0059_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW
    # One head, without pinning it to this revision: AGN-017's 0061 chains after 0060 (the AGN-016 test's form).
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1
    assert ScriptDirectory.from_config(_config()).get_revision(HEAD) is not None


def test_model_declares_the_new_columns_nullable():
    from app.models import OverseasApplication

    columns = OverseasApplication.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name
    assert columns["university_student_id"].type.length == 60


@pytest.mark.asyncio
async def test_new_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("overseas_applications")})
    for name in NEW:
        assert name in cols and cols[name]["nullable"], name


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@pytest.fixture
def isolated_db():
    """A fresh database at 0059 with one application."""
    cfg = _config()
    original = settings.database_url
    name = f"agn013_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("agent", "student", "country", "university", "application")}
        for key, role in (("agent", "agent"), ("student", "overseas_student")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, 'overseas', true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": f"{key} user", "role": role},
            )
        _sql(
            url,
            "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
            "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
            {"id": ids["country"], "slug": f"c-{name}"},
        )
        _sql(
            url,
            "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
            "VALUES (:id, :country, :slug, 'Mig University', 'Town', '', '', '[]', '[]', '[]')",
            {"id": ids["university"], "country": ids["country"], "slug": f"u-{name}"},
        )
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, agent_id, status, intake) VALUES (:id, :student, :university, :agent, 'enrolled', 'Sep 2027')",
            {"id": ids["application"], "student": ids["student"], "university": ids["university"], "agent": ids["agent"]},
        )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, APP_COLUMNS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, APP_COLUMNS) == before
    assert _sql(url, f"SELECT {', '.join(NEW)} FROM overseas_applications") == [(None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, APP_COLUMNS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, APP_COLUMNS) == before


@pytest.mark.parametrize(("column", "value"), [("enrollment_date", "DATE '2027-09-01'"), ("university_student_id", "'S-1'"), ("enrollment_confirmed_at", "now()")])
def test_downgrade_refuses_to_lose_enrollment_details(isolated_db, column, value):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"UPDATE overseas_applications SET {column} = {value}")
    with pytest.raises(RuntimeError, match="enrollment details exist"):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(HEAD,)]
    assert _sql(url, f"SELECT count(*) FROM overseas_applications WHERE {column} IS NOT NULL") == [(1,)]
