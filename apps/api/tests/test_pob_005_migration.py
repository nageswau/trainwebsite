"""pob-005 -- migration 0290_contact_status (DEC-SCOPE-411 D1-D7): the chain, the frozen catalogues, the status backfill from existing
activity and the round trip, in a throwaway database (the pob-003 0283 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import COMPANY_CONTACT_CHECKS, COMPANY_CONTACT_SOURCES, COMPANY_CONTACT_STATUSES, CompanyContact
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_005_migration_0290", VERSIONS / "0290_contact_status.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0290_contact_status", "0289_interview_results"
COLUMNS = ("is_decision_maker", "source", "verified_on", "status", "status_changed_at")


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_catalogues_and_checks_are_frozen_copies():
    assert _migration.STATUSES == COMPANY_CONTACT_STATUSES and _migration.SOURCES == COMPANY_CONTACT_SOURCES
    assert _migration.CHECKS == {k: v for k, v in COMPANY_CONTACT_CHECKS.items() if k in _migration.CHECKS}
    constraints = {c.name: str(c.sqltext) for c in CompanyContact.__table__.constraints if c.name in _migration.CHECKS}
    assert constraints == _migration.CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob005_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_backfills_status_and_downgrade_removes_everything(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # 0001 builds today's models, so drop what 0290 adds first: the guarded upgrade must add it back and backfill
    for column in COLUMNS:
        _sql(url, f"ALTER TABLE company_contacts DROP COLUMN IF EXISTS {column}")
    _sql(url, "ALTER TABLE recruiter_messages DROP COLUMN IF EXISTS replied_at")
    user = _sql(url, "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES "
                     "(gen_random_uuid(), 'pob005@x.test', 'P', 'placement_team', 'it', 'x', true, true, 'en-GB', '{}') RETURNING id")[0][0]  # fmt: skip
    company = _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type) VALUES (gen_random_uuid(), 'Pob005', 'recruiter', 'internal') RETURNING id")[0][0]
    quiet, messaged, called, met = (
        _sql(url, f"INSERT INTO company_contacts (id, company_id, name) VALUES (gen_random_uuid(), '{company}', '{n}') RETURNING id")[0][0]
        for n in ("Quiet", "Messaged", "Called", "Met")
    )
    _sql(url, f"INSERT INTO recruiter_messages (id, company_id, contact_id, sender_user_id, channel, body, sent_at) VALUES "
              f"(gen_random_uuid(), '{company}', '{messaged}', '{user}', 'whatsapp', 'Hi', now())")  # fmt: skip
    _sql(url, f"INSERT INTO recruiter_calls (id, company_id, contact_id, caller_user_id, occurred_at, direction, outcome) VALUES "
              f"(gen_random_uuid(), '{company}', '{called}', '{user}', now(), 'outgoing', 'connected')")  # fmt: skip
    _sql(url, f"INSERT INTO recruiter_meetings (id, meeting_code, company_id, contact_id, meeting_type, starts_at, mode, status, created_by_user_id) "
              f"VALUES (gen_random_uuid(), 'MTG-P005', '{company}', '{met}', 'contract_discussion', now(), 'Online', 'scheduled', '{user}')")  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert set(COLUMNS) <= _columns(url, "company_contacts") and "replied_at" in _columns(url, "recruiter_messages")
    rows = dict(_sql(url, f"SELECT id, status FROM company_contacts WHERE company_id = '{company}'"))
    assert rows == {quiet: "not_contacted", messaged: "contacted", called: "replied", met: "meeting_scheduled"}
    with pytest.raises(Exception, match="ck_company_contacts_status"):
        _sql(url, f"UPDATE company_contacts SET status = 'bogus' WHERE id = '{quiet}'")
    _sql(url, f"UPDATE company_contacts SET preferred_channel = 'linkedin' WHERE id = '{quiet}'")
    command.downgrade(cfg, BASE)
    assert not set(COLUMNS) & _columns(url, "company_contacts") and "replied_at" not in _columns(url, "recruiter_messages")
    assert _sql(url, f"SELECT preferred_channel FROM company_contacts WHERE id = '{quiet}'") == [(None,)]  # linkedin cleared for the old CHECK
    command.upgrade(cfg, HEAD)
