"""AGN-008 -- migration 0057_agent_applications (spec §4). Round trip and downgrade refusals run in a throwaway database built from
scratch (the AGN-004 / ENH-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_008_migration_0057", VERSIONS / "0057_agent_applications.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0056_agent_shortlist"
APP_COLUMNS = "SELECT id, student_id, university_id, status, intake, agent_id FROM overseas_applications ORDER BY id"
NEW = ("agent_student_id", *_migration.DATES)


def test_migration_chains_after_0056_and_is_the_single_head():
    assert _migration.revision == "0057_agent_applications"
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1


def test_model_declares_the_new_columns_nullable():
    from app.models import OverseasApplication

    columns = OverseasApplication.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name
    assert columns["agent_student_id"].index


@pytest.mark.asyncio
async def test_new_columns_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("overseas_applications")})
    indexes = await conn.run_sync(lambda sync: {i["name"] for i in inspect(sync).get_indexes("overseas_applications")})
    for name in NEW:
        assert name in cols and cols[name]["nullable"], name
    assert _migration.INDEX in indexes


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
    """A fresh database at 0056 with one agency student and one application for a student with an account."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn008_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("agent", "student", "country", "university", "application", "record")}
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
            "INSERT INTO overseas_applications (id, student_id, university_id, agent_id, status, intake) VALUES (:id, :student, :university, :agent, 'enquiry', 'Fall 2027')",
            {"id": ids["application"], "student": ids["student"], "university": ids["university"], "agent": ids["agent"]},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'No Login')", {"id": ids["record"], "agent": ids["agent"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, APP_COLUMNS)
    command.upgrade(cfg, "0057_agent_applications")
    assert _sql(url, APP_COLUMNS) == before
    assert _sql(url, "SELECT agent_student_id, submitted_on, application_deadline, offer_deadline FROM overseas_applications") == [(None, None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, APP_COLUMNS) == before
    command.upgrade(cfg, "0057_agent_applications")
    assert _sql(url, APP_COLUMNS) == before


@pytest.mark.parametrize(
    ("setup_sql", "message"),
    [
        ("UPDATE overseas_applications SET agent_student_id = :record", "applications of agency students exist"),
        ("UPDATE overseas_applications SET submitted_on = DATE '2026-09-01'", "application dates exist"),
        ("UPDATE overseas_applications SET offer_deadline = DATE '2026-12-01'", "application dates exist"),
    ],
)
def test_downgrade_refuses_to_lose_agn008_data(isolated_db, setup_sql, message):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, "0057_agent_applications")
    _sql(url, setup_sql, {"record": ids["record"]})
    with pytest.raises(RuntimeError, match=message):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [("0057_agent_applications",)]
