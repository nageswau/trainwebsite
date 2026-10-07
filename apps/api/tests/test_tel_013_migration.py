"""tel-013 -- migration 0095_lead_messages (spec §2). The round trip runs in a throwaway database (the tel-010 pattern); a downgrade never runs
against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0094_bdm_daily_reports (bdm-015) to reach the real pre-tel-013 shape."""

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
_spec = importlib.util.spec_from_file_location("_tel_013_migration_0095", VERSIONS / "0095_lead_messages.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0094_bdm_daily_reports", "0095_lead_messages"
COLUMNS = {"id", "lead_id", "sender_user_id", "channel", "template_id", "template_name", "subject", "body", "delivery_status", "sent_at",
           "created_at", "updated_at"}


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


def test_migration_chains_after_0094_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    # bdm-016's 0096_bdm_targets chains after this one, so it is in the chain under a single head (the bdm-015 test's form).
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEAD_MESSAGE_CHECKS, LeadMessage

    table = LeadMessage.__table__
    assert {c.name for c in table.columns} == COLUMNS | {"attempt_count"}  # tel-014 0097 adds attempt_count and ck_lead_messages_email
    assert {c.name for c in table.columns if c.nullable} == {"template_id", "template_name", "subject", "delivery_status"}
    assert {fk.parent.name: fk.column.table.name for fk in table.foreign_keys} == {
        "lead_id": "enquiries", "sender_user_id": "users", "template_id": "tel_message_templates"}
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert {name: checks[name] for name in LEAD_MESSAGE_CHECKS} == LEAD_MESSAGE_CHECKS == _migration.CHECKS
    assert {"ix_lead_messages_lead_sent", "ix_lead_messages_sender_sent"} <= {i.name for i in table.indexes}


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel013_migration_{uuid.uuid4().hex[:8]}"
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


EXISTS = "SELECT to_regclass('lead_messages')"
SEED = ("INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:user, :email, 'Sender', 'telecaller', 'it', 'x', true, true, 'en-GB', '{}');"
        "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, owner_id, crm_sync_status, metadata_json, priority) "
        "VALUES (:lead, 'it', 'Lead', 'l@example.com', 'Python', 'Hi', 'website', 'new', NULL, 'pending', '{}', 'warm')")
ROW = ("INSERT INTO lead_messages (id, lead_id, sender_user_id, channel, subject, body, delivery_status, sent_at) "
       "VALUES (:id, :lead, :user, :channel, :subject, :body, :status, now())")


def test_downgrade_to_0094_has_no_table(base_db):
    assert _sql(base_db["url"], EXISTS) == [(None,)]


def test_upgrade_adds_the_table_with_its_checks(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    user, lead = uuid.uuid4(), uuid.uuid4()
    for statement in SEED.split(";"):
        _sql(url, statement, {"user": user, "email": f"s-{user.hex[:8]}@example.com", "lead": lead})
    row = {"lead": lead, "user": user, "channel": "whatsapp", "subject": None, "body": "Hello", "status": None}
    _sql(url, ROW, {"id": uuid.uuid4(), **row})
    _sql(url, ROW, {"id": uuid.uuid4(), **row, "channel": "email", "subject": "Brochure", "status": "sent"})
    assert _sql(url, "SELECT channel, template_id, created_at IS NOT NULL FROM lead_messages ORDER BY channel") == [
        ("email", None, True), ("whatsapp", None, True)]
    with pytest.raises(Exception, match="ck_lead_messages_channel"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "channel": "sms"})
    with pytest.raises(Exception, match="ck_lead_messages_body"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "body": ""})
    with pytest.raises(Exception, match="ck_lead_messages_whatsapp"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "subject": "No subjects on WhatsApp"})
    with pytest.raises(Exception, match="ck_lead_messages_whatsapp"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "sent"})


def test_downgrade_drops_the_table(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, EXISTS) == [(None,)]
