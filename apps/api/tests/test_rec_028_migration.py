"""rec-028 -- migration 0118_recruiter_meetings (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-024 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_028_migration_0118", VERSIONS / "0118_recruiter_meetings.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0117_job_descriptions", "0118_recruiter_meetings"
MEETING_COLUMNS = {
    "id", "meeting_code", "company_id", "contact_id", "meeting_type", "starts_at", "mode", "location", "meeting_url", "purpose", "status",
    "outcome", "next_action", "follow_up_id", "completed_at", "completed_by_user_id", "cancelled_at", "cancel_reason", "created_by_user_id",
    "created_at", "updated_at",
}


def test_migration_chains_after_0117_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import RECRUITER_MEETING_CHECKS, RecruiterMeeting, RecruiterMeetingEvent, RecruiterMeetingParticipant

    assert _migration.CHECKS == RECRUITER_MEETING_CHECKS
    tables = {"recruiter_meetings": RecruiterMeeting.__table__, "recruiter_meeting_participants": RecruiterMeetingParticipant.__table__,
              "recruiter_meeting_events": RecruiterMeetingEvent.__table__}
    assert {c.name for c in tables["recruiter_meetings"].columns} == MEETING_COLUMNS
    names = {n for t in tables.values() for n in ({i.name for i in t.indexes} | {c.name for c in t.constraints})}
    assert set(_migration.CHECKS) | set(_migration.INDEXES) <= names
    constraints = {c.name: c for t in tables.values() for c in t.constraints}
    for name, sql in _migration.CHECKS.items():
        assert str(constraints[name].sqltext) == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec028_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> tuple[uuid.UUID, uuid.UUID]:
    company_id, user_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    return company_id, user_id


def _meeting(url, company_id, user_id, **over) -> uuid.UUID:
    values = {"id": uuid.uuid4(), "code": f"MTG-{uuid.uuid4().hex[:6]}", "c": company_id, "u": user_id, "t": "hr_meeting", "m": "Online",
              "s": "scheduled"} | over
    _sql(
        url,
        "INSERT INTO recruiter_meetings (id, meeting_code, company_id, meeting_type, starts_at, mode, status, created_by_user_id, created_at, "
        "updated_at) VALUES (:id, :code, :c, :t, now() + interval '1 day', :m, :s, :u, now(), now())",
        values,
    )
    return values["id"]


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruiter_meetings')") == [(None,)]
    command.upgrade(cfg, HEAD)
    company_id, user_id = _setup(url)
    meeting_id = _meeting(url, company_id, user_id)
    with pytest.raises(Exception, match="ck_recruiter_meetings_type"):
        _meeting(url, company_id, user_id, t="lunch")
    with pytest.raises(Exception, match="ck_recruiter_meetings_mode"):
        _meeting(url, company_id, user_id, m="Carrier pigeon")
    with pytest.raises(Exception, match="ck_recruiter_meetings_state"):
        _meeting(url, company_id, user_id, s="completed")  # completed without completed_at / by / outcome
    with pytest.raises(Exception, match="ck_recruiter_meeting_participants_one"):
        _sql(url, "INSERT INTO recruiter_meeting_participants (id, meeting_id) VALUES (:id, :m)", {"id": uuid.uuid4(), "m": meeting_id})
    assert _sql(url, "SELECT nextval('recruiter_meeting_code_seq') > 0") == [(True,)]
    _sql(url, "DELETE FROM recruiter_meetings")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruiter_meetings')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_meetings_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _meeting(url, *_setup(url))
    with pytest.raises(Exception, match="recruiter meetings exist"):
        command.downgrade(cfg, BASE)
