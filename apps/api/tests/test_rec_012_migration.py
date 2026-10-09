"""rec-012 -- migration 0135_resume_extraction (spec §2). The round trip runs in a throwaway database built from scratch (the tel-002
pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_012_migration_0135", VERSIONS / "0135_resume_extraction.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0134_application_screenings", "0135_resume_extraction"
COLUMNS = {"extracted_text", "extraction_json", "extracted_at"}


def test_migration_chains_after_rec_018_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_carries_the_columns():
    from app.models import CandidateResume

    assert {c.name for c in _migration._columns()} == COLUMNS
    assert COLUMNS <= {c.name for c in CandidateResume.__table__.columns}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec012_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (these columns included); going to head and back down gives the real 0134 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidate_resumes'")}


def test_round_trip_keeps_existing_resume_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not COLUMNS & _columns(url)
    user_id, candidate_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'U', 'placement_team', 'it', 'x', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"u{user_id.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO candidates (id, candidate_code, name, email, source_id, created_by_user_id, status, preferred_locations) "
        "VALUES (:id, :code, 'Rahul', :e, (SELECT id FROM rec_candidate_sources WHERE name = 'Referral'), :u, 'available', '[]')",
        {"id": candidate_id, "code": f"T-{candidate_id.hex[:8]}", "e": f"c{candidate_id.hex[:8]}@example.com", "u": user_id},
    )
    _sql(
        url,
        "INSERT INTO candidate_resumes (id, candidate_id, version, storage_key, content_type, size_bytes, uploaded_by_user_id) VALUES (:id, :c, 1, 'candidate-resumes/x', 'application/pdf', 10, :u)",
        {"id": uuid.uuid4(), "c": candidate_id, "u": user_id},
    )
    command.upgrade(cfg, HEAD)
    assert COLUMNS <= _columns(url)
    assert _sql(url, "SELECT version, extracted_text, extraction_json, extracted_at FROM candidate_resumes") == [(1, None, None, None)]
    command.downgrade(cfg, BASE)
    assert not COLUMNS & _columns(url)
    assert _sql(url, "SELECT count(*) FROM candidate_resumes")[0][0] == 1
    command.upgrade(cfg, HEAD)
