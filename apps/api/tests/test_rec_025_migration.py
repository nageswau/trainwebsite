"""rec-025 -- migration 0117_recruiter_calls (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-004 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_025_migration_0117", VERSIONS / "0117_recruiter_calls.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0116_recruiter_follow_ups", "0117_recruiter_calls"
COLUMNS = {
    "id", "company_id", "contact_id", "candidate_id", "caller_user_id", "occurred_at", "duration_seconds", "direction", "outcome", "notes",
    "created_at", "updated_at",
}


def test_migration_chains_after_0116_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import RECRUITER_CALL_CHECKS, RecruiterCall

    table = RecruiterCall.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert _migration.CHECKS == RECRUITER_CALL_CHECKS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | set(_migration.INDEXES) <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    assert not table.c.caller_user_id.nullable and not table.c.occurred_at.nullable and table.c.duration_seconds.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec025_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> dict:
    ids = {"company": uuid.uuid4(), "contact": uuid.uuid4(), "user": uuid.uuid4()}
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": ids["company"], "n": f"Co {ids['company'].hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO company_contacts (id, company_id, name, is_primary, active, created_at, updated_at) VALUES (:id, :c, 'Priya', true, true, now(), now())",
        {"id": ids["contact"], "c": ids["company"]},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": ids["user"], "e": f"{ids['user'].hex[:8]}@example.local"},
    )
    return ids


def _call(url, ids, **over):
    values = {"id": uuid.uuid4(), "co": ids["company"], "ct": ids["contact"], "cand": None, "u": ids["user"], "d": "outgoing", "o": "connected",
              "s": 60} | over
    _sql(
        url,
        "INSERT INTO recruiter_calls (id, company_id, contact_id, candidate_id, caller_user_id, occurred_at, duration_seconds, direction, outcome, "
        "created_at, updated_at) VALUES (:id, :co, :ct, :cand, :u, now(), :s, :d, :o, now(), now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruiter_calls')") == [(None,)]
    command.upgrade(cfg, HEAD)
    ids = _setup(url)
    _call(url, ids)
    _call(url, ids, s=None)  # CA8: duration is optional
    with pytest.raises(Exception, match="ck_recruiter_calls_outcome"):
        _call(url, ids, o="interested")
    with pytest.raises(Exception, match="ck_recruiter_calls_direction"):
        _call(url, ids, d="missed")
    with pytest.raises(Exception, match="ck_recruiter_calls_duration"):
        _call(url, ids, s=14401)
    with pytest.raises(Exception, match="ck_recruiter_calls_party"):
        _call(url, ids, co=None)  # a contact without its company
    with pytest.raises(Exception, match="ck_recruiter_calls_party"):
        _call(url, ids, co=None, ct=None)  # no party at all
    _sql(url, "DELETE FROM recruiter_calls")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruiter_calls')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_calls_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _call(url, _setup(url))
    with pytest.raises(Exception, match="recruiter calls exist"):
        command.downgrade(cfg, BASE)
