"""itc-010 -- migration 0227_lead_counseling_records (DEC-SCOPE-343). Round trip, the objection seed and the downgrade refusal run in a
throwaway database built from scratch (the itc-003 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import LEAD_COUNSELING_CHECKS, LeadCounselingObjection, LeadCounselingRecord, LeadCounselingRecordObjection
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_010_migration_0227", VERSIONS / "0227_lead_counseling_records.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0227_lead_counseling_records"
BASE = _migration.down_revision
TABLES = {"lead_counseling_objections", "lead_counseling_records", "lead_counseling_record_objections"}


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert LeadCounselingRecord.__tablename__ == "lead_counseling_records"
    assert {c.name for c in LeadCounselingRecord.__table__.columns} == {
        "id",
        "lead_id",
        "author_user_id",
        "updated_by_user_id",
        "recommended_product_id",
        "objection_notes",
        "fee_quoted",
        "expected_joining_date",
        "decision_maker",
        "outcome",
        "next_follow_up",
        "notes",
        "created_at",
        "updated_at",
    }
    assert {c.name for c in LeadCounselingObjection.__table__.columns} == {"id", "name", "active", "sort_order", "created_at", "updated_at"}
    assert {c.name for c in LeadCounselingRecordObjection.__table__.columns} == {"record_id", "objection_id"}
    assert _migration.CHECKS == LEAD_COUNSELING_CHECKS  # the migration repeats the model's CHECK strings


@pytest.mark.asyncio
async def test_tables_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert TABLES <= await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc010_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_round_trip_creates_seeds_and_drops(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    names = [row[0] for row in _sql(url, "SELECT name FROM lead_counseling_objections ORDER BY sort_order")]
    assert names == list(_migration.SEED)
    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)


def test_downgrade_refuses_while_records_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user, lead = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, :email, 'x', 'Itc User', 'counselor', 'it', '{}', true, true, 'en-GB')",
        {"id": user, "email": f"{user.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO enquiries (id, name, email, subject, message, division, source, status, priority, crm_sync_status, metadata_json) "
        "VALUES (:id, 'L', 'l@example.com', 'S', '', 'it', 'website', 'new', 'warm', 'pending', '{}')",
        {"id": lead},
    )
    _sql(url, "INSERT INTO lead_counseling_records (id, lead_id, author_user_id, updated_by_user_id, outcome) VALUES (gen_random_uuid(), :l, :u, :u, 'interested')", {"l": lead, "u": user})
    with pytest.raises(Exception, match="counseling records exist"):
        command.downgrade(cfg, BASE)
    assert TABLES <= _tables(url)
