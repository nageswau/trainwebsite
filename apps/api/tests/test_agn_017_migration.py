"""AGN-017 AC10 -- migration 0065_agent_notifications (spec §5): one nullable column and four partial indexes, additive only. The
round trip runs in a throwaway database built from scratch (the AGN-013 pattern); a downgrade never runs against the shared test
database. Plain tests: alembic/env.py calls asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_017_migration_0065", VERSIONS / "0065_agent_notifications.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0064_application_deposits"
HEAD = "0065_agent_notifications"
INDEXES = {
    "ux_notifications_dedupe_key": ("notifications", "dedupe_key IS NOT NULL"),
    "ix_overseas_applications_agent_application_deadline": ("overseas_applications", "agent_student_id IS NOT NULL"),
    "ix_overseas_applications_agent_offer_deadline": ("overseas_applications", "agent_student_id IS NOT NULL"),
    "ix_agent_tasks_open_due": ("agent_tasks", "'open'"),
}
NOTIFICATIONS = "SELECT id, user_id, title, body, read, action_url FROM notifications ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0064_with_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # one head; later migrations chain after 0065


def test_model_declares_the_nullable_dedupe_key_and_the_partial_indexes():
    from app.models import AgentTask, Notification, OverseasApplication

    column = Notification.__table__.columns["dedupe_key"]
    assert column.nullable and column.type.length == 200
    declared = {i.name: i for t in (Notification, OverseasApplication, AgentTask) for i in t.__table__.indexes}
    assert set(INDEXES) <= set(declared)
    assert declared["ux_notifications_dedupe_key"].unique


async def _indexdefs(db_session) -> dict[str, str]:
    rows = await db_session.execute(sa.text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname = ANY(:names)"), {"names": list(INDEXES)})
    return dict(rows.all())


@pytest.mark.asyncio
async def test_column_and_partial_indexes_exist_in_the_shared_database(db_session):
    nullable = await db_session.scalar(sa.text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'dedupe_key'"))
    assert nullable == "YES"
    defs = await _indexdefs(db_session)
    assert set(defs) == set(INDEXES)
    for name, (table, predicate) in INDEXES.items():
        assert f"ON public.{table}" in defs[name] and predicate in defs[name], defs[name]
    assert "UNIQUE" in defs["ux_notifications_dedupe_key"]


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
    """A fresh database at 0064 with one notification."""
    cfg = _config()
    original = settings.database_url
    name = f"agn017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Mig user', 'agent', 'overseas', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"mig-{name}@example.local"},
        )
        _sql(url, "INSERT INTO notifications (id, user_id, title, body, read) VALUES (:id, :user, 'Hello', 'Body', false)", {"id": uuid.uuid4(), "user": user_id})
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_notifications_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, NOTIFICATIONS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, NOTIFICATIONS) == before
    assert _sql(url, "SELECT dedupe_key FROM notifications") == [(None,)]
    command.downgrade(cfg, BASE)
    assert _sql(url, NOTIFICATIONS) == before
    assert _sql(url, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'dedupe_key'") == [(0,)]
    assert _sql(url, "SELECT count(*) FROM pg_indexes WHERE indexname = ANY(:names)", {"names": list(INDEXES)}) == [(0,)]
    command.upgrade(cfg, HEAD)
    assert _sql(url, NOTIFICATIONS) == before
    assert _sql(url, "SELECT count(*) FROM pg_indexes WHERE indexname = ANY(:names)", {"names": list(INDEXES)}) == [(len(INDEXES),)]
