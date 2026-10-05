"""AGN-004 -- migration 0049_agent_students_crm (spec §4, AC12; re-chained after AGN-002's 0047_agent_org_staff, then after ENH-030's
0048_school_attendance_records, on merging main).

The round trip and the downgrade refusals run in a throwaway database built from scratch (the ENH-001 pattern,
test_enh_001_academic_year.py): a downgrade is never run against the shared test database.
Plain (non-async) tests: alembic/env.py calls asyncio.run() itself.
"""

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
_spec = importlib.util.spec_from_file_location("_agn_004_migration_0049", VERSIONS / "0049_agent_students_crm.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0048_school_attendance_records"  # ENH-030, on main first; AGN-002's 0047_agent_org_staff (the staff pieces) precedes it
LINK_COLUMNS = "SELECT id, agent_id, student_id, status, created_at FROM agent_students ORDER BY id"


def test_migration_chains_after_enh030_and_is_the_single_head():
    assert _migration.revision == "0049_agent_students_crm"
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    # ENH-014 chained 0050_notification_channels after this migration, so the intent is kept without pinning the head -- the
    # relaxation ENH-013/ENH-025/ENH-027 received on earlier merges: one head, and 0049 is a parent in the chain.
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1
    assert "0049_agent_students_crm" in parents.values()


def test_model_declares_every_new_column_nullable():
    from app.models import AgentStudent

    columns = AgentStudent.__table__.columns
    for name, _ in (*_migration.STUDENT_COLUMNS, *_migration.FK_COLUMNS):
        assert name in columns and columns[name].nullable, name
    assert columns["student_id"].nullable


@pytest.mark.asyncio
async def test_new_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("agent_students")})
    for name, _ in (*_migration.STUDENT_COLUMNS, *_migration.FK_COLUMNS):
        assert name in cols and cols[name]["nullable"], name


def _run(coro_factory):
    return asyncio.run(coro_factory())


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return _run(_inner)


@pytest.fixture
def isolated_db():
    """A fresh database migrated to AGN-002's 0047, with one agency (org + Master) and one link to a student with an account."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("master", "student", "org", "member", "link")}
        for key, role in (("master", "agent"), ("student", "overseas_student")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, 'overseas', true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": f"{key} user", "role": role},
            )
        _sql(url, "INSERT INTO agent_orgs (id, name, prefix, status, master_seq) VALUES (:id, 'Mig Agency', :prefix, 'active', 1)", {"id": ids["org"], "prefix": f"M{uuid.uuid4().hex[:5].upper()}"})
        _sql(
            url,
            "INSERT INTO agent_org_members (id, org_id, user_id, role, seq, code, status) VALUES (:id, :org, :user, 'master', 1, :code, 'active')",
            {"id": ids["member"], "org": ids["org"], "user": ids["master"], "code": f"MIG-{uuid.uuid4().hex[:6]}"},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status) VALUES (:id, :agent, :student, 'active')", {"id": ids["link"], "agent": ids["master"], "student": ids["student"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, LINK_COLUMNS)
    command.upgrade(cfg, "0049_agent_students_crm")
    assert _sql(url, LINK_COLUMNS) == before
    new_cols = _sql(url, "SELECT full_name, assigned_member_id, archived_at FROM agent_students")
    assert new_cols == [(None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, LINK_COLUMNS) == before
    command.upgrade(cfg, "0049_agent_students_crm")
    assert _sql(url, LINK_COLUMNS) == before


@pytest.mark.parametrize(
    ("setup_sql", "message"),
    [
        ("INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:new, :agent, NULL, 'active', 'No Login')", "students with no login exist"),
        ("UPDATE agent_students SET assigned_member_id = :member", "assigned students exist"),
        # Final review M1: archive state (archived_at/by) would be dropped and the pre-AGN-004 roster would show the link again.
        ("UPDATE agent_students SET status = 'archived'", "archived students exist"),
    ],
)
def test_downgrade_refuses_to_lose_agn004_data(isolated_db, setup_sql, message):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, "0049_agent_students_crm")
    _sql(url, setup_sql, {"new": uuid.uuid4(), "agent": ids["master"], "member": ids["member"], "org": ids["org"], "student": ids["student"], "code": f"S-{uuid.uuid4().hex[:6]}"})
    with pytest.raises(RuntimeError, match=message):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [("0049_agent_students_crm",)]
