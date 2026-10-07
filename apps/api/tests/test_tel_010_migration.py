"""tel-010 -- migration 0092_lead_calls (spec §3). The round trip runs in a throwaway database (the tel-004/005/006/011 pattern); a downgrade
never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0091_lead_appointments (tel-016) to reach the real pre-tel-010 shape."""

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
_spec = importlib.util.spec_from_file_location("_tel_010_migration_0092", VERSIONS / "0092_lead_calls.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0091_lead_appointments", "0092_lead_calls"
COLUMNS = {"id", "lead_id", "caller_user_id", "occurred_at", "duration_seconds", "call_type", "outcome", "remarks", "created_at", "updated_at"}


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


def test_migration_chains_after_0091_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_CALL_CHECKS, LeadCall

    table = LeadCall.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert {c.name for c in table.columns if c.nullable} == {"remarks"}
    assert {fk.parent.name: fk.column.table.name for fk in table.foreign_keys} == {"lead_id": "enquiries", "caller_user_id": "users"}
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == LEAD_CALL_CHECKS == _migration.CHECKS
    assert {"ix_lead_calls_caller_occurred", "ix_lead_calls_lead_occurred"} <= {i.name for i in table.indexes}


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel010_migration_{uuid.uuid4().hex[:8]}"
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


EXISTS = "SELECT to_regclass('lead_calls')"
SEED = ("INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:user, :email, 'Caller', 'telecaller', 'it', 'x', true, true, 'en-GB', '{}');"
        "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, owner_id, crm_sync_status, metadata_json, priority) "
        "VALUES (:lead, 'it', 'Lead', 'l@example.com', 'Python', 'Hi', 'website', 'new', NULL, 'pending', '{}', 'warm')")
ROW = ("INSERT INTO lead_calls (id, lead_id, caller_user_id, occurred_at, duration_seconds, call_type, outcome) "
       "VALUES (:id, :lead, :user, now(), :duration, :type, :outcome)")


def test_downgrade_to_0091_has_no_table(base_db):
    assert _sql(base_db["url"], EXISTS) == [(None,)]


def test_upgrade_adds_the_table_with_its_checks(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    user, lead = uuid.uuid4(), uuid.uuid4()
    for statement in SEED.split(";"):
        _sql(url, statement, {"user": user, "email": f"c-{user.hex[:8]}@example.com", "lead": lead})
    row = {"lead": lead, "user": user, "duration": 0, "type": "outgoing", "outcome": "no_answer"}
    _sql(url, ROW, {"id": uuid.uuid4(), **row})
    assert _sql(url, "SELECT outcome, remarks, created_at IS NOT NULL FROM lead_calls") == [("no_answer", None, True)]
    with pytest.raises(Exception, match="ck_lead_calls_outcome"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "outcome": "converted"})
    with pytest.raises(Exception, match="ck_lead_calls_call_type"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "type": "callback"})
    with pytest.raises(Exception, match="ck_lead_calls_duration"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "duration": -1})
    with pytest.raises(Exception, match="ck_lead_calls_duration"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "duration": 14401})


def test_downgrade_drops_the_table(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, EXISTS) == [(None,)]
