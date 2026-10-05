"""AGN-006 -- migration 0055_agent_student_counseling (spec §4, AC09): single head after 0054, create-table only, matches the model,
database checks enforced, round trip keeps existing rows, downgrade refuses while counseling records exist.

Round trips run in a throwaway database built from scratch (the AGN-004 / ENH-001 pattern): a downgrade never runs against the shared
test database. Plain (non-async) round-trip tests: alembic/env.py calls asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings
from app.models import COUNSELING_CURRENCIES, AgentStudentCounseling
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_record

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_006_migration_0055", VERSIONS / "0055_agent_student_counseling.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

REV = "0055_agent_student_counseling"
BASE = "0054_school_onboarding_bulk"
TABLE = "agent_student_counseling"
STUDENTS = "SELECT id, agent_id, student_id, status, full_name FROM agent_students ORDER BY id"


def test_migration_follows_0054_and_is_the_single_head():
    assert _migration.revision == REV
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1


def test_currency_lists_agree():
    assert _migration.CURRENCIES == COUNSELING_CURRENCIES == ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")


@pytest.mark.asyncio
async def test_table_matches_the_model(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c["nullable"] for c in inspect(sync).get_columns(TABLE)})
    model = {c.name: c.nullable for c in AgentStudentCounseling.__table__.columns}
    assert cols == model
    assert cols["agent_student_id"] is False and cols["counseling_completed"] is False and cols["updated_by_user_id"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"budget_amount": Decimal("-1"), "budget_currency": "INR"}, "ck_agent_student_counseling_budget"),
        ({"budget_currency": "INR"}, "ck_agent_student_counseling_budget_pair"),
        ({"budget_amount": Decimal("5")}, "ck_agent_student_counseling_budget_pair"),
        ({"budget_amount": Decimal("5"), "budget_currency": "JPY"}, "ck_agent_student_counseling_currency"),
        ({"counseling_completed": True}, "ck_agent_student_counseling_completed"),
    ],
    ids=["negative", "currency-alone", "amount-alone", "unknown-currency", "completed-unstamped"],
)
async def test_the_database_refuses_invalid_rows(db_session, overrides, constraint):
    ctx = await mk_active_org(db_session, name=f"Counseling DB {uniq()}")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Db Check")
    db_session.add(AgentStudentCounseling(**({"agent_student_id": row.id, "counseling_completed": False, "updated_by_user_id": ctx["master"].id} | overrides)))
    with pytest.raises(IntegrityError, match=constraint):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_one_record_per_student(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling One {uniq()}")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Only Once")
    db_session.add(AgentStudentCounseling(agent_student_id=row.id, counseling_completed=False, updated_by_user_id=ctx["master"].id))
    await db_session.commit()
    db_session.add(AgentStudentCounseling(agent_student_id=row.id, counseling_completed=False, updated_by_user_id=ctx["master"].id))
    with pytest.raises(IntegrityError, match="uq_agent_student_counseling_student"):
        await db_session.commit()
    await db_session.rollback()


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


def _has_table(url: str) -> bool:
    return _sql(url, f"SELECT to_regclass('public.{TABLE}') IS NOT NULL")[0][0]


@pytest.fixture
def isolated_db():
    """A fresh database at 0054 with one agent and one agency student with no login."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {"agent": uuid.uuid4(), "student": uuid.uuid4()}
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Mig Agent', 'agent', 'overseas', true, true, 'en-GB', '{}')",
            {"id": ids["agent"], "email": f"agent-{name}@example.local"},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'Mig Student')", {"id": ids["student"], "agent": ids["agent"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, STUDENTS)
    command.upgrade(cfg, REV)
    assert _has_table(url)
    command.downgrade(cfg, BASE)
    assert not _has_table(url)
    assert _sql(url, STUDENTS) == before
    command.upgrade(cfg, REV)
    assert _has_table(url)
    assert _sql(url, STUDENTS) == before


def test_downgrade_refuses_while_counseling_records_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, REV)
    _sql(
        url,
        f"INSERT INTO {TABLE} (id, agent_student_id, counseling_completed, updated_by_user_id) VALUES (:id, :student, false, :agent)",
        {"id": uuid.uuid4(), "student": ids["student"], "agent": ids["agent"]},
    )
    with pytest.raises(RuntimeError, match="counseling records exist"):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(REV,)]
    assert _sql(url, f"SELECT count(*) FROM {TABLE}") == [(1,)]
