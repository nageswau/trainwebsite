"""AGN-011 -- migration 0063_application_deposits (spec §3): one new table, its checks and the one-deposit-per-application rule.
Lite: chain, model, shared database; the full round-trip pattern (AGN-013) is not repeated here."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import ApplicationDeposit
from tests.agn011_helpers import deposit_world, mk_deposit, mk_deposit_payment

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_011_migration_0063", VERSIONS / "0063_application_deposits.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_chains_after_0062_and_is_the_single_head():
    assert _migration.revision == "0063_application_deposits"
    assert _migration.down_revision == "0062_agent_offer_details"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


@pytest.mark.asyncio
async def test_table_and_checks_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert "application_deposits" in tables
    checks = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_check_constraints("application_deposits")})
    assert set(_migration.CHECKS) <= checks
    uniques = await conn.run_sync(lambda sync: [u["column_names"] for u in inspect(sync).get_unique_constraints("application_deposits")])
    indexes = await conn.run_sync(lambda sync: [i["column_names"] for i in inspect(sync).get_indexes("application_deposits") if i["unique"]])
    assert ["application_id"] in uniques + indexes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"status": "maybe"},
        {"currency": "USD"},
        {"amount": None},
        {"amount": Decimal("0")},
        {"required": False},  # status pending but not required
        {"status": "paid"},  # paid without paid_payment_id
        {"refund_amount": Decimal("10")},  # refund columns all-or-nothing
    ],
)
async def test_checks_refuse_invalid_rows(db_session, fields):
    w = await deposit_world(db_session)
    row = ApplicationDeposit(application_id=w["app"].id, required=True, amount=Decimal("100"), currency="INR", status="pending", created_by_user_id=w["master"].id, updated_by_user_id=w["master"].id)
    for key, value in fields.items():
        setattr(row, key, value)
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_one_deposit_per_application_and_a_paid_row_is_valid(db_session):
    w = await deposit_world(db_session)
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    payment = await mk_deposit_payment(db_session, deposit, w["master"], status="paid")
    deposit.status, deposit.paid_payment_id, deposit.active_payment_id = "paid", payment.id, None
    from datetime import UTC, datetime

    deposit.paid_at = datetime.now(UTC)
    await db_session.commit()
    db_session.add(ApplicationDeposit(application_id=w["app"].id, required=False, currency="INR", status="not_required", created_by_user_id=w["master"].id, updated_by_user_id=w["master"].id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
