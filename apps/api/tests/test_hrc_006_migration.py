"""hrc-006 -- migration 0261_job_assignments (DEC-SCOPE-384 O1/O2): the chain, the frozen checks, and the round trip with the primary
backfill in a throwaway database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_ASSIGNMENT_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_006_migration_0261", VERSIONS / "0261_job_assignments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0261_job_assignments", "0260_candidate_profile"


def test_migration_chains_after_its_base():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies_of_the_model():
    assert _migration.CHECKS == JOB_ASSIGNMENT_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc006_migration_{uuid.uuid4().hex[:8]}"
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


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'job_assignment%'")}


def test_round_trip_backfills_the_primary(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _tables(url) == set()
    company, owned, unowned, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
              "VALUES (:id, :e, 'x', 'Mig Rec', 'placement_team', 'it', true, true, 'en-GB', '{}')", {"id": user, "e": f"mig.{user.hex}@example.local"})  # fmt: skip
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type) VALUES (:id, :n, 'recruiter', 'internal')", {"id": company, "n": f"Mig {company.hex}"})
    for job, owner in ((owned, user), (unowned, None)):
        _sql(url, "INSERT INTO jobs (id, company_id, title, location, description, skills, status, assigned_recruiter_user_id) "
                  "VALUES (:id, :c, 'Dev', 'Pune', '', '[]', 'sourcing', :o)", {"id": job, "c": company, "o": owner})  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert _tables(url) == {"job_assignments", "job_assignment_history"}
    rows = _sql(url, "SELECT job_id, user_id, role, action, reason, changed_by_user_id FROM job_assignment_history")
    assert [tuple(r) for r in rows] == [(owned, user, "primary", "added", "backfill", None)]
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert _tables(url) == set()
    assert _sql(url, "SELECT assigned_recruiter_user_id FROM jobs WHERE id = :id", {"id": owned})[0][0] == user
    command.upgrade(cfg, HEAD)
