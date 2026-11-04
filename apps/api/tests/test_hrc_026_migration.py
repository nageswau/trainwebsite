"""hrc-026 -- migration 0271_application_record (DEC-SCOPE-394): the chain, the checks matching the models, and the round trip with its
backfill, in a throwaway database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import APPLICATION_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_026_migration_0271", VERSIONS / "0271_application_record.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0271_application_record"
BASE = _migration.down_revision


def test_migration_chains_after_its_base_and_is_the_only_head():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_repeat_the_models():
    assert {k: APPLICATION_CHECKS[k] for k in _migration.CHECKS} == _migration.CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc026_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    rows = _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_applications'")
    return {r[0] for r in rows}


def _seed(url) -> dict:
    """One requirement with a recruiter owner, a student application now at Profile Shared (was Shortlisted) and a recruiter-added one."""
    ids = {k: str(uuid.uuid4()) for k in ("rec", "stu", "co", "job", "c1", "c2", "a1", "a2")}
    ids["src"] = str(_sql(url, "SELECT id FROM rec_candidate_sources ORDER BY name LIMIT 1")[0][0])  # migration 0121 seeds the sources
    statements = [
        f"""INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile)
        VALUES ('{ids["rec"]}', '{ids["rec"]}@x.test', 'Rec', 'placement_team', 'it', 'x', true, true, 'en-GB', '{{}}'),
               ('{ids["stu"]}', '{ids["stu"]}@x.test', 'Stu', 'it_student', 'it', 'x', true, true, 'en-GB', '{{}}')""",
        f"""INSERT INTO companies (id, name, partner_type, owner_type, assigned_recruiter_user_id)
        VALUES ('{ids['co']}', 'Mig Co {ids['co'][:6]}', 'recruiter', 'internal', '{ids['rec']}')""",
        f"""INSERT INTO jobs (id, company_id, title, location, description, skills, status, assigned_recruiter_user_id)
        VALUES ('{ids["job"]}', '{ids["co"]}', 'Dev', 'Pune', '', '[]', 'requirement_received', '{ids["rec"]}')""",
        f"""INSERT INTO candidates (id, candidate_code, name, email, preferred_locations, source_id, status, opted_in, created_by_user_id)
        VALUES ('{ids["c1"]}', 'CAN-M{ids["c1"][:5]}', 'One', '{ids["c1"]}@x.test', '[]', '{ids["src"]}', 'available', false, '{ids["rec"]}'),
               ('{ids["c2"]}', 'CAN-M{ids["c2"][:5]}', 'Two', '{ids["c2"]}@x.test', '[]', '{ids["src"]}', 'available', false, '{ids["rec"]}')""",
        f"""INSERT INTO job_applications (id, job_id, candidate_id, student_id, status, added_by_user_id, created_at)
        VALUES ('{ids["a1"]}', '{ids["job"]}', '{ids["c1"]}', '{ids["stu"]}', 'profile_shared', NULL, now() - interval '1 day'),
               ('{ids["a2"]}', '{ids["job"]}', '{ids["c2"]}', NULL, 'sourced', '{ids["rec"]}', now())""",
        f"""INSERT INTO job_application_status_history (id, application_id, from_status, to_status, created_at)
        VALUES ('{uuid.uuid4()}', '{ids["a1"]}', NULL, 'sourced', now() - interval '1 day'),
               ('{uuid.uuid4()}', '{ids["a1"]}', 'sourced', 'shortlisted', now())""",
    ]
    for sql in statements:
        _sql(url, sql)
    return ids


def test_round_trip_numbers_and_backfills_existing_applications(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "application_code" not in _columns(url)
    ids = _seed(url)
    command.upgrade(cfg, HEAD)
    rows = {r[0]: r[1:] for r in _sql(url, "SELECT id::text, application_code, source, candidate_status, owner_user_id::text FROM job_applications")}
    assert rows[ids["a1"]] == ("JA-000001", "portal", "shortlisted", ids["rec"])
    assert rows[ids["a2"]] == ("JA-000002", "recruiter", "sourced", ids["rec"])
    nxt = _sql(url, "SELECT nextval('job_application_code_seq')")[0][0]
    assert nxt == 3
    command.downgrade(cfg, BASE)
    assert not {"application_code", "source", "owner_user_id", "candidate_status", "rejection_reason"} & _columns(url)
