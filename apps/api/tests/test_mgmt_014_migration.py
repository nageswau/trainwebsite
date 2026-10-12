"""mgmt-014 -- migration 0151_investments (spec §3). Round trip and the downgrade refusal run in a throwaway database built from scratch
(the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_mgmt_014_migration_0151", VERSIONS / "0151_investments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0150_management_ledger", "0151_investments"


def test_migration_chains_after_0150_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from typing import get_args

    from app.models import INVESTMENT_CHECKS, INVESTMENT_STATUSES, INVESTMENT_VERTICALS, Investment
    from app.schemas import InvestmentStatus, InvestmentVertical

    assert INVESTMENT_STATUSES == ("planned", "active", "completed", "cancelled")
    assert INVESTMENT_VERTICALS == ("abroad", "it", "recruitment", "school", "shared", "other")
    assert get_args(InvestmentStatus) == INVESTMENT_STATUSES and get_args(InvestmentVertical) == INVESTMENT_VERTICALS
    assert INVESTMENT_CHECKS == _migration.CHECKS
    assert {c.name for c in Investment.__table__.columns} == {
        "id", "code", "invested_on", "investor_kind", "investor_user_id", "amount", "purpose", "vertical", "expected_return",
        "actual_return", "status", "notes", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_table_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, indexes = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {i["name"] for i in inspect(sync).get_indexes("investments")}))
    assert "investments" in tables and "ix_investments_invested_on" in indexes


@pytest.fixture
def isolated_db():
    """A fresh database at 0150."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt014_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_investments_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'investments'")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'p@example.local', 'x', 'P', 'partner', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    insert = (
        "INSERT INTO investments (id, code, invested_on, investor_kind, investor_user_id, amount, purpose, vertical, status, "
        "created_by_user_id, updated_by_user_id) VALUES (gen_random_uuid(), :code, current_date, :kind, :investor, :amount, 'Ads', 'it', 'active', :p, :p)"
    )
    with pytest.raises(Exception, match="ck_investments_investor"):
        _sql(url, insert, {"code": "INV-X1", "kind": "partner", "investor": None, "amount": 10, "p": user})
    with pytest.raises(Exception, match="ck_investments_amount"):
        _sql(url, insert, {"code": "INV-X2", "kind": "company", "investor": None, "amount": 0, "p": user})
    _sql(url, insert, {"code": "INV-X3", "kind": "company", "investor": None, "amount": 10, "p": user})
    assert _sql(url, "SELECT nextval('investment_code_seq')")[0][0] >= 1
    with pytest.raises(Exception, match="investments exist"):
        command.downgrade(cfg, BASE)
