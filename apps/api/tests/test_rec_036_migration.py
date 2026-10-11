"""rec-036 -- migration 0147_program_skills (spec §2). Round trip, keys and downgrade refusal run in a throwaway database built from
scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_036_migration_0147", VERSIONS / "0147_program_skills.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0146_interview_feedback", "0147_program_skills"


def test_migration_chains_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import ProgramSkill

    table = ProgramSkill.__table__
    assert {c.name for c in table.columns} == {"program_id", "skill_id", "added_by_user_id", "created_at"}
    assert {c.name for c in table.primary_key.columns} == {"program_id", "skill_id"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec036_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (this table included); going to head and back down gives the real 0146 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _rows(url) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user_id, program_id, category_id, skill_id = (uuid.uuid4() for _ in range(4))
    _sql(
        url,
        "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES (:id, :e, 'U', 'it_admin', 'it', 'x', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"u{user_id.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO programs (id, slug, category, title, summary, duration, eligibility, fees, certification, curriculum, "
        "placement_assistance, trainer_name, active, created_at, updated_at) VALUES (:id, :s, 'IT', 'Python Full Stack', '', '8w', '', 0, "
        "'Cert', '[]', '', 'T', true, now(), now())",
        {"id": program_id, "s": f"p-{program_id.hex[:8]}"},
    )
    _sql(url, "INSERT INTO skill_categories (id, name, created_at, updated_at) VALUES (:id, :n, now(), now())", {"id": category_id, "n": f"C {category_id.hex[:8]}"})
    _sql(
        url,
        "INSERT INTO skills (id, name, category_id, created_at, updated_at) VALUES (:id, :n, :c, now(), now())",
        {"id": skill_id, "n": f"S {skill_id.hex[:8]}", "c": category_id},
    )
    return user_id, program_id, skill_id


INSERT = "INSERT INTO program_skills (program_id, skill_id, added_by_user_id) VALUES (:p, :s, :u)"


def test_round_trip_keys_and_cascade(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user_id, program_id, skill_id = _rows(url)
    _sql(url, INSERT, {"p": program_id, "s": skill_id, "u": user_id})
    with pytest.raises(Exception, match="pkey"):
        _sql(url, INSERT, {"p": program_id, "s": skill_id, "u": user_id})  # a skill is tagged once per program
    with pytest.raises(Exception, match="foreign key"):
        _sql(url, "DELETE FROM skills WHERE id = :s", {"s": skill_id})  # a tagged skill is never deleted underneath (merge re-points)
    with pytest.raises(Exception, match="program skill tags exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM programs WHERE id = :p", {"p": program_id})  # a program's tags go with it
    assert _sql(url, "SELECT count(*) FROM program_skills")[0][0] == 0
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'program_skills'")
