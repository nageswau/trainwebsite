"""itc-022 -- migration 0249_it_training_progress (DEC-SCOPE-365): programme modules/topics, topic completions, the progress formula,
remediation plans and the enrolment override reason. Round trip in a throwaway database (the upc-001 pattern); no existing row changes."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import Enrollment, ItProgressFormula, RemediationPlan
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_022_migration_0249", VERSIONS / "0249_it_training_progress.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0249_it_training_progress"
BASE = _migration.down_revision
TABLES = ("it_progress_formulas", "program_modules", "program_topics", "remediation_plans", "topic_completions")
PRESENT = "SELECT table_name FROM information_schema.tables WHERE table_name IN (" + ", ".join(f"'{t}'" for t in TABLES) + ") ORDER BY 1"
OVERRIDE = "SELECT column_name FROM information_schema.columns WHERE table_name = 'enrollments' AND column_name = 'progress_override_reason'"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert Enrollment.__table__.columns["progress_override_reason"].nullable
    checks = {c.name for c in ItProgressFormula.__table__.constraints}
    assert "ck_it_progress_formulas_sum" in checks
    assert {c.name for c in RemediationPlan.__table__.constraints} >= {"ck_remediation_plans_status"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc022_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001 builds from the current models: step back to the base to start without the tables
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_creates_the_tables_and_downgrade_removes_them(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, PRESENT) == [] and _sql(url, OVERRIDE) == []

    command.upgrade(cfg, HEAD)
    assert [r[0] for r in _sql(url, PRESENT)] == list(TABLES)
    assert _sql(url, OVERRIDE) == [("progress_override_reason",)]

    command.downgrade(cfg, BASE)
    assert _sql(url, PRESENT) == [] and _sql(url, OVERRIDE) == []
