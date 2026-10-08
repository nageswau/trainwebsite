"""rec-017 -- migration 0120_job_application_tracking (spec §1; AC3). The backfill (candidates for students, A3 linking), the A1 status
mapping with history, the duplicate refusal and the downgrade refusal run in a throwaway database built from scratch (the rec-007
pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_017_migration_0120", VERSIONS / "0120_job_application_tracking.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0119_recruiter_meetings", "0120_job_application_tracking"


def test_migration_chains_after_0119():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import APPLICATION_CHECKS, APPLICATION_STATUSES, JobApplication, JobApplicationStatusHistory

    assert _migration.CHECKS == APPLICATION_CHECKS
    assert _migration.STATUSES == APPLICATION_STATUSES
    assert set(_migration.LEGACY.values()) <= set(APPLICATION_STATUSES)
    table = JobApplication.__table__
    assert not table.c.candidate_id.nullable and table.c.student_id.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(APPLICATION_CHECKS) | set(_migration.INDEXES) | {_migration.UNIQUE} <= names
    assert {c.name for c in JobApplicationStatusHistory.__table__.columns} == {"id", "application_id", "from_status", "to_status", "note", "changed_by_user_id", "created_at"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0119 shape of `job_applications`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _user(url, role="it_student", email=None, phone=None) -> uuid.UUID:
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, phone, active, email_verified, locale, profile, created_at, updated_at) "
        "VALUES (:id, :e, 'x', :n, :r, 'it', :p, true, true, 'en-GB', '{}', now(), now())",
        {"id": user_id, "e": email or f"{user_id.hex[:10]}@example.com", "n": f"Student {user_id.hex[:4]}", "r": role, "p": phone},
    )
    return user_id


def _job(url) -> uuid.UUID:
    company_id, job_id = uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())", {"id": company_id, "n": f"Co {company_id.hex[:6]}"})
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) VALUES (:id, :c, 'Dev', 'Remote', '', '[]', 'requirement_received', now(), now())",
        {"id": job_id, "c": company_id},
    )
    return job_id


def _application(url, job_id, student_id, status, at=datetime(2026, 1, 1, tzinfo=UTC)) -> uuid.UUID:
    app_id = uuid.uuid4()
    _sql(url, "INSERT INTO job_applications (id, job_id, student_id, status, created_at, updated_at) VALUES (:id, :j, :s, :st, :at, :at)", {"id": app_id, "j": job_id, "s": student_id, "st": status, "at": at})
    return app_id


def _external(url, email=None, mobile=None, mobile_key=None) -> uuid.UUID:
    staff = _user(url, role="placement_team")
    source = _sql(url, "SELECT id FROM rec_candidate_sources WHERE lower(name) = 'linkedin'")[0][0]
    cand_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO candidates (id, candidate_code, name, email, mobile, mobile_normalized, preferred_locations, source_id, status, opted_in, created_by_user_id, created_at, updated_at) "
        "VALUES (:id, :code, 'External Person', :e, :m, :mk, '[]', :src, 'available', false, :by, now(), now())",
        {"id": cand_id, "code": f"CAN-9{cand_id.int % 100000:05d}", "e": email, "m": mobile, "mk": mobile_key, "src": source, "by": staff},
    )
    return cand_id


def test_upgrade_backfills_candidates_and_maps_statuses(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    job, other_job = _job(url), _job(url)
    rahul = _user(url, phone="+91 98765 43210")
    linked_email = _user(url, email="Taken@Example.com")
    linked_mobile = _user(url, phone="+91 91234 56789")
    profile_only = _user(url)
    _sql(url, "INSERT INTO placement_profiles (id, student_id, readiness_status, resume_status, mock_interview_status, aptitude_status, available, withdrawn, created_at, updated_at) "
         "VALUES (:id, :s, 'preparation', 'pending', 'pending', 'pending', false, false, now(), now())", {"id": uuid.uuid4(), "s": profile_only})
    external_email = _external(url, email="taken@example.com")
    external_mobile = _external(url, email="other@example.com", mobile="+91 91234 56789", mobile_key="+919123456789")
    legacy = {
        "applied": _application(url, job, rahul, "applied"),
        "interview_scheduled": _application(url, other_job, rahul, "interview_scheduled"),
        "offer_received": _application(url, job, linked_email, "offer_received"),
        "hired": _application(url, other_job, linked_email, "hired"),
        "screening": _application(url, job, linked_mobile, "screening"),
        "odd": _application(url, other_job, linked_mobile, "on_ice"),
    }
    command.upgrade(cfg, HEAD)

    statuses = dict(_sql(url, "SELECT id, status FROM job_applications"))
    assert statuses == {
        legacy["applied"]: "sourced", legacy["interview_scheduled"]: "interview", legacy["offer_received"]: "selected",
        legacy["hired"]: "joined", legacy["screening"]: "screened", legacy["odd"]: "sourced",
    }
    history = _sql(url, "SELECT application_id, from_status, to_status, note, changed_by_user_id FROM job_application_status_history")
    assert len(history) == 6
    assert (legacy["odd"], None, "sourced", "Legacy status 'on_ice'", None) in history
    # A3: an email or mobile collision links the external candidate and keeps it visible; nobody else is opted in.
    candidates = {r[0]: r[1:] for r in _sql(url, "SELECT user_id, id, opted_in, mobile_normalized, created_by_user_id FROM candidates WHERE user_id IS NOT NULL")}
    assert candidates[linked_email][:2] == (external_email, True)
    assert candidates[linked_mobile][:2] == (external_mobile, True)
    assert candidates[rahul][1:] == (False, "+919876543210", rahul)
    assert candidates[profile_only][1] is False
    per_app = dict(_sql(url, "SELECT a.id, c.user_id FROM job_applications a JOIN candidates c ON c.id = a.candidate_id"))
    assert per_app[legacy["applied"]] == rahul and per_app[legacy["hired"]] == linked_email
    assert _sql(url, "SELECT count(*) FROM job_applications WHERE candidate_id IS NULL") == [(0,)]
    with pytest.raises(Exception, match="ck_job_applications_status"):
        _sql(url, "UPDATE job_applications SET status = 'applied'")
    with pytest.raises(Exception, match="uq_job_applications_candidate_job"):
        _sql(url, "INSERT INTO job_applications (id, job_id, candidate_id, status, stage_changed_at, created_at, updated_at) "
             "SELECT gen_random_uuid(), job_id, candidate_id, 'sourced', now(), now(), now() FROM job_applications LIMIT 1")


def test_upgrade_refuses_duplicate_student_applications(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    job, student = _job(url), _user(url)
    _application(url, job, student, "applied")
    _application(url, job, student, "shortlisted")
    with pytest.raises(Exception, match="duplicate"):
        command.upgrade(cfg, HEAD)


def test_round_trip_restores_legacy_statuses(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    app_id = _application(url, _job(url), _user(url), "interview_scheduled")
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT status FROM job_applications WHERE id = :id", {"id": app_id}) == [("interview_scheduled",)]
    command.upgrade(cfg, HEAD)  # re-runnable: the backfilled candidate is reused, not duplicated
    assert _sql(url, "SELECT count(*) FROM candidates WHERE user_id IS NOT NULL") == [(1,)]


def test_downgrade_refuses_while_tracking_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _application(url, _job(url), _user(url), "applied")
    command.upgrade(cfg, HEAD)
    staff = _user(url, role="placement_team")
    _sql(url, "INSERT INTO job_application_status_history (id, application_id, from_status, to_status, changed_by_user_id, created_at) "
         "SELECT gen_random_uuid(), id, 'sourced', 'screened', :u, now() FROM job_applications", {"u": staff})
    with pytest.raises(Exception, match="tracking data"):
        command.downgrade(cfg, BASE)
