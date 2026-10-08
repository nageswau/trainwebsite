"""rec-001 -- migration 0100_recruiter_profiles (spec §3). Round trip, backfill and the downgrade refusal run in a throwaway database
built from scratch (the tel-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_001_migration_0100", VERSIONS / "0100_recruiter_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0099_tel_settings", "0100_recruiter_profiles"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"
PROFILES = "SELECT user_id, employee_id, reporting_manager_user_id FROM recruiter_profiles ORDER BY user_id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0099_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_matches_the_migration():
    from app.models import RecruiterProfile

    table = RecruiterProfile.__table__
    assert {c.name for c in table.columns} == {"id", "user_id", "employee_id", "reporting_manager_user_id", "created_at", "updated_at"}
    assert not table.c.user_id.nullable
    assert table.c.employee_id.nullable and table.c.reporting_manager_user_id.nullable  # backfilled / legacy-form rows (spec §3)
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_recruiter_profiles_user", "uq_recruiter_profiles_employee_id", "ix_recruiter_profiles_reporting_manager"} <= names


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("recruiter_profiles")})
    assert indexes["uq_recruiter_profiles_employee_id"]["unique"]
    assert "ix_recruiter_profiles_reporting_manager" in indexes


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


def _add_user(url: str, user_id, role: str, division: str, tag: str) -> None:
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', :name, :role, :division, true, true, 'en-GB', '{}')",
        {"id": user_id, "email": f"{tag}-{user_id.hex[:8]}@example.local", "name": tag, "role": role, "division": division},
    )


@pytest.fixture
def isolated_db():
    """A fresh database at 0099 with two existing recruiters, a placement manager and an hr_team user."""
    cfg = _config()
    original = settings.database_url
    name = f"rec001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("rec1", "rec2", "manager", "hr")}
        for key, role, division in (("rec1", "placement_team", "it"), ("rec2", "placement_team", "it"), ("manager", "placement_manager", "global"),
                                    ("hr", "hr_team", "it")):
            _add_user(url, ids[key], role, division, key)
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_an_empty_profile_for_every_existing_recruiter_only(isolated_db):
    """AC5: existing placement_team users keep working with a profile that has no Employee ID and no manager."""
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    assert sorted(_sql(url, PROFILES)) == sorted([(ids["rec1"], None, None), (ids["rec2"], None, None)])


def test_backfill_is_idempotent_and_keeps_existing_profiles(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    _sql(url, "UPDATE recruiter_profiles SET employee_id = 'R-1', reporting_manager_user_id = :m WHERE user_id = :u", {"m": ids["manager"], "u": ids["rec1"]})
    _migration_upgrade_again(url)
    rows = {row[0]: row for row in _sql(url, PROFILES)}
    assert len(rows) == 2
    assert rows[ids["rec1"]] == (ids["rec1"], "R-1", ids["manager"])


def _migration_upgrade_again(url: str) -> None:
    """Re-run the backfill statement exactly as upgrade() does (the guard path when 0001 already built the table)."""
    _sql(url, _migration.BACKFILL)


def test_round_trip_keeps_users_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before
    assert len(_sql(url, PROFILES)) == 2


def test_constraints_hold_and_downgrade_refuses_while_a_profile_carries_data(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    set_emp = "UPDATE recruiter_profiles SET employee_id = :emp WHERE user_id = :u"
    _sql(url, set_emp, {"emp": "R1", "u": ids["rec1"]})
    with pytest.raises(Exception, match="uq_recruiter_profiles_employee_id"):
        _sql(url, set_emp, {"emp": "r1", "u": ids["rec2"]})
    with pytest.raises(Exception, match="uq_recruiter_profiles_user"):
        _sql(url, "INSERT INTO recruiter_profiles (id, user_id) VALUES (:id, :u)", {"id": uuid.uuid4(), "u": ids["rec1"]})
    with pytest.raises(Exception, match="carry an Employee ID or a manager"):
        command.downgrade(cfg, BASE)
