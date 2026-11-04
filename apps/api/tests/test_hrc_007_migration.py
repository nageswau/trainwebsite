"""hrc-007 -- migration 0257_job_approval (DEC-SCOPE-380): the chain, the frozen copies and the round trip, in a throwaway database
(the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from app.models import JOB_APPROVAL_DEFAULTS, JOB_CHECKS, JOB_SOURCE_CHECK, JOB_SOURCES
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_007_migration_0257", VERSIONS / "0257_job_approval.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0257_job_approval", "0256_candidate_duplicates"


def test_migration_chains_after_0256():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_frozen_copies_match_the_models_and_the_default_grants():
    assert _migration.STATUS_CHECK == JOB_CHECKS["ck_jobs_status"]
    assert _migration.SOURCE_CHECK == JOB_SOURCE_CHECK
    assert _migration.SOURCES == JOB_SOURCES and dict(_migration.SETTINGS) == JOB_APPROVAL_DEFAULTS
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "jobs.approve" in keys}
    assert holders == {r for r, _, _ in _migration.SEED} == {"hr_manager"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc007_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")}


def test_round_trip_backfills_the_source_and_restores_the_old_status_check(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "source" not in _columns(url) and not _sql(url, "SELECT to_regclass('job_approval_settings')")[0][0]
    others = _sql(url, "SELECT count(*) FROM role_permissions WHERE resource <> 'jobs'")[0][0]
    company = uuid.uuid4()
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{company}', 'Mig Co {company.hex[:6]}', 'recruiter', 'internal')")
    employer, legacy, recruiter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES ('{employer}', 'e{employer.hex[:6]}@x.local', 'x', 'E', 'employer', 'it', true, false, 'en-GB', '{{}}')",
    )
    for job, status, by in ((employer, "new", f"'{employer}'"), (legacy, "requirement_received", "NULL"), (recruiter, "new", "NULL")):
        _sql(url, f"INSERT INTO jobs (id, company_id, title, location, description, skills, status) VALUES ('{job}', '{company}', 't', 'l', 'd', '[]', '{status}')")
        _sql(url, f"INSERT INTO job_status_history (id, job_id, from_status, to_status, changed_by_user_id) VALUES ('{uuid.uuid4()}', '{job}', NULL, '{status}', {by})")

    command.upgrade(cfg, HEAD)
    assert {"source", "submitted_by_user_id", "submitted_at"} <= _columns(url)
    sources = dict(_sql(url, f"SELECT id::text, source FROM jobs WHERE company_id = '{company}'"))
    assert sources == {str(employer): "employer", str(legacy): "legacy", str(recruiter): "recruiter"}
    assert dict(_sql(url, "SELECT source, required FROM job_approval_settings")) == JOB_APPROVAL_DEFAULTS
    assert [tuple(r) for r in _sql(url, "SELECT role, resource, action FROM role_permissions WHERE resource = 'jobs'")] == [("hr_manager", "jobs", "approve")]
    _sql(url, f"UPDATE jobs SET status = 'pending_approval' WHERE id = '{employer}'")
    _sql(url, f"UPDATE jobs SET status = 'filled' WHERE id = '{legacy}'")

    command.downgrade(cfg, BASE)
    assert "source" not in _columns(url)
    assert dict(_sql(url, f"SELECT id::text, status FROM jobs WHERE company_id = '{company}'")) == {str(employer): "new", str(legacy): "closed", str(recruiter): "new"}
    assert _sql(url, "SELECT count(*) FROM role_permissions WHERE resource <> 'jobs'")[0][0] == others
    with pytest.raises(Exception, match="ck_jobs_status"):
        _sql(url, f"UPDATE jobs SET status = 'filled' WHERE id = '{legacy}'")
