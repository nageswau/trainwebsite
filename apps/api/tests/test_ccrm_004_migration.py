"""ccrm-004 -- migration 0181_lead_meetings (DEC-SCOPE-259). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the csc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_004_migration_0181", VERSIONS / "0181_lead_meetings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0180_application_checklists", "0181_lead_meetings"
TABLE = "lead_meetings"


def test_migration_chains_after_0180_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import APPOINTMENT_MODES, LEAD_MEETING_NOTES_MAX, Appointment, LeadMeeting

    assert LeadMeeting.__tablename__ == TABLE and LEAD_MEETING_NOTES_MAX == _migration.MAX and APPOINTMENT_MODES == _migration.MODES
    assert {c.name for c in LeadMeeting.__table__.columns} == {"id", "lead_id", "author_user_id", "occurred_at", "mode", "notes", "created_at"}
    assert {i.name for i in LeadMeeting.__table__.indexes} == {"ix_lead_meetings_lead_occurred"}
    assert Appointment.__table__.c.outcome_notes.nullable


@pytest.mark.asyncio
async def test_table_and_column_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, columns = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {c["name"] for c in inspect(sync).get_columns("appointments")}))
    assert TABLE in tables and "outcome_notes" in columns


@pytest.fixture
def isolated_db():
    """A fresh database at 0180_application_checklists."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def _has_outcome_notes(url: str) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'appointments' AND column_name = 'outcome_notes'"))


def test_round_trip_creates_and_drops_the_table_and_column(isolated_db):
    url = isolated_db["url"]
    assert TABLE not in _tables(url) and not _has_outcome_notes(url)
    command.upgrade(isolated_db["cfg"], HEAD)
    assert TABLE in _tables(url) and _has_outcome_notes(url)
    command.downgrade(isolated_db["cfg"], BASE)
    assert TABLE not in _tables(url) and not _has_outcome_notes(url)


def test_checks_hold_and_downgrade_refuses_while_meetings_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    author, lead = uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
              "VALUES (:id, :email, 'x', 'Ccrm User', 'counselor', 'overseas', '{}', true, true, 'en-GB')",
         {"id": author, "email": f"{author.hex[:8]}@example.com"})
    _sql(url, "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json) "
              "VALUES (:id, 'overseas', 'Lead', 'l@example.com', 'S', '', 'website', 'new', 'pending', '{}')", {"id": lead})
    insert = f"INSERT INTO {TABLE} (id, lead_id, author_user_id, occurred_at, mode, notes) VALUES (gen_random_uuid(), :l, :a, now(), :m, :n)"
    with pytest.raises(Exception, match="ck_lead_meetings_mode"):
        _sql(url, insert, {"l": lead, "a": author, "m": "Fax", "n": "x"})
    with pytest.raises(Exception, match="ck_lead_meetings_notes"):
        _sql(url, insert, {"l": lead, "a": author, "m": "Online", "n": ""})
    _sql(url, insert, {"l": lead, "a": author, "m": "In person", "n": "Kept"})
    with pytest.raises(Exception, match="lead meetings exist"):
        command.downgrade(cfg, BASE)
    assert TABLE in _tables(url)
