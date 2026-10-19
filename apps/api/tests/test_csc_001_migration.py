"""csc-001 -- migration 0165_overseas_student_counselors (DEC-SCOPE-226). Round trip and the downgrade refusal run in a throwaway
database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py
calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_csc_001_migration_0165", VERSIONS / "0165_overseas_student_counselors.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0164_agent_org_kyc", "0165_overseas_student_counselors"
TABLE = "overseas_student_counselors"


def test_migration_chains_after_0164_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import OverseasStudentCounselor

    assert OverseasStudentCounselor.__tablename__ == TABLE
    assert {c.name for c in OverseasStudentCounselor.__table__.columns} == {
        "id", "student_user_id", "counselor_user_id", "assigned_by_user_id", "created_at", "updated_at",
    }  # fmt: skip
    unique = {c.name: [col.name for col in c.columns] for c in OverseasStudentCounselor.__table__.constraints if c.name and c.name.startswith("uq_")}
    assert unique == {"uq_overseas_student_counselors_student": ["student_user_id"]}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert TABLE in await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.fixture
def isolated_db():
    """A fresh database at 0164_agent_org_kyc."""
    cfg = _config()
    original = settings.database_url
    name = f"csc001_migration_{uuid.uuid4().hex[:8]}"
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
    assert {"ix_overseas_student_counselors_counselor_user_id", "uq_overseas_student_counselors_student"} <= indexes
    command.downgrade(isolated_db["cfg"], BASE)
    assert TABLE not in _tables(isolated_db["url"])


def test_one_counselor_per_student_and_downgrade_refuses_while_links_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    student, counselor, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for user_id, role in ((student, "overseas_student"), (counselor, "counselor"), (other, "counselor")):
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
            "VALUES (:id, :email, 'x', 'Csc User', :role, 'overseas', '{}', true, true, 'en-GB')",
            {"id": user_id, "email": f"{user_id.hex[:8]}@example.com", "role": role},
        )
    insert = f"INSERT INTO {TABLE} (id, student_user_id, counselor_user_id, assigned_by_user_id) VALUES (gen_random_uuid(), :s, :c, :c)"
    _sql(url, insert, {"s": student, "c": counselor})
    with pytest.raises(Exception, match="uq_overseas_student_counselors_student"):
        _sql(url, insert, {"s": student, "c": other})
    with pytest.raises(Exception, match="student-counselor links exist"):
        command.downgrade(cfg, BASE)
    assert TABLE in _tables(url)
