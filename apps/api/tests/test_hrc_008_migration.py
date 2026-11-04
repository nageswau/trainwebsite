"""hrc-008 -- migration 0262_job_visibility (DEC-SCOPE-385): the chain, the frozen copies and the round trip, in a throwaway database
(the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core import rbac
from app.core.config import settings
from app.models import JOB_SEGMENT_POOL_CHECK, JOB_VISIBILITIES, JOB_VISIBILITY_CHECK
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_008_migration_0262", VERSIONS / "0262_job_visibility.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0262_job_visibility", "0261_job_assignments"


def test_migration_chains_after_0261():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_frozen_copies_match_the_models_and_the_default_grants():
    assert _migration.VISIBILITY_CHECK == JOB_VISIBILITY_CHECK and _migration.SEGMENT_CHECK == JOB_SEGMENT_POOL_CHECK
    assert _migration.VISIBILITIES == JOB_VISIBILITIES
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "jobs.publish" in keys}
    assert holders == {r for r, _, _ in _migration.SEED} == {"placement_manager"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc008_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_defaults_existing_jobs_to_public(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not {"visibility", "segment_pool_id"} & _columns(url)
    assert not _sql(url, "SELECT 1 FROM role_permissions WHERE role = 'placement_manager' AND resource = 'jobs' AND action = 'publish'")
    company = uuid.uuid4()
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{company}', 'Vis Co {company.hex[:6]}', 'recruiter', 'internal')")
    _sql(url, f"INSERT INTO jobs (id, company_id, title, location, description, skills, status) VALUES ('{uuid.uuid4()}', '{company}', 't', 'l', 'd', '[]', 'sourcing')")
    command.upgrade(cfg, HEAD)
    assert {"visibility", "segment_pool_id"} <= _columns(url)
    assert [tuple(r) for r in _sql(url, "SELECT DISTINCT visibility FROM jobs")] == [("public",)]  # V3
    assert _sql(url, "SELECT 1 FROM role_permissions WHERE role = 'placement_manager' AND resource = 'jobs' AND action = 'publish'")
    assert _sql(url, "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_jobs_status_visibility'")
    command.downgrade(cfg, BASE)
    assert not {"visibility", "segment_pool_id"} & _columns(url)
