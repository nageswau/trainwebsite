"""ccrm-010 -- migration 0169_overseas_student_notes (DEC-SCOPE-241). Round trip and the downgrade refusal run in a throwaway database
built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_010_migration_0169", VERSIONS / "0169_overseas_student_notes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0168_application_sub_status", "0169_overseas_student_notes"
TABLE = "overseas_student_notes"


def test_migration_chains_after_0168_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert script.get_heads() == [HEAD]


def test_model_matches_the_migration():
    from app.models import OverseasStudentNote

    assert OverseasStudentNote.__tablename__ == TABLE
    assert {c.name for c in OverseasStudentNote.__table__.columns} == {
        "id", "student_user_id", "application_id", "author_user_id", "body", "created_at", "updated_at",
    }  # fmt: skip
    assert {i.name for i in OverseasStudentNote.__table__.indexes} == {"ix_overseas_student_notes_student_created"}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert TABLE in await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.fixture
def isolated_db():
    """A fresh database at 0168_application_sub_status."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm010_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_creates_and_drops_the_table(isolated_db):
    assert TABLE not in _tables(isolated_db["url"])
    command.upgrade(isolated_db["cfg"], HEAD)
    assert TABLE in _tables(isolated_db["url"])
    indexes = {row[0] for row in _sql(isolated_db["url"], f"SELECT indexname FROM pg_indexes WHERE tablename = '{TABLE}'")}
    assert "ix_overseas_student_notes_student_created" in indexes
    command.downgrade(isolated_db["cfg"], BASE)
    assert TABLE not in _tables(isolated_db["url"])


def test_downgrade_refuses_while_notes_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    student, counselor = uuid.uuid4(), uuid.uuid4()
    for user_id, role in ((student, "overseas_student"), (counselor, "counselor")):
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
            "VALUES (:id, :email, 'x', 'Ccrm User', :role, 'overseas', '{}', true, true, 'en-GB')",
            {"id": user_id, "email": f"{user_id.hex[:8]}@example.com", "role": role},
        )
    _sql(url, f"INSERT INTO {TABLE} (id, student_user_id, author_user_id, body) VALUES (gen_random_uuid(), :s, :c, 'First call')", {"s": student, "c": counselor})
    with pytest.raises(Exception, match="student notes exist"):
        command.downgrade(cfg, BASE)
    assert TABLE in _tables(url)
