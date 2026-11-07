"""pob-008 -- migration 0304_outreach_cadences (DEC-SCOPE-423 B12): the chain, the frozen checks, the backlog stamp and the round trip, in a
throwaway database (the pob-016 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import RECRUITER_CONTACT_CADENCE_CHECKS, RECRUITER_FOLLOW_UP_CHECKS, RecruiterFollowUp
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_008_migration", VERSIONS / "0304_outreach_cadences.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = _migration.revision, _migration.down_revision
TABLES = ("recruiter_cadences", "recruiter_contact_cadences")
COMPANY = "00000000-0000-4000-8000-000000000008"
USER = "00000000-0000-4000-8000-000000000108"
REASON = "ck_recruiter_follow_ups_reason"


def test_migration_is_in_the_single_chain():
    assert (HEAD, BASE) == ("0304_outreach_cadences", "0303_company_bd_stages")
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies_of_the_models():
    assert _migration.REASON_CHECK == RECRUITER_FOLLOW_UP_CHECKS[REASON]
    assert _migration.RUN_CHECKS == RECRUITER_CONTACT_CADENCE_CHECKS
    assert "reminded_at" in RecruiterFollowUp.__table__.c and _migration.UNREMINDED in {i.name for i in RecruiterFollowUp.__table__.indexes}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob008_migration_{uuid.uuid4().hex[:8]}"
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
    return bool(_sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'recruiter_follow_ups' AND column_name = 'reminded_at'"))


def _follow_up(url, reason: str, due: str) -> None:
    _sql(url, f"INSERT INTO recruiter_follow_ups (id, company_id, reason, due_at, status, created_by_user_id) VALUES "
              f"(gen_random_uuid(), '{COMPANY}', '{reason}', {due}, 'open', '{USER}')", autocommit=True)  # fmt: skip


def test_the_round_trip_stamps_the_backlog_and_keeps_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so remove what 0304 adds first: the guarded upgrade must add it back
    for table in ("recruiter_contact_cadences", "recruiter_cadences"):
        _sql(url, f"DROP TABLE IF EXISTS {table}", autocommit=True)
    _sql(url, f"DROP INDEX IF EXISTS {_migration.UNREMINDED}", autocommit=True)
    _sql(url, "ALTER TABLE recruiter_follow_ups DROP COLUMN IF EXISTS reminded_at", autocommit=True)
    _sql(url, f"ALTER TABLE recruiter_follow_ups DROP CONSTRAINT {REASON}", autocommit=True)
    _sql(url, f"ALTER TABLE recruiter_follow_ups ADD CONSTRAINT {REASON} CHECK ({_migration.OLD_REASON_CHECK})", autocommit=True)
    _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES ('{COMPANY}', 'Pob 008 Kept', 'recruiter', 'recruiter')", autocommit=True)
    _sql(url, f"INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES ('{USER}', 'pob008@x.local', 'P', 'placement_team', 'it', 'x', true, true, 'en', '{{}}')", autocommit=True)
    _follow_up(url, "jd", "now() - interval '2 days'")  # overdue: stamped, so no backlog reminder
    _follow_up(url, "new_openings", "now() + interval '2 days'")  # upcoming: reminded normally later
    with pytest.raises(Exception, match=REASON):
        _follow_up(url, "first_outreach", "now()")

    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and _has_column(url)
    stamped = dict(_sql(url, f"SELECT reason, reminded_at IS NOT NULL FROM recruiter_follow_ups WHERE company_id = '{COMPANY}'"))
    assert stamped == {"jd": True, "new_openings": False}
    _follow_up(url, "first_outreach", "now() + interval '1 day'")
    _follow_up(url, "cadence_step", "now() + interval '1 day'")

    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url) and not _has_column(url)
    rows = _sql(url, f"SELECT reason, count(*) FROM recruiter_follow_ups WHERE company_id = '{COMPANY}' GROUP BY reason ORDER BY reason")
    assert rows == [("jd", 1), ("new_openings", 3)]  # no row is lost
    with pytest.raises(Exception, match=REASON):
        _follow_up(url, "cadence_step", "now()")

    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and _has_column(url)
