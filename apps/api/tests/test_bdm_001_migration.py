"""bdm-001 -- migration 0061_bdm_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the AGN-008 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
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
_spec = importlib.util.spec_from_file_location("_bdm_001_migration_0061", VERSIONS / "0061_bdm_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0060_agent_app_enrollment"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def test_migration_chains_after_0060_and_is_the_single_head():
    assert _migration.revision == "0061_bdm_profiles"
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_model_matches_the_migration():
    from app.models import BdmProfile

    table = BdmProfile.__table__
    assert {c.name for c in table.columns} == {
        "id", "user_id", "bdm_type", "employee_id", "designation", "department", "territory", "reporting_manager_user_id", "created_at", "updated_at",
    }
    assert not table.c.employee_id.nullable and not table.c.reporting_manager_user_id.nullable and table.c.designation.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_bdm_profiles_user", "ck_bdm_profiles_type", "uq_bdm_profiles_employee_id", "ix_bdm_profiles_reporting_manager"} <= names


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("bdm_profiles")})
    assert indexes["uq_bdm_profiles_employee_id"]["unique"]
    assert "ix_bdm_profiles_reporting_manager" in indexes


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
    """A fresh database at 0060 with one bdm_manager and one other user."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("manager", "bdm")}
        for key, role, division in (("manager", "bdm_manager", "global"), ("bdm", "counselor", "overseas")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, :division, true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": key, "role": role, "division": division},
            )
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_users_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, "0061_bdm_profiles")
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    command.upgrade(cfg, "0061_bdm_profiles")
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, "0061_bdm_profiles")
    insert = (
        "INSERT INTO bdm_profiles (id, user_id, bdm_type, employee_id, reporting_manager_user_id) "
        "VALUES (:id, :user, :type, :emp, :mgr)"
    )
    with pytest.raises(Exception, match="ck_bdm_profiles_type"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["bdm"], "type": "it", "emp": "E1", "mgr": ids["manager"]})
    _sql(url, insert, {"id": uuid.uuid4(), "user": ids["bdm"], "type": "college", "emp": "E1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_bdm_profiles_employee_id"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["manager"], "type": "agent", "emp": "e1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="profiles exist"):
        command.downgrade(cfg, BASE)
