"""itc-026 -- migration 0235_student_resumes (DEC-SCOPE-350): the resume versions and the one-row limit setting. Round trip in a
throwaway database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import StudentResume, StudentResumeSetting
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_026_migration_0235", VERSIONS / "0235_student_resumes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0235_student_resumes"
BASE = _migration.down_revision
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name IN ('student_resumes', 'student_resume_settings') ORDER BY 1"


def test_migration_is_the_single_head():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    def checks(table):
        return {c.name for c in table.constraints if c.name and c.name.startswith("ck_")}

    assert checks(StudentResume.__table__) == {"ck_student_resumes_visibility", "ck_student_resumes_version"}
    assert checks(StudentResumeSetting.__table__) == {"ck_student_resume_settings_one_row", "ck_student_resume_settings_max_bytes"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc026_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_enforces_the_rules_and_refuses_to_drop_resumes(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert [r[0] for r in _sql(url, TABLES)] == ["student_resume_settings", "student_resumes"]
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
    row = "INSERT INTO student_resumes (id, student_user_id, version, storage_key, content_type, size_bytes, visibility, uploaded_by_user_id) "
    values = "VALUES (:rid, :id, :v, 'student-resumes/x', 'application/pdf', 10, :vis, :id)"
    with pytest.raises(Exception, match="ck_student_resumes_visibility"):
        _sql(url, row + values, {"rid": uuid.uuid4(), "id": user, "v": 1, "vis": "public"}, autocommit=True)
    with pytest.raises(Exception, match="ck_student_resumes_version"):
        _sql(url, row + values, {"rid": uuid.uuid4(), "id": user, "v": 0, "vis": "hr"}, autocommit=True)
    _sql(url, row + values, {"rid": uuid.uuid4(), "id": user, "v": 1, "vis": "hr"}, autocommit=True)
    with pytest.raises(Exception, match="uq_student_resumes_version"):
        _sql(url, row + values, {"rid": uuid.uuid4(), "id": user, "v": 1, "vis": "private"}, autocommit=True)

    with pytest.raises(Exception, match="ck_student_resume_settings_one_row"):
        _sql(url, "INSERT INTO student_resume_settings (id, max_bytes) VALUES (2, 1048576)", autocommit=True)
    with pytest.raises(Exception, match="ck_student_resume_settings_max_bytes"):
        _sql(url, "INSERT INTO student_resume_settings (id, max_bytes) VALUES (1, 20971520)", autocommit=True)

    with pytest.raises(RuntimeError, match="student resumes exist"):
        command.downgrade(cfg, BASE)
