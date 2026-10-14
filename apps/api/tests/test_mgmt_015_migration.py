"""mgmt-015 -- migration 0158_partner_capital (spec §3). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

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

_spec = importlib.util.spec_from_file_location("_mgmt_015_migration_0158", VERSIONS / "0158_partner_capital.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0157_direct_tieups", "0158_partner_capital"


def test_migration_chains_after_0157_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from typing import get_args

    from app.models import CAPITAL_ENTRY_CHECKS, CAPITAL_ENTRY_KINDS, PARTNER_SHARE_CHECKS, PartnerCapitalEntry, PartnerShare
    from app.schemas import CapitalEntryKind

    assert CAPITAL_ENTRY_KINDS == ("initial", "additional", "withdrawal", "profit_distribution")
    assert get_args(CapitalEntryKind) == CAPITAL_ENTRY_KINDS
    assert CAPITAL_ENTRY_CHECKS == _migration.ENTRY_CHECKS and PARTNER_SHARE_CHECKS == _migration.SHARE_CHECKS
    assert {c.name for c in PartnerCapitalEntry.__table__.columns} == {
        "id", "partner_user_id", "entry_date", "kind", "amount", "note", "created_by_user_id", "created_at",
    }  # fmt: skip
    assert {c.name for c in PartnerShare.__table__.columns} == {
        "id", "partner_user_id", "effective_from", "share_pct", "commitment", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()

    def read(sync):
        found = inspect(sync)
        return set(found.get_table_names()), {i["name"] for i in found.get_indexes("partner_capital_entries")}, {u["name"] for u in found.get_unique_constraints("partner_shares")}

    tables, indexes, uniques = await conn.run_sync(read)
    assert {"partner_capital_entries", "partner_shares"} <= tables
    assert "ix_partner_capital_entries_partner_date" in indexes and "uq_partner_shares_partner_month" in uniques


@pytest.fixture
def isolated_db():
    """A fresh database at 0157."""
    cfg = _config()
    original = settings.database_url
    name = f"mgmt015_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_and_downgrade_refuses_while_capital_rows_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name IN ('partner_capital_entries', 'partner_shares')")
    command.upgrade(cfg, HEAD)
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (gen_random_uuid(), 'p@example.local', 'x', 'P', 'partner', 'global', true, true, 'en-GB', '{}') RETURNING id",
    )[0][0]
    entry = (
        "INSERT INTO partner_capital_entries (id, partner_user_id, entry_date, kind, amount, created_by_user_id) "
        "VALUES (gen_random_uuid(), :p, current_date, :kind, :amount, :p)"
    )
    with pytest.raises(Exception, match="ck_partner_capital_entries_kind"):
        _sql(url, entry, {"p": user, "kind": "bonus", "amount": 10})
    with pytest.raises(Exception, match="ck_partner_capital_entries_amount"):
        _sql(url, entry, {"p": user, "kind": "initial", "amount": 0})
    share = (
        "INSERT INTO partner_shares (id, partner_user_id, effective_from, share_pct, commitment, created_by_user_id, updated_by_user_id) "
        "VALUES (gen_random_uuid(), :p, :month, :pct, :commitment, :p, :p)"
    )
    with pytest.raises(Exception, match="ck_partner_shares_month"):
        _sql(url, share, {"p": user, "month": date(2026, 4, 2), "pct": 50, "commitment": None})
    with pytest.raises(Exception, match="ck_partner_shares_share_pct"):
        _sql(url, share, {"p": user, "month": date(2026, 4, 1), "pct": 100.01, "commitment": None})
    with pytest.raises(Exception, match="ck_partner_shares_commitment"):
        _sql(url, share, {"p": user, "month": date(2026, 4, 1), "pct": 50, "commitment": -1})
    _sql(url, share, {"p": user, "month": date(2026, 4, 1), "pct": 50, "commitment": 1000})
    with pytest.raises(Exception, match="uq_partner_shares_partner_month"):
        _sql(url, share, {"p": user, "month": date(2026, 4, 1), "pct": 40, "commitment": None})
    with pytest.raises(Exception, match="capital records exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM partner_shares")
    _sql(url, entry, {"p": user, "kind": "initial", "amount": 10})
    with pytest.raises(Exception, match="capital records exist"):
        command.downgrade(cfg, BASE)
