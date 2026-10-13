"""mgmt-009 -- the company profitability dashboard, a P&L per vertical (spec PL1-PL12; AC: the total row = the sum of the rows,
contribution = revenue - expenses), read with `GET /management/pnl?month=YYYY-MM&period=month|quarter|year`.

The stack DB is shared and never emptied, so each test works in a random far-past month and compares the P&L before and after it
adds its own money (deltas)."""

from datetime import date
from decimal import Decimal

import pytest

from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import as_user, category, create, post
from tests.test_mgmt_005_auto_lines import a_month, ist, month_param, paid_commission, paid_payment, recruiter_payment, trip_expense, university_receipt

PNL = "/api/v1/management/pnl"
ROWS = ["abroad", "it", "recruitment", "school", "other", "shared"]
LABELS = ["Abroad Education", "IT Training", "Recruitment", "School projects", "Other", "Shared (company-wide, not allocated)"]
FIGURES = ("revenue", "expenses", "contribution")


async def pnl(client, month: str | None = None, period: str | None = None) -> dict:
    params = {**({"month": month} if month else {}), **({"period": period} if period else {})}
    response = await client.get(PNL, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def row(data: dict, key: str) -> dict:
    (found,) = [r for r in data["rows"] if r["key"] == key]
    return {f: Decimal(found[f]) for f in FIGURES}


def delta(after: dict, before: dict, key: str) -> tuple[Decimal, Decimal, Decimal]:
    a, b = row(after, key), row(before, key)
    return tuple(a[f] - b[f] for f in FIGURES)  # type: ignore[return-value]


def assert_reconciles(data: dict) -> None:
    """AC: the total row is the sum of the rows; contribution = revenue - expenses, for every row and the total."""
    for f in FIGURES:
        assert sum((Decimal(r[f]) for r in data["rows"]), Decimal(0)) == Decimal(data["total"][f]), f
    for figures in [*data["rows"], data["total"]]:
        assert Decimal(figures["contribution"]) == Decimal(figures["revenue"]) - Decimal(figures["expenses"])


async def approved_entry(client, db, *, kind: str, vertical: str, on: date, amount: str, approve: bool = True) -> dict:
    """An accountant's entry, submitted and (unless `approve=False`) approved by a partner; leaves an accountant signed in."""
    await as_user(client, db)
    cat = await category(client, kind)
    entry = await create(client, cat["id"], kind=kind, vertical=vertical, entry_date=on.isoformat(), amount=amount, description="P&L test entry")
    if approve:
        assert (await post(client, entry["id"], "submit")).status_code == 200
        await as_user(client, db, "partner")
        assert (await post(client, entry["id"], "approve")).status_code == 200
        await as_user(client, db)
    return entry


# --- access (PL10) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_reads_six_rows_and_a_reconciled_total(client, db_session, role):
    await as_user(client, db_session, role)
    data = await pnl(client)
    assert [r["key"] for r in data["rows"]] == ROWS
    assert [r["label"] for r in data["rows"]] == LABELS
    assert data["commission_visible"] is (role == "partner")
    assert data["period"] == "month"
    assert_reconciles(data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,division,detail", [("super_admin", "global", "Finance access required"), ("it_admin", "it", "Management access required"), ("student", "it", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(PNL)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(PNL)).status_code == 401


# --- period and validation (PL1) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"month": "2026-13"}, {"month": "26-01"}, {"month": "1999-12"}, {"period": "week"}, {"period": ""}])
async def test_bad_month_or_period_is_422(client, db_session, params):
    await as_user(client, db_session)
    assert (await client.get(PNL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_a_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    response = await client.get(PNL, params={"month": "2999-01"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose this month or an earlier one"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "month,period,start,end,label",
    [
        ("2024-05", "month", "2024-05-01", "2024-05-31", "May 2024"),
        ("2024-05", "quarter", "2024-04-01", "2024-05-31", "Q1 (April–June) of 2024-25 to date"),
        ("2024-12", "quarter", "2024-10-01", "2024-12-31", "Q3 (October–December) of 2024-25 to date"),
        ("2025-02", "quarter", "2025-01-01", "2025-02-28", "Q4 (January–March) of 2024-25 to date"),
        ("2025-02", "year", "2024-04-01", "2025-02-28", "Financial year 2024-25 to date"),
    ],
)
async def test_the_period_runs_from_its_start_to_the_end_of_the_month(client, db_session, month, period, start, end, label):
    await as_user(client, db_session)
    data = await pnl(client, month, period)
    assert (data["month"], data["period"], data["start"], data["end"], data["label"]) == (month, period, start, end, label)


@pytest.mark.asyncio
async def test_quarter_and_year_count_earlier_months_the_month_does_not(client, db_session):
    year, _ = a_month()
    feb = month_param(year, 2)
    await as_user(client, db_session)
    before = {p: await pnl(client, feb, p) for p in ("month", "quarter", "year")}
    await approved_entry(client, db_session, kind="income", vertical="it", on=date(year, 1, 10), amount="1000.00")  # Q4 (Jan-Mar)
    await approved_entry(client, db_session, kind="income", vertical="it", on=date(year - 1, 12, 10), amount="200.00")  # Q3
    await approved_entry(client, db_session, kind="income", vertical="it", on=date(year, 2, 3), amount="30.00")
    after = {p: await pnl(client, feb, p) for p in ("month", "quarter", "year")}
    assert delta(after["month"], before["month"], "it")[0] == Decimal("30.00")
    assert delta(after["quarter"], before["quarter"], "it")[0] == Decimal("1030.00")
    assert delta(after["year"], before["year"], "it")[0] == Decimal("1230.00")


# --- rows (PL2-PL6) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_each_vertical_gets_its_own_income_and_expenses(client, db_session):
    year, month = a_month()
    on, m = date(year, month, 12), month_param(year, month)
    await as_user(client, db_session)
    before = await pnl(client, m)
    await paid_payment(db_session, when=ist(year, month, 12), division="overseas", reference_type="service_fee", amount="40000.00")
    await paid_commission(db_session, when=ist(year, month, 13), amount=4000)  # an Abroad expense
    await paid_payment(db_session, when=ist(year, month, 12), division="it", amount="25000.00")
    await trip_expense(db_session, on=on, bdm_type="college", amount="700.00")  # an IT expense
    await recruiter_payment(db_session, on=on, amount="50000.00")
    await trip_expense(db_session, on=on, bdm_type="school", amount="300.00")
    await approved_entry(client, db_session, kind="income", vertical="other", on=on, amount="900.00")
    await approved_entry(client, db_session, kind="expense", vertical="shared", on=on, amount="120000.00")  # rent, not allocated (PL4)
    after = await pnl(client, m)
    assert delta(after, before, "abroad") == (Decimal("40000.00"), Decimal("4000.00"), Decimal("36000.00"))
    assert delta(after, before, "it") == (Decimal("25000.00"), Decimal("700.00"), Decimal("24300.00"))
    assert delta(after, before, "recruitment") == (Decimal("50000.00"), Decimal(0), Decimal("50000.00"))
    assert delta(after, before, "school") == (Decimal(0), Decimal("300.00"), Decimal("-300.00"))
    assert delta(after, before, "other") == (Decimal("900.00"), Decimal(0), Decimal("900.00"))
    assert delta(after, before, "shared") == (Decimal(0), Decimal("120000.00"), Decimal("-120000.00"))
    total = {f: Decimal(after["total"][f]) - Decimal(before["total"][f]) for f in FIGURES}
    assert total == {"revenue": Decimal("115900.00"), "expenses": Decimal("125000.00"), "contribution": Decimal("-9100.00")}
    assert_reconciles(after)


@pytest.mark.asyncio
async def test_unapproved_entries_and_other_currencies_are_not_counted(client, db_session):
    year, month = a_month()
    on, m = date(year, month, 9), month_param(year, month)
    await as_user(client, db_session)
    before = await pnl(client, m)
    await approved_entry(client, db_session, kind="expense", vertical="it", on=on, amount="5000.00", approve=False)
    await paid_payment(db_session, when=ist(year, month, 9), division="it", amount="700.00", currency="USD")
    after = await pnl(client, m)
    assert delta(after, before, "it") == (Decimal(0), Decimal(0), Decimal(0))
    usd = [n for n in after["not_counted"] if n["currency"] == "USD" and n["kind"] == "income"]
    assert usd and Decimal(usd[0]["amount"]) >= Decimal("700.00")


@pytest.mark.asyncio
async def test_margin_is_contribution_over_revenue_or_none(client, db_session):
    year, month = a_month()
    on, m = date(year, month, 5), month_param(year, month)
    await approved_entry(client, db_session, kind="income", vertical="school", on=on, amount="1000.00")
    data = await pnl(client, m)
    for figures in [*data["rows"], data["total"]]:
        revenue = Decimal(figures["revenue"])
        if revenue > 0:
            assert figures["margin"] == round(float(Decimal(figures["contribution"]) / revenue * 100), 1)
        else:
            assert figures["margin"] is None


# --- university commission (PL7) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_university_commission_counts_for_partners_only(client, db_session):
    year, month = a_month()
    m = month_param(year, month)
    await as_user(client, db_session, "partner")
    partner_before = await pnl(client, m)
    await as_user(client, db_session, "accountant")
    accountant_before = await pnl(client, m)
    await university_receipt(db_session, on=date(year, month, 20), amount="60000.00")
    await university_receipt(db_session, on=date(year, month, 21), amount="500.00", currency="GBP")

    await as_user(client, db_session, "partner")
    partner = await pnl(client, m)
    assert delta(partner, partner_before, "abroad")[0] == Decimal("60000.00")
    assert any(n["currency"] == "GBP" for n in partner["not_counted"])
    assert_reconciles(partner)

    await as_user(client, db_session, "accountant")
    accountant = await pnl(client, m)
    assert accountant["commission_visible"] is False
    assert delta(accountant, accountant_before, "abroad") == (Decimal(0), Decimal(0), Decimal(0))
    assert accountant["total"] == accountant_before["total"]
    assert accountant["not_counted"] == accountant_before["not_counted"]
    assert_reconciles(accountant)
