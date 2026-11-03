"""itc-027 -- migration 0237_hr_review_tasks: chain, the CHECKs, one task per student, the queue index and a round trip, in a throwaway
database (the tel-001 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import HR_REVIEW_STAGES
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_027_migration_0237", VERSIONS / "0237_hr_review_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = _migration.down_revision, "0237_hr_review_tasks"
NAMES = ("hr_assignment_rules", "hr_review_stage_history", "hr_review_tasks")
TABLES = f"SELECT table_name FROM information_schema.tables WHERE table_name IN {NAMES} ORDER BY 1"


def test_migration_is_in_the_single_head_chain_and_repeats_the_stages():
    assert _migration.revision == HEAD and _migration.STAGES == HR_REVIEW_STAGES
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg, original = _config(), settings.database_url
    name = f"itc027_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)  # 0001's create_all already holds today's shape: 0237 must be a no-op on top of it
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _user(url: str) -> uuid.UUID:
    uid = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Student', 'it_student', 'it', true, true, 'en-GB', '{}')",
        {"id": uid, "email": f"s-{uid.hex[:8]}@example.local"},
        autocommit=True,
    )
    return uid


def test_constraints_unique_student_index_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == [(n,) for n in NAMES]
    student = _user(url)
    insert = "INSERT INTO hr_review_tasks (id, student_user_id, stage, resume_version, checklist) VALUES ('{}', '{}', '{}', 1, '[]')"
    with pytest.raises(Exception, match="ck_hr_review_tasks_stage"):
        _sql(url, insert.format(uuid.uuid4(), student, "hired"))
    _sql(url, insert.format(uuid.uuid4(), student, "resume_received"))
    with pytest.raises(Exception, match="uq_hr_review_tasks_student"):
        _sql(url, insert.format(uuid.uuid4(), student, "under_review"))
    index = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_hr_review_tasks_owner_stage'")
    assert "owner_user_id, stage" in index[0][0]

    _sql(url, "DELETE FROM hr_review_tasks")
    command.downgrade(cfg, BASE)
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == [(n,) for n in NAMES]
