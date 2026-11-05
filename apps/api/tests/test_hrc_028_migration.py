"""hrc-028 -- migration 0274_interview_completion (DEC-SCOPE-399 I1/I3/I4/I6). The round trip runs in a throwaway database built from
scratch (the rec-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_hrc_017_migration import _config, _sql

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_hrc_028_migration_0274", API_ROOT / "alembic" / "versions" / "0274_interview_completion.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0273_candidate_privacy", "0274_interview_completion"


def test_migration_chains_after_candidate_privacy_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import INTERVIEW_CHECKS, INTERVIEW_EVENT_CHECKS, INTERVIEW_EVENTS, INTERVIEW_PLATFORMS, INTERVIEW_STATUSES, Interview, InterviewEvent, RecruiterMessage

    assert _migration.STATUSES == INTERVIEW_STATUSES and _migration.EVENTS == INTERVIEW_EVENTS and _migration.PLATFORMS == INTERVIEW_PLATFORMS
    assert dict([_migration.STATUS_CHECK]) == {"ck_interviews_status": INTERVIEW_CHECKS["ck_interviews_status"]}
    assert dict([_migration.EVENT_CHECK]) == INTERVIEW_EVENT_CHECKS
    assert {k: INTERVIEW_CHECKS[k] for k in _migration.CHECKS} == _migration.CHECKS
    table = Interview.__table__
    assert {n for n, _ in _migration.COLUMNS} | {"time_zone", "calendar_sequence"} <= set(table.c.keys())
    assert not table.c.time_zone.nullable and not table.c.calendar_sequence.nullable
    assert {n for n, _ in _migration.EVENT_COLUMNS} <= set(InterviewEvent.__table__.c.keys())
    assert "calendar_ics" in RecruiterMessage.__table__.c


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc028_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url, table) -> set[str]:
    return {r[0] for r in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)  # 0001 builds from the current models: go down to BASE so the columns are really added
    command.downgrade(cfg, BASE)
    assert _columns(url, "interviews").isdisjoint({"time_zone", "ends_at", "cancel_reason", "calendar_sequence"})
    assert "old_meeting_url" not in _columns(url, "interview_events") and "calendar_ics" not in _columns(url, "recruiter_messages")
    command.upgrade(cfg, HEAD)
    assert {"time_zone", "ends_at", "round_number", "platform", "phone_details", "instructions", "documents_required", "cancel_reason"} <= _columns(url, "interviews")
    checks = dict(_sql(url, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE 'ck_interview%'"))
    assert "cancelled" in checks["ck_interviews_status"] and "details" in checks["ck_interview_events_event"]
    assert {"ck_interviews_round_number", "ck_interviews_platform", "ck_interviews_ends_after_start", "ck_interviews_cancel_reason"} <= set(checks)
