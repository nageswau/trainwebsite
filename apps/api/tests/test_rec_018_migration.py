"""rec-018 -- migration 0134_application_screenings (spec §1). Round trip, constraints and downgrade refusal run in a throwaway database
built from scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_018_migration_0134", VERSIONS / "0134_application_screenings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0133_interview_management", "0134_application_screenings"


def test_migration_chains_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import SCREENING_CHECKS, ApplicationScreening

    assert _migration.CHECKS == SCREENING_CHECKS  # one source of truth for the CHECK text
    table = ApplicationScreening.__table__
    assert {c.name for c in table.columns} == {
        "application_id",
        "qualification_verified",
        "experience_verified",
        "skills_verified",
        "expected_salary",
        "notice_days",
        "location_preference",
        "communication_rating",
        "technical_rating",
        "availability",
        "willing_to_relocate",
        "remarks",
        "result",
        "screened_by_user_id",
        "created_at",
        "updated_at",
    }
    assert set(SCREENING_CHECKS) <= {c.name for c in table.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec018_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (this table included); going to head and back down gives the real 0133 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _application(url) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, candidate_id, company_id, job_id, application_id = (uuid.uuid4() for _ in range(5))
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
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:8]}"},
    )
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) VALUES (:id, :c, 'Dev', 'Pune', '', '[]', 'requirement_received', now(), now())",
        {"id": job_id, "c": company_id},
    )
    _sql(
        url,
        "INSERT INTO job_applications (id, job_id, candidate_id, status, stage_changed_at, created_at, updated_at) VALUES (:id, :j, :c, 'sourced', now(), now(), now())",
        {"id": application_id, "j": job_id, "c": candidate_id},
    )
    return user_id, application_id


INSERT = (
    "INSERT INTO application_screenings (application_id, result, remarks, communication_rating, technical_rating, notice_days, "
    "expected_salary, screened_by_user_id) VALUES (:a, :result, :remarks, :comm, :tech, :notice, :salary, :u)"
)


def _row(url, user_id, application_id, *, result="shortlisted", remarks=None, comm=None, tech=None, notice=None, salary=None):
    _sql(url, INSERT, {"a": application_id, "result": result, "remarks": remarks, "comm": comm, "tech": tech, "notice": notice, "salary": salary, "u": user_id})


def test_round_trip_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user_id, application_id = _application(url)
    for kwargs, check in (
        ({"result": "maybe"}, "ck_application_screenings_result"),
        ({"result": "rejected"}, "ck_application_screenings_rejected_remarks"),
        ({"comm": 0}, "ck_application_screenings_communication"),
        ({"tech": 6}, "ck_application_screenings_technical"),
        ({"notice": 366}, "ck_application_screenings_notice"),
        ({"salary": -1}, "ck_application_screenings_salary"),
    ):
        with pytest.raises(Exception, match=check):
            _row(url, user_id, application_id, **kwargs)
    _row(url, user_id, application_id, result="rejected", remarks="No Java", comm=1, tech=5, notice=365, salary=0)
    with pytest.raises(Exception, match="pkey"):
        _row(url, user_id, application_id)  # one current screening per application (SC5)
    with pytest.raises(Exception, match="screenings exist"):
        command.downgrade(cfg, BASE)
