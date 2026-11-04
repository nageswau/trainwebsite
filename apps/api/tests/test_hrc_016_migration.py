"""hrc-016 -- migration 0262_candidate_notes_tasks (DEC-SCOPE-385): the chain, the frozen checks and the round trip in a throwaway database
(the hrc-012 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import CANDIDATE_NOTE_TASK_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_016_migration_0262", VERSIONS / "0262_candidate_notes_tasks.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0262_candidate_notes_tasks", "0261_job_assignments"
TABLES = {"candidate_notes", "candidate_tasks"}


def test_migration_chains_after_0261():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_are_frozen_copies():
    assert _migration.CHECKS == CANDIDATE_NOTE_TASK_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc016_migration_{uuid.uuid4().hex[:8]}"
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


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def test_round_trip_and_guarded_downgrade(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)
    uid, cid = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(url, f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, session_version, locale, profile) "
              f"VALUES ('{uid}', '{uid}@example.local', '!', 'H16', 'placement_team', 'it', true, true, 0, 'en', '{{}}')")  # fmt: skip
    source = _sql(url, "SELECT id FROM rec_candidate_sources ORDER BY name LIMIT 1")[0][0]
    _sql(url, f"INSERT INTO candidates (id, candidate_code, name, source_id, status, opted_in, created_by_user_id, preferred_locations, email) "
              f"VALUES ('{cid}', 'CAN-H{cid[:6]}', 'H16', '{source}', 'available', false, '{uid}', '[]', '{cid}@example.com')")  # fmt: skip
    _sql(url, f"INSERT INTO candidate_notes (id, candidate_id, author_user_id, body) VALUES (gen_random_uuid(), '{cid}', '{uid}', 'kept')")
    with pytest.raises(RuntimeError, match="candidate notes or tasks exist"):
        command.downgrade(cfg, BASE)
