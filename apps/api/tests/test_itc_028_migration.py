"""itc-028 -- migration 0234_it_student_notes (DEC-SCOPE-351): the IT student notes table. Round trip in a throwaway database built from
scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import ItStudentNote
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_028_migration_0234", VERSIONS / "0234_it_student_notes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0234_it_student_notes"
BASE = _migration.down_revision
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name = 'it_student_notes'"


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert {c.name for c in ItStudentNote.__table__.constraints if c.name and c.name.startswith("ck_")} == {"ck_it_student_notes_visibility"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc028_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_defaults_to_internal_and_refuses_to_drop_notes(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == [("it_student_notes",)]
    command.downgrade(cfg, BASE)  # empty: drops cleanly
    command.upgrade(cfg, HEAD)
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Student', 'it_student', 'it', true, true, 'en-GB', '{}')",
        {"id": user, "email": f"s-{user.hex[:8]}@example.local"},
        autocommit=True,
    )
    with pytest.raises(Exception, match="ck_it_student_notes_visibility"):
        _sql(url, "INSERT INTO it_student_notes (id, student_user_id, author_user_id, body, visibility) VALUES (:n, :id, :id, 'x', 'public')",
             {"n": uuid.uuid4(), "id": user}, autocommit=True)  # fmt: skip
    _sql(url, "INSERT INTO it_student_notes (id, student_user_id, author_user_id, body) VALUES (:n, :id, :id, 'x')", {"n": uuid.uuid4(), "id": user}, autocommit=True)
    assert _sql(url, "SELECT visibility, shared_at FROM it_student_notes")[0] == ("internal", None)  # N4: internal by default
    with pytest.raises(RuntimeError, match="IT student notes exist"):
        command.downgrade(cfg, BASE)
