"""hrc-029 -- migration 0280_interview_panel (DEC-SCOPE-405 V1/V7): the two tables, the frozen checks, the chain and the round trip, in a
throwaway database (the hrc-020 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import InterviewInterviewer, InterviewPanelFeedback
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_029_migration_0280", VERSIONS / "0280_interview_panel.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0280_interview_panel", "0278_commercial_grants"
TABLES = ("interview_interviewers", "interview_panel_feedback")


def test_migration_chains_after_0278_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert HEAD in {r.revision for r in script.walk_revisions()} and len(script.get_heads()) == 1


def _checks(model) -> dict:
    return {c.name: str(c.sqltext) for c in model.__table__.constraints if c.name and c.name.startswith("ck_")}


def test_checks_are_frozen_copies_of_the_models():
    assert _checks(InterviewInterviewer) == _migration.ASSIGNMENT_CHECKS
    assert _checks(InterviewPanelFeedback) == _migration.FEEDBACK_CHECKS


def _tables(url) -> set[str]:
    names = ", ".join(f"'{t}'" for t in TABLES)
    return {r[0] for r in _sql(url, f"SELECT table_name FROM information_schema.tables WHERE table_name IN ({names})")}


def test_round_trip():
    cfg = _config()
    original = settings.database_url
    name = f"hrc029_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        assert _tables(url) == set(TABLES)
        command.downgrade(cfg, BASE)
        assert _tables(url) == set()
        command.upgrade(cfg, HEAD)  # replays cleanly, now really creating the tables
        assert _tables(url) == set(TABLES)
        checks = {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_interview_panel%' OR conname LIKE 'ck_interview_interviewers%'")}
        assert set(_migration.ASSIGNMENT_CHECKS) | set(_migration.FEEDBACK_CHECKS) <= checks
        lead = _sql(url, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_interview_interviewers_lead'")
        assert lead and "WHERE is_lead" in lead[0][0]
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
