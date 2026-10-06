"""tel-001 -- migration 0075_telecaller_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the bdm-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_tel_001_migration_0075", VERSIONS / "0075_telecaller_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0074_enquiry_bdm_attribution", "0075_telecaller_profiles"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0074_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # tel-002's 0076 now follows this revision


def test_model_matches_the_migration():
    from app.models import TelecallerProfile

    table = TelecallerProfile.__table__
    assert {c.name for c in table.columns} == {"id", "user_id", "team", "employee_id", "reporting_manager_user_id", "created_at", "updated_at"}
    assert not table.c.employee_id.nullable and not table.c.reporting_manager_user_id.nullable and not table.c.team.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_telecaller_profiles_user", "ck_telecaller_profiles_team", "uq_telecaller_profiles_employee_id", "ix_telecaller_profiles_reporting_manager"} <= names


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("telecaller_profiles")})
    assert indexes["uq_telecaller_profiles_employee_id"]["unique"]
    assert "ix_telecaller_profiles_reporting_manager" in indexes


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
    """A fresh database at 0074 with one telecaller_manager and one other user."""
    cfg = _config()
    original = settings.database_url
    name = f"tel001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("manager", "caller")}
        for key, role, division in (("manager", "telecaller_manager", "global"), ("caller", "counselor", "overseas")):
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
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    insert = (
        "INSERT INTO telecaller_profiles (id, user_id, team, employee_id, reporting_manager_user_id) "
        "VALUES (:id, :user, :team, :emp, :mgr)"
    )
    with pytest.raises(Exception, match="ck_telecaller_profiles_team"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "global", "emp": "T1", "mgr": ids["manager"]})
    _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "it", "emp": "T1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_telecaller_profiles_employee_id"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["manager"], "team": "overseas", "emp": "t1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_telecaller_profiles_user"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "it", "emp": "T2", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="profiles exist"):
        command.downgrade(cfg, BASE)
