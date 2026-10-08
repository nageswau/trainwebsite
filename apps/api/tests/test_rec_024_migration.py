"""rec-024 -- migration 0113_recruiter_follow_ups (spec §2). Round trip and downgrade refusal run in a throwaway database built from
scratch (the rec-004 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_024_migration_0113", VERSIONS / "0113_recruiter_follow_ups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0112_company_pipeline", "0113_recruiter_follow_ups"
COLUMNS = {
    "id", "company_id", "contact_id", "job_id", "application_id", "reason", "due_at", "notes", "status", "outcome", "completed_at",
    "completed_by_user_id", "cancelled_at", "cancel_reason", "created_by_user_id", "created_at", "updated_at",
}


def test_migration_chains_after_0112_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import RECRUITER_FOLLOW_UP_CHECKS, RecruiterFollowUp

    table = RecruiterFollowUp.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert _migration.CHECKS == RECRUITER_FOLLOW_UP_CHECKS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | set(_migration.INDEXES) <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    assert not table.c.company_id.nullable and not table.c.due_at.nullable and not table.c.reason.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec024_migration_{uuid.uuid4().hex[:8]}"
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


def _follow_up(url, company_id, user_id, **over):
    values = {"id": uuid.uuid4(), "c": company_id, "u": user_id, "r": "jd", "s": "open"} | over
    _sql(
        url,
        "INSERT INTO recruiter_follow_ups (id, company_id, reason, due_at, status, created_by_user_id, created_at, updated_at) "
        "VALUES (:id, :c, :r, now() + interval '1 day', :s, :u, now(), now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruiter_follow_ups')") == [(None,)]
    command.upgrade(cfg, HEAD)
    company_id, user_id = _setup(url)
    _follow_up(url, company_id, user_id)
    with pytest.raises(Exception, match="ck_recruiter_follow_ups_reason"):
        _follow_up(url, company_id, user_id, r="fee_details")
    with pytest.raises(Exception, match="ck_recruiter_follow_ups_status"):
        _follow_up(url, company_id, user_id, s="paused")
    with pytest.raises(Exception, match="ck_recruiter_follow_ups_state"):
        _follow_up(url, company_id, user_id, s="done")  # done without completed_at / by
    _sql(url, "DELETE FROM recruiter_follow_ups")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruiter_follow_ups')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_follow_ups_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _follow_up(url, *_setup(url))
    with pytest.raises(Exception, match="recruiter follow-ups exist"):
        command.downgrade(cfg, BASE)
