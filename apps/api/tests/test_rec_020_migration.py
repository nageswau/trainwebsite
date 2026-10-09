"""rec-020 -- migration 0124_interview_management (spec §2). The backfill (codes in creation order, status from the legacy result), the
CHECKs, the round trip and the downgrade refusal run in a throwaway database built from scratch (the rec-017 pattern); a downgrade never
runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_rec_017_migration import _external, _job
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_020_migration_0124", VERSIONS / "0124_interview_management.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0122_candidate_skills", "0124_interview_management"


def test_migration_chains_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import INTERVIEW_CHECKS, INTERVIEW_EVENT_CHECKS, INTERVIEW_ROUNDS, INTERVIEW_STATUSES, Interview, InterviewEvent

    assert _migration.CHECKS == INTERVIEW_CHECKS
    assert _migration.EVENT_CHECKS == INTERVIEW_EVENT_CHECKS
    assert _migration.ROUNDS == INTERVIEW_ROUNDS and _migration.STATUSES == INTERVIEW_STATUSES
    table = Interview.__table__
    assert not table.c.interview_code.nullable and not table.c.status.nullable and table.c.round.nullable
    names = {i.name for t in (table, InterviewEvent.__table__) for i in t.indexes} | {c.name for t in (table, InterviewEvent.__table__) for c in t.constraints}
    assert set(INTERVIEW_CHECKS) | set(INTERVIEW_EVENT_CHECKS) | set(_migration.INDEXES) <= names
    assert {c.name for c in InterviewEvent.__table__.columns} == {
        "id", "interview_id", "event", "from_status", "to_status", "old_scheduled_at", "new_scheduled_at", "note", "actor_user_id", "position", "created_at",
    }


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec020_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0122 shape of `interviews`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _application(url) -> uuid.UUID:
    app_id, job_id = uuid.uuid4(), _job(url)
    _sql(url, "INSERT INTO job_applications (id, job_id, candidate_id, status, stage_changed_at, created_at, updated_at) VALUES (:id, :j, :c, 'interview', now(), now(), now())",
         {"id": app_id, "j": job_id, "c": _external(url, email=f"{app_id.hex[:10]}@example.com")})
    return app_id


def _interview(url, application_id, result=None, day=1) -> uuid.UUID:
    interview_id = uuid.uuid4()
    _sql(url, "INSERT INTO interviews (id, application_id, scheduled_at, mode, result, created_at, updated_at) VALUES (:id, :a, '2027-02-01T10:00Z', 'Online', :r, now(), now())",
         {"id": interview_id, "a": application_id, "r": result})
    _sql(url, "UPDATE interviews SET created_at = make_timestamptz(2026, 1, :d, 0, 0, 0) WHERE id = :id", {"id": interview_id, "d": day})
    return interview_id


def test_upgrade_backfills_codes_and_statuses(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    application = _application(url)
    rows = {
        None: _interview(url, application, None, 1),
        "selected": _interview(url, application, "selected", 2),
        "rejected": _interview(url, application, "rejected", 3),
        "on_hold": _interview(url, application, "on_hold", 4),
        "cancelled": _interview(url, application, "cancelled", 5),
    }
    command.upgrade(cfg, HEAD)
    stored = {r[0]: r[1:] for r in _sql(url, "SELECT id, interview_code, status, round FROM interviews")}
    assert [stored[rows[k]][0] for k in rows] == ["INT-000001", "INT-000002", "INT-000003", "INT-000004", "INT-000005"]
    assert {k: stored[v][1] for k, v in rows.items()} == {None: "scheduled", "selected": "selected", "rejected": "rejected", "on_hold": "on_hold", "cancelled": "on_hold"}
    assert all(r[2] is None for r in stored.values())
    assert _sql(url, "SELECT nextval('interview_code_seq')") == [(6,)]
    assert _sql(url, "SELECT count(*) FROM interview_events") == [(0,)]


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    application = _application(url)
    for column, value, name in (("status", "lunch", "ck_interviews_status"), ("round", "pub_round", "ck_interviews_round")):
        with pytest.raises(Exception, match=name):
            _sql(url, f"INSERT INTO interviews (id, interview_code, application_id, scheduled_at, mode, {column}, created_at, updated_at) "
                 f"VALUES (:id, :code, :a, now(), 'Online', :v, now(), now())", {"id": uuid.uuid4(), "code": f"INT-{uuid.uuid4().hex[:6]}", "a": application, "v": value})
    _sql(url, "DELETE FROM interviews")
    command.downgrade(cfg, BASE)
    assert "interview_code" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'interviews'")}
    assert _sql(url, "SELECT to_regclass('interview_events')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_events_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    interview = _interview_at_head(url, _application(url))
    _sql(url, "INSERT INTO interview_events (id, interview_id, event, to_status, created_at) VALUES (:id, :i, 'scheduled', 'scheduled', now())", {"id": uuid.uuid4(), "i": interview})
    with pytest.raises(Exception, match="interview history exists"):
        command.downgrade(cfg, BASE)


def _interview_at_head(url, application_id) -> uuid.UUID:
    interview_id = uuid.uuid4()
    _sql(url, "INSERT INTO interviews (id, interview_code, application_id, scheduled_at, mode, created_at, updated_at) VALUES (:id, 'INT-900001', :a, now(), 'Online', now(), now())",
         {"id": interview_id, "a": application_id})
    return interview_id

