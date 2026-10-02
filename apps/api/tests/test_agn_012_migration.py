"""AGN-012 -- migration 0061_agent_visa_details (spec §3). Round trip and downgrade refusals run in a throwaway database built from
scratch (the AGN-013 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()
itself."""

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_012_migration_0061", VERSIONS / "0061_agent_visa_details.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0060_agent_app_enrollment"
HEAD = "0061_agent_visa_details"
CASE_COLUMNS = "SELECT id, application_id, status, appointment_date, checklist::text, tracking_reference FROM visa_cases ORDER BY id"
NEW = ("visa_application_date", "interview_date", "decision", "decided_at")


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0060_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_declares_the_new_columns_nullable_with_the_decision_check():
    from app.models import VisaCase

    columns = VisaCase.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name
    checks = {c.name: str(c.sqltext) for c in VisaCase.__table__.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == {"ck_visa_cases_decision": _migration.DECISION_CHECK}


@pytest.mark.asyncio
async def test_new_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("visa_cases")})
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
    """A fresh database at 0060 with one application and one legacy visa case."""
    cfg = _config()
    original = settings.database_url
    name = f"agn012_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("student", "country", "university", "application", "case")}
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'student user', 'overseas_student', 'overseas', true, true, 'en-GB', '{}')",
            {"id": ids["student"], "email": f"student-{name}@example.local"},
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
            "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :student, :university, 'visa_documentation', 'Sep 2027')",
            {"id": ids["application"], "student": ids["student"], "university": ids["university"]},
        )
        _sql(
            url,
            "INSERT INTO visa_cases (id, application_id, status, appointment_date, checklist, tracking_reference) "
            "VALUES (:id, :app, 'not_started', DATE '2027-05-01', '[\"Passport\", \"Visa form\"]', 'TR-1')",
            {"id": ids["case"], "app": ids["application"]},
        )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_cases_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, CASE_COLUMNS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, CASE_COLUMNS) == before
    assert _sql(url, f"SELECT {', '.join(NEW)} FROM visa_cases") == [(None, None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, CASE_COLUMNS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, CASE_COLUMNS) == before


def test_the_database_refuses_an_unknown_decision(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError):
        _sql(url, "UPDATE visa_cases SET decision = 'pending'")
    _sql(url, "UPDATE visa_cases SET decision = 'refused'")


@pytest.mark.parametrize(("column", "value"), [("visa_application_date", "DATE '2027-04-01'"), ("interview_date", "DATE '2027-05-02'"), ("decision", "'approved'"), ("decided_at", "now()")])
def test_downgrade_refuses_to_lose_visa_details(isolated_db, column, value):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"UPDATE visa_cases SET {column} = {value}")
    with pytest.raises(RuntimeError, match="visa details exist"):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(HEAD,)]
    assert _sql(url, f"SELECT count(*) FROM visa_cases WHERE {column} IS NOT NULL") == [(1,)]
