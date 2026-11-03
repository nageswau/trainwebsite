"""itc-033 -- migration 0239_call_preference (DEC-SCOPE-357): the call opt-out on notification_preferences. Round trip in a throwaway
database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import NotificationPreference
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_033_migration_0239", VERSIONS / "0239_call_preference.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0239_call_preference"
BASE = _migration.down_revision
COLUMNS = (
    "SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = 'notification_preferences' "
    "AND column_name IN ('calls_opt_out', 'calls_opted_out_at') ORDER BY 1"
)


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    columns = NotificationPreference.__table__.columns
    assert not columns["calls_opt_out"].nullable and columns["calls_opted_out_at"].nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc033_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001 builds from the current models, so step back to the base to start without the columns
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_existing_rows_default_to_calls_allowed_and_the_round_trip_is_clean(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Student', 'it_student', 'it', true, true, 'en-GB', '{}')",
        {"id": user, "email": f"s-{user.hex[:8]}@example.local"},
        autocommit=True,
    )
    _sql(url, "INSERT INTO notification_preferences (user_id, whatsapp_opt_in, sms_opt_in) VALUES (:id, true, false)", {"id": user}, autocommit=True)
    assert _sql(url, COLUMNS) == []

    command.upgrade(cfg, HEAD)
    assert [(r[0], r[1]) for r in _sql(url, COLUMNS)] == [("calls_opt_out", "NO"), ("calls_opted_out_at", "YES")]
    # the existing row keeps its WhatsApp/SMS choice and reads as calls allowed
    assert _sql(url, "SELECT whatsapp_opt_in, calls_opt_out, calls_opted_out_at FROM notification_preferences") == [(True, False, None)]

    command.downgrade(cfg, BASE)
    assert _sql(url, COLUMNS) == []
    assert _sql(url, "SELECT whatsapp_opt_in FROM notification_preferences") == [(True,)]
