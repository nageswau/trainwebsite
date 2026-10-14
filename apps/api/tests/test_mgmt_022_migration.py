"""mgmt-022 -- migration 0162_school_values (spec §4). Round trip and the downgrade refusal run in a throwaway database built from scratch
(the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_022_migration_0162", VERSIONS / "0162_school_values.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0161_management_meetings", "0162_school_values"
COLUMNS = (
    "SELECT table_name, column_name FROM information_schema.columns WHERE (table_name, column_name) IN (('schools', 'contract_value'), ('schools', 'renewal_value'), ('ledger_entries', 'school_id'))"
)


def test_migration_chains_after_0161_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import LEDGER_SCHOOL_CHECK, SCHOOL_VALUE_CHECKS, LedgerEntry, School

    assert SCHOOL_VALUE_CHECKS == _migration.VALUE_CHECKS and LEDGER_SCHOOL_CHECK == _migration.SCHOOL_CHECK
    assert {"contract_value", "renewal_value"} <= {c.name for c in School.__table__.columns}
    assert LedgerEntry.__table__.c.school_id.nullable


@pytest.fixture
def isolated_db():
    """A fresh database at 0161."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt022_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_round_trips_and_downgrade_refuses_while_values_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not _sql(url, COLUMNS)
    command.upgrade(cfg, HEAD)
    assert len(_sql(url, COLUMNS)) == 3
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'a@example.local', 'x', 'A', 'accountant', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    school = _sql(url, "INSERT INTO schools (id, name, created_by_user_id) VALUES (gen_random_uuid(), 'S', :u) RETURNING id", {"u": user})[0][0]
    with pytest.raises(Exception, match="ck_schools_contract_value"):
        _sql(url, "UPDATE schools SET contract_value = -1 WHERE id = :s", {"s": school})
    category = _sql(url, "SELECT id FROM ledger_categories WHERE kind = 'expense' LIMIT 1")[0][0]
    entry = (
        "INSERT INTO ledger_entries (id, entry_date, kind, category_id, amount, description, vertical, school_id, status, created_by_user_id, updated_by_user_id) "
        "VALUES (gen_random_uuid(), current_date, :kind, :c, 10, 'd', :vertical, :s, 'draft', :u, :u)"
    )
    with pytest.raises(Exception, match="ck_ledger_entries_school"):
        _sql(url, entry, {"kind": "expense", "c": category, "vertical": "school", "s": school, "u": user})
    _sql(url, "UPDATE schools SET renewal_value = 5 WHERE id = :s", {"s": school})
    with pytest.raises(Exception, match="school values"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE schools SET renewal_value = NULL")
    command.downgrade(cfg, BASE)
    assert not _sql(url, COLUMNS)
