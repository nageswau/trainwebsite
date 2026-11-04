"""hrc-012 -- migration 0259_candidate_ownership (DEC-SCOPE-382): the chain, the frozen checks, the O9 backfill and the round trip in a
throwaway database (the hrc-011/014 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CandidateAssignmentHistory
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_012_migration_0259", VERSIONS / "0259_candidate_ownership.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0259_candidate_ownership", "0258_vacancy_fields"
TABLES = {"candidate_collaborators", "candidate_assignment_history", "candidate_ownership_settings"}


def test_migration_chains_after_0258():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies():
    model = {c.name: str(c.sqltext) for c in CandidateAssignmentHistory.__table__.constraints if c.name in _migration.HISTORY_CHECKS}
    assert model == _migration.HISTORY_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc012_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidates'")}


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _person(url, role: str) -> str:
    uid = str(uuid.uuid4())
    _sql(url, f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, session_version, locale, profile) "
              f"VALUES ('{uid}', '{uid}@example.local', '!', 'H12 {role}', '{role}', 'it', true, true, 0, 'en', '{{}}')")  # fmt: skip
    return uid


def _candidate(url, creator: str) -> str:
    cid = str(uuid.uuid4())
    source = _sql(url, "SELECT id FROM rec_candidate_sources ORDER BY name LIMIT 1")[0][0]
    _sql(url, f"INSERT INTO candidates (id, candidate_code, name, source_id, status, opted_in, created_by_user_id, preferred_locations, email) "
              f"VALUES ('{cid}', 'CAN-H{cid[:6]}', 'H12', '{source}', 'available', false, '{creator}', '[]', '{cid}@example.com')")  # fmt: skip
    return cid


def test_round_trip_and_backfill(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "owner_user_id" not in _columns(url) and not TABLES & _tables(url)
    recruiter, manager = _person(url, "placement_team"), _person(url, "placement_manager")
    by_recruiter, by_manager = _candidate(url, recruiter), _candidate(url, manager)
    command.upgrade(cfg, HEAD)
    assert {"owner_user_id", "placement_officer_user_id"} <= _columns(url) and TABLES <= _tables(url)
    owners = dict(_sql(url, f"SELECT id::text, owner_user_id::text FROM candidates WHERE id IN ('{by_recruiter}', '{by_manager}')"))
    assert owners == {by_recruiter: recruiter, by_manager: None}  # O9
    assert _sql(url, "SELECT count(*) FROM candidate_assignment_history")[0][0] == 0  # no invented history
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert "owner_user_id" not in _columns(url) and not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
