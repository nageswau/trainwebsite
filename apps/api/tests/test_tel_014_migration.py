"""tel-014 -- migration 0097_lead_message_email (spec §2). The round trip runs in a throwaway database (the tel-013 pattern); a downgrade never
runs against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0096_bdm_targets (bdm-016) to reach the real pre-tel-014 shape."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_013_migration import ROW, SEED, VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_tel_014_migration_0097", VERSIONS / "0097_lead_message_email.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0096_bdm_targets", "0097_lead_message_email"
COLUMN = "SELECT column_name FROM information_schema.columns WHERE table_name = 'lead_messages' AND column_name = 'attempt_count'"


def test_migration_chains_after_0096_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_model_matches_the_migration():
    from app.models import LEAD_MESSAGE_EMAIL_CHECK, LeadMessage

    table = LeadMessage.__table__
    column = table.columns["attempt_count"]
    assert not column.nullable and str(column.server_default.arg) == "0"
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert {_migration.CHECK_NAME: checks[_migration.CHECK_NAME]} == LEAD_MESSAGE_EMAIL_CHECK == {_migration.CHECK_NAME: _migration.CHECK_SQL}


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel014_migration_{uuid.uuid4().hex[:8]}"
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


def _seed(url) -> dict:
    user, lead = uuid.uuid4(), uuid.uuid4()
    for statement in SEED.split(";"):
        _sql(url, statement, {"user": user, "email": f"s-{user.hex[:8]}@example.com", "lead": lead})
    return {"lead": lead, "user": user, "channel": "email", "subject": "Brochure", "body": "Hello", "status": "queued"}


def test_downgrade_to_0096_has_no_column(base_db):
    assert _sql(base_db["url"], COLUMN) == []


def test_upgrade_keeps_rows_and_adds_the_column_and_check(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    row = _seed(url)
    _sql(url, ROW, {"id": uuid.uuid4(), **row, "channel": "whatsapp", "subject": None, "status": None})  # an existing tel-013 row
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT channel, attempt_count FROM lead_messages") == [("whatsapp", 0)]
    for status in ("queued", "sending", "retrying", "sent", "failed"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": status})
    with pytest.raises(Exception, match="ck_lead_messages_email"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "delivered"})
    with pytest.raises(Exception, match="ck_lead_messages_email"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": None})
    with pytest.raises(Exception, match="ck_lead_messages_email"):
        _sql(url, ROW, {"id": uuid.uuid4(), **row, "subject": None})


def test_downgrade_drops_the_column_and_check(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, COLUMN) == []
    row = _seed(url)
    _sql(url, ROW, {"id": uuid.uuid4(), **row, "status": "delivered"})  # the 0096 shape has no email check
