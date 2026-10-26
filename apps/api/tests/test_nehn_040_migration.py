"""nehn-040 -- migration 0194_agent_student_codes (DEC-SCOPE-279 N5). The backfill and round trip run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_nehn_040_migration_0194", VERSIONS / "0194_agent_student_codes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0193_student_archive_consent", "0194_agent_student_codes"
TAKEN = "ABCDEF01"


def test_migration_chains_after_0193_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


@pytest.mark.asyncio
async def test_column_and_unique_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, indexes = await conn.run_sync(lambda sync: ({c["name"]: c for c in inspect(sync).get_columns("agent_students")}, {i["name"]: i for i in inspect(sync).get_indexes("agent_students")}))
    assert columns["student_code"]["nullable"]
    assert indexes["ix_agent_students_student_code"]["unique"]


def _insert_user(url, role, code=None):
    return _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, student_code, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :email, 'x', 'Someone', :role, 'overseas', true, false, 'en', '{}', :code, now(), now()) RETURNING id",
        {"email": f"{uuid.uuid4().hex[:10]}@example.local", "role": role, "code": code},
    )[0][0]


def _insert_record(url, agent, student=None, name="Record"):
    return _sql(
        url,
        "INSERT INTO agent_students (id, agent_id, student_id, status, full_name, created_at, updated_at) VALUES (gen_random_uuid(), :agent, :student, 'active', :name, now(), now()) RETURNING id",
        {"agent": agent, "student": student, "name": name if student is None else None},
    )[0][0]


@pytest.fixture
def isolated_db():
    """A fresh database at 0193 with an agent, two no-login records, a linked record and a student account with no code."""
    cfg = _config()
    original = settings.database_url
    name = f"nehn040_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        agent = _insert_user(url, "agent")
        coded = _insert_user(url, "overseas_student", TAKEN)
        uncoded = _insert_user(url, "it_student")
        staff = _insert_user(url, "counselor")
        records = [_insert_record(url, agent, name="One"), _insert_record(url, agent, name="Two")]
        linked = _insert_record(url, agent, student=coded)
        yield {"cfg": cfg, "url": url, "records": records, "linked": linked, "uncoded": uncoded, "staff": staff, "coded": coded}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_codes_and_round_trips(isolated_db, monkeypatch):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # The first candidate is a code a user already holds: the backfill must skip it.
    candidates = iter([TAKEN, "11111111", "22222222", "33333333", "44444444"])
    monkeypatch.setattr(_migration.secrets, "token_hex", lambda n: next(candidates).lower())
    command.upgrade(cfg, HEAD)
    codes = dict(_sql(url, "SELECT id, student_code FROM agent_students"))
    assert codes[isolated_db["linked"]] is None
    record_codes = {codes[r] for r in isolated_db["records"]}
    users = dict(_sql(url, "SELECT id, student_code FROM users"))
    assert users[isolated_db["coded"]] == TAKEN and users[isolated_db["staff"]] is None
    assert record_codes | {users[isolated_db["uncoded"]]} == {"11111111", "22222222", "33333333"}
    with pytest.raises(Exception, match="ix_agent_students_student_code"):
        _sql(url, "UPDATE agent_students SET student_code = '11111111' WHERE student_id IS NULL")
    command.downgrade(cfg, BASE)
    assert "student_code" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'agent_students'")}
    assert _sql(url, "SELECT student_code FROM users WHERE id = :id", {"id": isolated_db["uncoded"]})[0][0] is not None
    monkeypatch.undo()
    command.upgrade(cfg, HEAD)
    assert all(code for (code,) in _sql(url, "SELECT student_code FROM agent_students WHERE student_id IS NULL"))
