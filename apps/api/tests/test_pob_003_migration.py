"""pob-003 -- migration 0283_company_business_context (DEC-SCOPE-406 D1-D6): the chain, the frozen document kinds, the backfill of
`last_contacted_at` and the round trip, in a throwaway database (the pob-001 0278 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import COMPANY_DOCUMENT_KINDS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_003_migration_0283", VERSIONS / "0283_company_business_context.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0283_company_business_context", "0278_commercial_grants"
TABLES = ("company_branches", "company_skill_demand", "company_documents")
COLUMNS = ("products_services", "departments_hiring", "hiring_locations", "target_roles", "last_contacted_at")


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_document_kinds_are_a_frozen_copy():
    assert (*_migration.DOCUMENT_KINDS, "nda") == COMPANY_DOCUMENT_KINDS  # pob-010 V7 added the NDA (migration 0300)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob003_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'companies'")}


def test_upgrade_backfills_last_contact_and_downgrade_removes_everything(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    user = _sql(url, "INSERT INTO users (id, email, full_name, role, division, password_hash, active, email_verified, locale, profile) VALUES "
                     "(gen_random_uuid(), 'pob003@x.test', 'P', 'placement_team', 'it', 'x', true, true, 'en-GB', '{}') RETURNING id")[0][0]  # fmt: skip
    called, silent = (
        _sql(url, f"INSERT INTO companies (id, name, partner_type, owner_type) VALUES (gen_random_uuid(), '{n}', 'recruiter', 'internal') RETURNING id")[0][0] for n in ("Called", "Silent")
    )
    contact = _sql(url, f"INSERT INTO company_contacts (id, company_id, name) VALUES (gen_random_uuid(), '{called}', 'C') RETURNING id")[0][0]
    _sql(url, f"INSERT INTO recruiter_calls (id, company_id, contact_id, caller_user_id, occurred_at, direction, outcome) VALUES "
              f"(gen_random_uuid(), '{called}', '{contact}', '{user}', '2026-01-02T10:00:00Z', 'outgoing', 'connected')")  # fmt: skip
    _sql(url, f"INSERT INTO recruiter_messages (id, company_id, contact_id, sender_user_id, channel, body, sent_at) VALUES "
              f"(gen_random_uuid(), '{called}', '{contact}', '{user}', 'whatsapp', 'Hi', '2026-01-05T10:00:00Z')")  # fmt: skip
    command.upgrade(cfg, HEAD)
    assert set(TABLES) <= _tables(url) and set(COLUMNS) <= _columns(url)
    rows = dict(_sql(url, f"SELECT id, last_contacted_at FROM companies WHERE id IN ('{called}', '{silent}')"))
    assert rows[silent] is None and rows[called].isoformat().startswith("2026-01-05T10:00:00")
    command.downgrade(cfg, BASE)
    assert not set(TABLES) & _tables(url) and not set(COLUMNS) & _columns(url)
    command.upgrade(cfg, HEAD)
