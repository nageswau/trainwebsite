"""pob-017 -- migration 0310_sourcing_plans (DEC-SCOPE-429): the chain, the frozen checks, the S6 backfill and the round trip, in a throwaway
database (the pob-016 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_SOURCING_PLAN_CHECKS
from app.services.applications import SUBMITTED
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_017_migration", VERSIONS / "0310_sourcing_plans.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
TABLES = ("job_sourcing_plans", "job_sourcing_channels", "job_sourcing_searches")
COMPANY = "00000000-0000-4000-8000-000000000017"
USER = "00000000-0000-4000-8000-000000000117"
JOB = "00000000-0000-4000-8000-000000000217"


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.PLAN_CHECKS == JOB_SOURCING_PLAN_CHECKS
    assert _migration.SUBMITTED == SUBMITTED


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _has_column(url) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'job_applications' AND column_name = 'submitted_source_id'"))


def _application(url, status: str, source: str) -> str:
    candidate, application = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(url, f"INSERT INTO candidates (id, candidate_code, name, email, preferred_locations, source_id, created_by_user_id) VALUES "
              f"('{candidate}', 'C17-{candidate[:6]}', 'P', '{candidate[:8]}@x.local', '[]', '{source}', '{USER}')", autocommit=True)  # fmt: skip
    _sql(url, f"INSERT INTO job_applications (id, job_id, candidate_id, status) VALUES ('{application}', '{JOB}', '{candidate}', '{status}')", autocommit=True)
    return application


def test_the_round_trip_backfills_submitted_applications(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so remove what 0310 adds first: the guarded upgrade must add it back
    for table in TABLES:
        _sql(url, f"DROP TABLE IF EXISTS {table}", autocommit=True)
    _sql(url, "ALTER TABLE job_applications DROP COLUMN IF EXISTS submitted_source_id", autocommit=True)
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{COMPANY}', 'Pob 017 Kept', 'recruiter', 'recruiter')", autocommit=True)
    _sql(url, f"INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES ('{USER}', 'pob017@x.local', 'P', 'placement_team', 'it', 'x', true, true, 'en', '{{}}')", autocommit=True)
    _sql(url, f"INSERT INTO jobs (id, company_id, title, location, description, skills, status) VALUES ('{JOB}', '{COMPANY}', 'Kept', 'Pune', '', '[]', 'sourcing')", autocommit=True)
    source = _sql(url, "SELECT id FROM rec_candidate_sources ORDER BY name LIMIT 1")[0][0]
    shared, waiting = _application(url, "interview", source), _application(url, "sourced", source)

    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and _has_column(url)
    rows = dict(_sql(url, f"SELECT id::text, submitted_source_id::text FROM job_applications WHERE job_id = '{JOB}'"))
    assert rows == {shared: str(source), waiting: None}

    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url) and not _has_column(url)
    assert _sql(url, f"SELECT count(*) FROM job_applications WHERE job_id = '{JOB}'") == [(2,)]  # no row is lost
