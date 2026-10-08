"""upc-001 -- migration 0100_partnership_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the tel-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_upc_001_migration_0100", VERSIONS / "0100_partnership_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0099_tel_settings", "0100_partnership_profiles"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0099_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import PartnershipProfile

    table = PartnershipProfile.__table__
    assert {c.name for c in table.columns} == {"user_id", "employee_id", "reporting_head_user_id", "created_at", "updated_at"}
    assert [c.name for c in table.primary_key.columns] == ["user_id"]
    assert not table.c.employee_id.nullable and not table.c.reporting_head_user_id.nullable
    assert {"uq_partnership_profiles_employee_id", "ix_partnership_profiles_reporting_head"} <= {i.name for i in table.indexes}


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("partnership_profiles")})
    assert indexes["uq_partnership_profiles_employee_id"]["unique"]
    assert "ix_partnership_profiles_reporting_head" in indexes


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
    """A fresh database at 0099 with one partnership_head and two other users."""
    cfg = _config()
    original = settings.database_url
    name = f"upc001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("head", "pm", "pm2")}
        for key, role, division in (("head", "partnership_head", "global"), ("pm", "partnership_manager", "overseas"), ("pm2", "partnership_manager", "overseas")):
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
    assert "partnership_profiles" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables")}
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    insert = "INSERT INTO partnership_profiles (user_id, employee_id, reporting_head_user_id) VALUES (:user, :emp, :head)"
    _sql(url, insert, {"user": ids["pm"], "emp": "P1", "head": ids["head"]})
    with pytest.raises(Exception, match="uq_partnership_profiles_employee_id"):
        _sql(url, insert, {"user": ids["pm2"], "emp": "p1", "head": ids["head"]})
    with pytest.raises(Exception, match="partnership_profiles_pkey"):
        _sql(url, insert, {"user": ids["pm"], "emp": "P2", "head": ids["head"]})
    with pytest.raises(Exception, match="foreign key"):
        _sql(url, insert, {"user": ids["pm2"], "emp": "P3", "head": uuid.uuid4()})
    with pytest.raises(Exception, match="profiles exist"):
        command.downgrade(cfg, BASE)
