"""itc-012 -- migration 0229_it_student_profiles (DEC-SCOPE-345): the `it_student_profiles` table and the nullable enrolment override
columns. Round trip and the downgrade refusal run in a throwaway database built from scratch (the itc-003 pattern). Plain tests:
alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import Enrollment, ItStudentProfile
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_012_migration_0229", VERSIONS / "0229_it_student_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0229_it_student_profiles"
BASE = _migration.down_revision
TABLE = "it_student_profiles"
OVERRIDES = {"start_date", "end_date", "delivery_mode"}


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert ItStudentProfile.__tablename__ == TABLE
    assert {c.name for c in ItStudentProfile.__table__.columns} == {
        "student_user_id", "date_of_birth", "address", "city", "qualification", "graduation_year", "emergency_contact_name",
        "emergency_contact_relation", "emergency_contact_phone", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip
    assert OVERRIDES <= {c.name for c in Enrollment.__table__.columns}
    assert all(Enrollment.__table__.columns[name].nullable for name in OVERRIDES)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc012_migration_{uuid.uuid4().hex[:8]}"
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


def _enrollment_columns(url: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'enrollments'")}


def test_round_trip_adds_and_drops_the_table_and_columns(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert TABLE not in _tables(url) and not OVERRIDES & _enrollment_columns(url)
    command.upgrade(cfg, HEAD)
    assert TABLE in _tables(url) and OVERRIDES <= _enrollment_columns(url)
    command.downgrade(cfg, BASE)
    assert TABLE not in _tables(url) and not OVERRIDES & _enrollment_columns(url)


def test_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    student = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, :email, 'x', 'Itc User', 'it_student', 'it', '{}', true, true, 'en-GB')",
        {"id": student, "email": f"{student.hex[:8]}@example.com"},
    )
    _sql(url, f"INSERT INTO {TABLE} (student_user_id, city) VALUES (:s, 'Pune')", {"s": student})
    with pytest.raises(Exception, match="IT student profiles exist"):
        command.downgrade(cfg, BASE)
    assert TABLE in _tables(url)
