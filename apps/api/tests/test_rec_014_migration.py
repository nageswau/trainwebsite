"""rec-014 -- migration 0137_resume_search (spec §2, FT8): a generated `search_vector` over the extracted text and its GIN index. The
round trip runs in a throwaway database built from scratch (the tel-002 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_014_migration_0137", VERSIONS / "0137_resume_search.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0136_partnership_events", "0137_resume_search"


def test_migration_chains_after_upc_011_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_carries_the_generated_column_and_the_gin_index():
    from app.models import CandidateResume

    column = CandidateResume.__table__.c.search_vector
    assert column.computed is not None and column.computed.persisted
    assert "to_tsvector('english'" in str(column.computed.sqltext) and _migration.EXPRESSION == str(column.computed.sqltext)
    index = next(i for i in CandidateResume.__table__.indexes if i.name == _migration.INDEX)
    assert index.dialect_options["postgresql"]["using"] == "gin"


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec014_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (the column included); going to head and back down gives the real 0136 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _vector_column(url):
    return _sql(url, "SELECT is_generated FROM information_schema.columns WHERE table_name = 'candidate_resumes' AND column_name = 'search_vector'")


def _index(url):
    return _sql(url, f"SELECT indexdef FROM pg_indexes WHERE indexname = '{_migration.INDEX}'")


def test_round_trip_fills_the_vector_of_existing_rows_and_keeps_them(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _vector_column(url) == [] and _index(url) == []
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
        "INSERT INTO candidate_resumes (id, candidate_id, version, storage_key, content_type, size_bytes, uploaded_by_user_id, extracted_text) "
        "VALUES (:id, :c, 1, 'candidate-resumes/x', 'application/pdf', 10, :u, 'Built Microservices with Spring Boot')",
        {"id": uuid.uuid4(), "c": candidate_id, "u": user_id},
    )
    command.upgrade(cfg, HEAD)
    assert _vector_column(url) == [("ALWAYS",)]
    assert "USING gin (search_vector)" in _index(url)[0][0]
    assert _sql(url, "SELECT search_vector @@ websearch_to_tsquery('english', 'microservice spring') FROM candidate_resumes") == [(True,)]
    command.downgrade(cfg, BASE)
    assert _vector_column(url) == [] and _index(url) == []
    assert _sql(url, "SELECT extracted_text FROM candidate_resumes") == [("Built Microservices with Spring Boot",)]
    command.upgrade(cfg, HEAD)
