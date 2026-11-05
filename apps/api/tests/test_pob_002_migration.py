"""pob-002 -- migration 0284_job_revisions (DEC-SCOPE-405 R1/R6/R7/R9): the chain, the frozen checks and the round trip in a throwaway
database (the hrc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_REVISION_CHECKS, JOB_TERMS_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_002_migration_0284", VERSIONS / "0284_job_revisions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0284_job_revisions", "0283_company_business_context"
NEW_COLUMNS = {"interview_rounds", "screening_steps", "decision_maker_contact_id", "expected_tat_days", "payment_trigger", "payment_days",
               "payment_terms", "replacement_terms", "backup_owner_user_id"}  # fmt: skip


def test_migration_chains_after_its_base():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies_of_the_model():
    assert _migration.CHECKS == {**JOB_TERMS_CHECKS, **JOB_REVISION_CHECKS}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob002_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")} & NEW_COLUMNS


def _has_table(url) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'job_revisions'"))


def test_round_trip_adds_and_removes_the_columns_and_table(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _columns(url) == set() and not _has_table(url)
    command.upgrade(cfg, HEAD)
    assert _columns(url) == NEW_COLUMNS and _has_table(url)
    checks = {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE conrelid = 'jobs'::regclass")}
    assert set(JOB_TERMS_CHECKS) <= checks
    command.downgrade(cfg, BASE)
    assert _columns(url) == set() and not _has_table(url)
    command.upgrade(cfg, HEAD)
    assert _columns(url) == NEW_COLUMNS
