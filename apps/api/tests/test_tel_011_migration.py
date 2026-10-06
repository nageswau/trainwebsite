"""tel-011 -- migration 0089_lead_follow_ups (spec §2). The round trip runs in a throwaway database (the tel-004/005/006 pattern); a
downgrade never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first
downgrades to 0087_lead_import_batches to reach the real pre-tel-011 shape."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime
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
_spec = importlib.util.spec_from_file_location("_tel_011_migration_0089", VERSIONS / "0089_lead_follow_ups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0087_lead_import_batches", "0089_lead_follow_ups"
COLUMNS = {"id", "lead_id", "due_at", "reason", "notes", "next_action", "status", "created_by_user_id", "completed_at",
           "completed_by_user_id", "cancelled_at", "cancel_reason", "created_at", "updated_at"}
NULLABLE = {"notes", "next_action", "completed_at", "completed_by_user_id", "cancelled_at", "cancel_reason"}


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


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


def test_migration_chains_after_0087_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_FOLLOW_UP_CHECKS, LeadFollowUp

    table = LeadFollowUp.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert {c.name for c in table.columns if c.nullable} == NULLABLE
    assert {fk.parent.name: fk.column.table.name for fk in table.foreign_keys} == {
        "lead_id": "enquiries", "created_by_user_id": "users", "completed_by_user_id": "users"}
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == LEAD_FOLLOW_UP_CHECKS == _migration.CHECKS
    assert {"ix_lead_follow_ups_lead", "ix_lead_follow_ups_open_due"} <= {i.name for i in table.indexes}


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel011_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


AT = datetime(2026, 10, 6, 10, tzinfo=UTC)
EXISTS = "SELECT to_regclass('lead_follow_ups')"
SEED = ("INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:user, :email, 'Caller', 'telecaller', 'it', 'x', true, true, 'en-GB', '{}');"
        "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, owner_id, crm_sync_status, metadata_json, priority) "
        "VALUES (:lead, 'it', 'Lead', 'l@example.com', 'Python', 'Hi', 'website', 'new', NULL, 'pending', '{}', 'warm')")
ROW = ("INSERT INTO lead_follow_ups (id, lead_id, due_at, reason, status, created_by_user_id, completed_at, completed_by_user_id, "
       "cancelled_at, cancel_reason) VALUES (:id, :lead, now() + interval '1 day', :reason, :status, :user, :done_at, :done_by, :cancel_at, :cancel_reason)")


def test_downgrade_to_0087_has_no_table(base_db):
    assert _sql(base_db["url"], EXISTS) == [(None,)]


def test_upgrade_adds_the_table_with_its_checks(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    user, lead = uuid.uuid4(), uuid.uuid4()
    for statement in SEED.split(";"):
        _sql(url, statement, {"user": user, "email": f"c-{user.hex[:8]}@example.com", "lead": lead})
    row = {"lead": lead, "user": user, "reason": "fee_details", "status": "open", "done_at": None, "done_by": None, "cancel_at": None,
           "cancel_reason": None}
    _sql(url, ROW, {"id": uuid.uuid4(), **row})
    assert _sql(url, "SELECT status, created_at IS NOT NULL FROM lead_follow_ups") == [("open", True)]
    with pytest.raises(Exception, match="ck_lead_follow_ups_reason"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "reason": "other"})
    with pytest.raises(Exception, match="ck_lead_follow_ups_status"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "snoozed"})
    with pytest.raises(Exception, match="ck_lead_follow_ups_state"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "done"})  # done without completed_at / completed_by
    with pytest.raises(Exception, match="ck_lead_follow_ups_state"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "cancelled", "cancel_reason": "x"})  # no cancelled_at
    _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "done", "done_at": AT, "done_by": user})
    _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "cancelled", "cancel_at": AT, "cancel_reason": "x"})


def test_downgrade_drops_the_table(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, EXISTS) == [(None,)]
