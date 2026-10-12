"""mgmt-013 -- migration 0155_finance_balances (spec §3). The chain, the model/migration match and the shared database's state; the round
trip runs in a throwaway database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_013_migration_0155", VERSIONS / "0155_finance_balances.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0154_salaries", "0155_finance_balances"


def test_migration_chains_after_0154_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import FINANCE_BALANCE_CHECKS, FinanceBalance

    assert FINANCE_BALANCE_CHECKS == _migration.CHECKS
    assert {c.name for c in FinanceBalance.__table__.columns} == {
        "id", "month", "cash_bank", "payables", "tax_liabilities", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert "finance_balances" in tables


@pytest.fixture
def isolated_db():
    """A fresh database at 0154."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt013_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_constraints_and_downgrade_refuses_with_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'finance_balances'")
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'a@example.local', 'x', 'A', 'accountant', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO finance_balances (id, month, cash_bank, payables, tax_liabilities, created_by_user_id, updated_by_user_id) "
        "VALUES (gen_random_uuid(), :month, :cash, :payables, :tax, :u, :u)"
    )
    with pytest.raises(Exception, match="ck_finance_balances_month"):
        _sql(url, insert, {"month": date(2026, 1, 2), "cash": 1, "payables": 1, "tax": 1, "u": user})
    with pytest.raises(Exception, match="ck_finance_balances_payables"):
        _sql(url, insert, {"month": date(2026, 1, 1), "cash": 1, "payables": -1, "tax": 1, "u": user})
    with pytest.raises(Exception, match="ck_finance_balances_tax"):
        _sql(url, insert, {"month": date(2026, 1, 1), "cash": 1, "payables": 1, "tax": -1, "u": user})
    _sql(url, insert, {"month": date(2026, 1, 1), "cash": -500, "payables": None, "tax": None, "u": user})  # an overdraft, nothing else entered
    with pytest.raises(Exception, match="uq_finance_balances_month"):
        _sql(url, insert, {"month": date(2026, 1, 1), "cash": 1, "payables": 1, "tax": 1, "u": user})
    with pytest.raises(Exception, match="finance balances exist"):
        command.downgrade(cfg, BASE)
