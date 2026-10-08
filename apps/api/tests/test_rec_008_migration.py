"""rec-008 -- migration 0117_job_descriptions (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-004 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_008_migration_0117", VERSIONS / "0117_job_descriptions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0116_recruiter_follow_ups", "0117_job_descriptions"
COLUMNS = {
    "id", "job_id", "jd_number", "version", "is_current", "role", "experience", "qualification", "skills", "salary", "location",
    "description", "responsibilities", "requirements", "openings", "contact_id", "closing_date", "storage_key", "file_name",
    "content_type", "size_bytes", "created_by_user_id", "created_at",
}


def test_migration_chains_after_0116_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import JOB_DESCRIPTION_CHECKS, JobDescription

    table = JobDescription.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert _migration.CHECKS == JOB_DESCRIPTION_CHECKS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | {"uq_job_descriptions_version", "uq_job_descriptions_current", "ix_job_descriptions_number"} <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    assert not table.c.job_id.nullable and not table.c.role.nullable and not table.c.jd_number.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec008_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> tuple[uuid.UUID, uuid.UUID]:
    company_id, user_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) "
        "VALUES (:id, :c, 'Dev', 'Hyderabad', '', '[]', 'new', now(), now())",
        {"id": job_id, "c": company_id},
    )
    return job_id, user_id


def _jd(url, job_id, user_id, **over):
    values = {"id": uuid.uuid4(), "j": job_id, "u": user_id, "v": 1, "cur": True, "o": None, "k": None} | over
    _sql(
        url,
        "INSERT INTO job_descriptions (id, job_id, jd_number, version, is_current, role, openings, storage_key, created_by_user_id, created_at) "
        "VALUES (:id, :j, 'JD-000001', :v, :cur, 'Dev', :o, :k, :u, now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('job_descriptions')") == [(None,)]
    command.upgrade(cfg, HEAD)
    job_id, user_id = _setup(url)
    _jd(url, job_id, user_id)
    with pytest.raises(Exception, match="uq_job_descriptions_current"):
        _jd(url, job_id, user_id, v=2)  # a second current version
    with pytest.raises(Exception, match="uq_job_descriptions_version"):
        _jd(url, job_id, user_id, cur=False)
    with pytest.raises(Exception, match="ck_job_descriptions_openings"):
        _jd(url, job_id, user_id, v=3, cur=False, o=0)
    with pytest.raises(Exception, match="ck_job_descriptions_file"):
        _jd(url, job_id, user_id, v=4, cur=False, k="job-descriptions/x")  # a key without its name/type/size
    _sql(url, "DELETE FROM job_descriptions")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('job_descriptions')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_job_descriptions_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _jd(url, *_setup(url))
    with pytest.raises(Exception, match="job descriptions exist"):
        command.downgrade(cfg, BASE)
