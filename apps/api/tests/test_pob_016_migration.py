"""pob-016 -- migration 0298_requirement_checklist (DEC-SCOPE-419): the chain, the frozen checks and the round trip, in a throwaway database
(the pob-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import JOB_CHECKLIST_ITEM_CHECKS, RECRUITER_FOLLOW_UP_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_016_migration", VERSIONS / "0298_requirement_checklist.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
TABLES = ("job_checklist_items", "job_checklist_overrides", "requirement_checklist_settings")
COMPANY = "00000000-0000-4000-8000-000000000016"
USER = "00000000-0000-4000-8000-000000000116"
REASON = "ck_recruiter_follow_ups_reason"


def test_migration_is_in_the_single_chain():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies():
    assert _migration.ITEM_CHECKS == JOB_CHECKLIST_ITEM_CHECKS
    assert _migration.REASON_CHECK == RECRUITER_FOLLOW_UP_CHECKS[REASON]


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob016_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _has_column(url) -> bool:
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'checklist_blocks_sourcing'"))


def _follow_up(url, reason: str) -> None:
    _sql(url, f"INSERT INTO recruiter_follow_ups (id, company_id, reason, due_at, status, created_by_user_id) VALUES "
              f"(gen_random_uuid(), '{COMPANY}', '{reason}', now(), 'open', '{USER}')", autocommit=True)  # fmt: skip


def test_the_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so remove what 0298 adds first: the guarded upgrade must add it back
    for table in TABLES:
        _sql(url, f"DROP TABLE IF EXISTS {table}", autocommit=True)
    _sql(url, "ALTER TABLE companies DROP COLUMN IF EXISTS checklist_blocks_sourcing", autocommit=True)
    _sql(url, f"ALTER TABLE recruiter_follow_ups DROP CONSTRAINT {REASON}", autocommit=True)
    _sql(url, f"ALTER TABLE recruiter_follow_ups ADD CONSTRAINT {REASON} CHECK ({_migration.OLD_REASON_CHECK})", autocommit=True)
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{COMPANY}', 'Pob 016 Kept', 'recruiter', 'recruiter')", autocommit=True)
    _sql(url, f"INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale) VALUES ('{USER}', 'pob016@x.local', 'P', 'placement_team', 'it', 'x', true, true, 'en')", autocommit=True)
    _follow_up(url, "jd")
    with pytest.raises(Exception, match=REASON):
        _follow_up(url, "clarification")

    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and _has_column(url)
    _follow_up(url, "clarification")
    assert _sql(url, f"SELECT checklist_blocks_sourcing FROM companies WHERE id = '{COMPANY}'") == [(None,)]

    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url) and not _has_column(url)
    assert _sql(url, f"SELECT reason, count(*) FROM recruiter_follow_ups WHERE company_id = '{COMPANY}' GROUP BY reason") == [("jd", 2)]  # no row is lost
    with pytest.raises(Exception, match=REASON):
        _follow_up(url, "clarification")

    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and _has_column(url)
