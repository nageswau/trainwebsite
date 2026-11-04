"""hrc-005 -- migration 0258_vacancy_fields (DEC-SCOPE-381): the chain, the frozen checks and index key, and the round trip in a throwaway
database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_PAY_CHECKS, JOB_TITLE_KEY_SQL
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_005_migration_0258", VERSIONS / "0258_vacancy_fields.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0258_vacancy_fields", "0257_job_approval"


def test_migration_chains_after_0257():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_and_index_key_are_frozen_copies_of_the_model():
    assert _migration.CHECKS == JOB_PAY_CHECKS
    assert _migration.TITLE_KEY == JOB_TITLE_KEY_SQL


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc005_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "requisition_reference" not in _columns(url)
    company, job = uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type) VALUES (:id, :n, 'recruiter', 'internal')", {"id": company, "n": f"Mig {company.hex}"})
    _sql(url, "INSERT INTO jobs (id, company_id, title, location, description, skills, status) VALUES (:id, :c, 'Dev', 'Pune', '', '[]', 'sourcing')",
         {"id": job, "c": company})  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert {"requisition_reference", "city", "salary_currency", "hiring_manager_user_id", "updated_by_user_id"} <= _columns(url)
    assert tuple(_sql(url, "SELECT location, city, salary_currency FROM jobs WHERE id = :id", {"id": job})[0]) == ("Pune", None, None)  # V3: no backfill
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert "requisition_reference" not in _columns(url) and "updated_by_user_id" not in _columns(url)
    assert _sql(url, "SELECT location FROM jobs WHERE id = :id", {"id": job})[0][0] == "Pune"
    command.upgrade(cfg, HEAD)
