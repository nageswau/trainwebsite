"""mgmt-030 -- GET /management/health, the §30 business health score (EVID-017 §30, spec BH1-BH14; acceptance: the breakdown
recomputes the overall score). The stack DB is shared and never emptied, so money is asserted as deltas in random far-past months and
every factor's score is checked against the scale applied to the figures the API returned."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services import management_health as health
from app.services.bdm_appointments import IST
from app.services.management_expenses import next_month
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import as_user
from tests.test_mgmt_005_auto_lines import a_month, month_param
from tests.test_mgmt_009_pnl import approved_entry

URL = "/api/v1/management/health"
ALL = ["revenue", "profit", "cash_flow", "sales_pipeline", "student_growth", "enrollment", "agent_growth", "school_growth", "universities", "productivity", "marketing_roi", "expenses"]
OPERATIONAL = ["sales_pipeline", "student_growth", "enrollment", "agent_growth", "school_growth", "universities"]


async def read(client, **params) -> dict:
    response = await client.get(URL, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def factor(body: dict, key: str) -> dict:
    (found,) = [f for f in body["factors"] if f["key"] == key]
    return found


def assert_recomputes(body: dict) -> None:
    """AC: the points of the available factors add up to the overall score; every score sits in its RAG band."""
    available = [f for f in body["factors"] if f["score"] is not None]
    if body["score"] is None:
        assert available == [] and body["rag"] is None
        return
    assert sum(f["points"] for f in available) == body["score"]
    assert body["rag"] == health.rag(body["score"])
    for f in body["factors"]:
        assert (f["points"] is None) is (f["score"] is None)
        assert f["rag"] == (health.rag(f["score"]) if f["score"] is not None else None)
        assert (f["note"] is None) is (f["score"] is not None)


# --- the scales and bands (BH5, BH9) ---------------------------------------------------------------------------------------------
def test_growth_scale():
    assert health.growth_score(Decimal(110), Decimal(100)) == (100, 10.0)
    assert health.growth_score(Decimal(100), Decimal(100)) == (50, 0.0)
    assert health.growth_score(Decimal(90), Decimal(100)) == (0, -10.0)
    assert health.growth_score(Decimal(104), Decimal(100)) == (70, 4.0)
    assert health.growth_score(Decimal(500), Decimal(100)) == (100, 400.0)  # clamped
    assert health.growth_score(Decimal(5), Decimal(0)) == (100, None)  # new this month
    assert health.growth_score(Decimal(0), Decimal(0)) is None  # no basis
    assert health.growth_score(Decimal(-50), Decimal(-100)) == (100, 50.0)  # a smaller overdraft is growth


def test_margin_roi_and_expense_scales():
    assert [health.margin_score(m) for m in (-30.0, -20.0, 0.0, 15.0, 30.0, 45.0)] == [0, 0, 40, 70, 100, 100]
    assert [health.roi_score(r) for r in (-150.0, -100.0, 0.0, 40.0, 100.0)] == [0, 0, 50, 70, 100]
    assert [health.expense_score(d) for d in (-20.0, -10.0, 0.0, 4.0, 10.0)] == [100, 100, 50, 30, 0]


def test_rag_bands():
    assert [health.rag(s) for s in (100, 70, 69, 40, 39, 0)] == ["green", "green", "amber", "amber", "red", "red"]


def test_weights_add_up_to_100_in_source_order():
    assert [f.key for f in health.FACTORS] == ALL
    assert sum(f.weight for f in health.FACTORS) == 100
    assert [f.key for f in health.FACTORS if f.key in health.OPERATIONAL_KEYS] == OPERATIONAL


# --- access (BH1) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "detail"), [("accountant", "global", "Operational access required"), ("it_admin", "it", "Management access required"), ("counselor", "overseas", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["1999-12", "2999-01", "2026-13", "May"])
async def test_a_month_out_of_range_is_422(client, db_session, month):
    await as_user(client, db_session, "partner")
    assert (await client.get(URL, params={"month": month})).status_code == 422


@pytest.mark.asyncio
async def test_the_partner_sees_twelve_factors_and_a_recomputed_score(client, db_session):
    await as_user(client, db_session, "partner")
    body = await read(client)
    assert body["scope"] == "business"
    assert [f["key"] for f in body["factors"]] == ALL
    assert {f["tier"] for f in body["factors"]} == {"finance", "operational"}
    assert_recomputes(body)


@pytest.mark.asyncio
async def test_super_admin_sees_only_the_operational_factors(client, db_session):
    await as_user(client, db_session, "super_admin")
    body = await read(client)
    assert body["scope"] == "operational"
    assert [f["key"] for f in body["factors"]] == OPERATIONAL
    assert all(f["tier"] == "operational" and f["unit"] == "count" for f in body["factors"])
    assert_recomputes(body)


# --- the period (BH2) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_default_is_the_last_complete_month(client, db_session):
    await as_user(client, db_session, "partner")
    body = await read(client)
    assert next_month(date.fromisoformat(body["month"] + "-01")).strftime("%Y-%m") == _ist_month()
    assert next_month(date.fromisoformat(body["previous_month"] + "-01")).strftime("%Y-%m") == body["month"]
    assert body["partial"] is False


@pytest.mark.asyncio
async def test_the_current_month_is_partial(client, db_session):
    await as_user(client, db_session, "partner")
    body = await read(client, month=_ist_month())
    assert body["partial"] is True


@pytest.mark.asyncio
async def test_a_month_before_any_data_has_no_score(client, db_session):
    await as_user(client, db_session, "partner")
    body = await read(client, month="2000-01")
    assert body["previous_month"] == "1999-12"
    assert body["score"] is None and body["rag"] is None
    assert all(f["score"] is None and f["note"] for f in body["factors"])


# --- the money factors (BH4/BH5) -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revenue_profit_and_expense_factors_follow_the_ledger(client, db_session):
    year, month = a_month()
    month_start = date(year, month, 1)
    earlier = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    await as_user(client, db_session, "partner")
    before = await read(client, month=month_param(year, month))

    await approved_entry(client, db_session, kind="income", vertical="it", on=earlier.replace(day=10), amount="100000.00")
    await approved_entry(client, db_session, kind="income", vertical="it", on=month_start.replace(day=10), amount="150000.00")
    await approved_entry(client, db_session, kind="expense", vertical="it", on=month_start.replace(day=12), amount="20000.00")
    await as_user(client, db_session, "partner")
    body = await read(client, month=month_param(year, month))

    revenue = factor(body, "revenue")
    assert Decimal(revenue["current"]) - Decimal(factor(before, "revenue")["current"] or 0) == Decimal("150000.00")
    assert Decimal(revenue["previous"]) - Decimal(factor(before, "revenue")["previous"] or 0) == Decimal("100000.00")
    assert revenue["unit"] == "inr" and revenue["tier"] == "finance"
    expected = health.growth_score(Decimal(revenue["current"]), Decimal(revenue["previous"]))
    assert expected is not None and (revenue["score"], revenue["change"]) == expected

    profit = factor(body, "profit")
    assert profit["unit"] == "percent" and profit["score"] == health.margin_score(float(profit["current"]))
    expenses = factor(body, "expenses")
    if expenses["score"] is not None:
        assert expenses["score"] == health.expense_score(expenses["change"])
    assert_recomputes(body)


@pytest.mark.asyncio
async def test_a_missing_balance_or_headcount_is_excluded_with_a_reason(client, db_session):
    await as_user(client, db_session, "partner")
    body = await read(client, month="2000-01")
    assert factor(body, "cash_flow")["note"] == "Cash/bank balance not entered for both months"
    assert factor(body, "productivity")["note"] == "Salary headcount not entered for both months"
    assert factor(body, "marketing_roi")["note"] == "No marketing spend tagged in the month"
    assert factor(body, "profit")["note"] == "No revenue in the month"


def _ist_month() -> str:
    return datetime.now(IST).strftime("%Y-%m")
