"""mgmt-010 -- the expense dashboard (spec ME1-ME10; AC: the total = the sum of the heads, annual = the sum of the months), read with
`GET /management/expenses?month=YYYY-MM`.

The stack DB is shared and never emptied, so each test works in a random far-past month and compares the dashboard before and after
it adds its own money (deltas), never absolute figures."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import TODAY, as_user, category, create, post
from tests.test_mgmt_005_auto_lines import ist, paid_commission, paid_payment, trip_expense

EXPENSES = "/api/v1/management/expenses"
LEDGER = "/api/v1/management/ledger"
HEADS = ["rent", "salaries", "marketing", "travel", "trainers", "commissions", "technology", "other"]


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


async def dashboard(client, month: str | None = None) -> dict:
    response = await client.get(EXPENSES, params={"month": month} if month else None)
    assert response.status_code == 200, response.text
    return response.json()


def head(data: dict, key: str) -> tuple[Decimal, Decimal]:
    (row,) = [g for g in data["groups"] if g["key"] == key]
    return Decimal(row["month"]), Decimal(row["year"])


def delta(before: dict, after: dict, key: str) -> tuple[Decimal, Decimal]:
    (bm, by), (am, ay) = head(before, key), head(after, key)
    return am - bm, ay - by


def not_counted(data: dict, currency: str) -> tuple[Decimal, int]:
    rows = [(Decimal(n["amount"]), n["count"]) for n in data["not_counted"] if n["currency"] == currency]
    return rows[0] if rows else (Decimal(0), 0)


async def seeded(client, name: str) -> str:
    items = (await client.get(f"{LEDGER}/categories")).json()["items"]
    (found,) = [c["id"] for c in items if c["kind"] == "expense" and c["name"] == name]
    return found


async def approved_expense(client, db, name: str, on: date, amount: str = "1000.00", category_id: str | None = None) -> dict:
    """An accountant's expense in the seeded category `name` (or `category_id`), approved by a partner. Leaves the partner signed in."""
    await as_user(client, db)
    entry = await create(client, category_id or await seeded(client, name), entry_date=on.isoformat(), amount=amount)
    assert (await post(client, entry["id"], "submit")).status_code == 200
    await as_user(client, db, "partner")
    assert (await post(client, entry["id"], "approve")).status_code == 200
    return entry


# --- access (ME10) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_reads_the_dashboard(client, db_session, role):
    await as_user(client, db_session, role)
    data = await dashboard(client)
    assert [g["key"] for g in data["groups"]] == HEADS
    assert [g["label"] for g in data["groups"]] == ["Rent", "Salaries", "Marketing", "Travel", "Trainers", "Commissions", "Technology", "Other"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,division,detail", [("super_admin", "global", "Finance access required"), ("it_admin", "it", "Management access required"), ("student", "it", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(EXPENSES)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(EXPENSES)).status_code == 401


# --- period and validation (ME3, ME4, ME9) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_month_is_the_current_ist_month(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client)
    assert data["month"] == TODAY.strftime("%Y-%m")


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-13", "abc", "1999-12", "2024-1"])
async def test_bad_months_are_422(client, db_session, month):
    await as_user(client, db_session)
    assert (await client.get(EXPENSES, params={"month": month})).status_code == 422


@pytest.mark.asyncio
async def test_a_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    nxt = (TODAY.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
    response = await client.get(EXPENSES, params={"month": nxt})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose this month or an earlier one"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "month,start,label,months",
    [
        ("2024-06", "2024-04-01", "2024-25", ["2024-04", "2024-05", "2024-06"]),
        ("2024-04", "2024-04-01", "2024-25", ["2024-04"]),
        ("2025-03", "2024-04-01", "2024-25", [f"2024-{m:02d}" for m in range(4, 13)] + ["2025-01", "2025-02", "2025-03"]),
        ("2025-01", "2024-04-01", "2024-25", [f"2024-{m:02d}" for m in range(4, 13)] + ["2025-01"]),
    ],
)
async def test_the_year_is_the_indian_financial_year_to_date(client, db_session, month, start, label, months):
    await as_user(client, db_session)
    data = await dashboard(client, month)
    assert (data["month"], data["year_start"], data["year_label"]) == (month, start, label)
    assert [m["month"] for m in data["months"]] == months


# --- figures (ME1, ME2, ME5) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_approved_rent_expense_counts_under_rent_for_the_month_and_year(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await approved_expense(client, db_session, "Office rent", date(year, month, 10), "120000.00")
    after = await dashboard(client, month_param(year, month))
    assert delta(before, after, "rent") == (Decimal("120000.00"), Decimal("120000.00"))
    assert Decimal(after["totals"]["month"]) - Decimal(before["totals"]["month"]) == Decimal("120000.00")
    assert any(c["label"] == "Office rent" and c["group"] == "rent" for c in after["categories"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,key",
    [
        ("Salaries", "salaries"),
        ("Marketing", "marketing"),
        ("Travel", "travel"),
        ("Trainer payments", "trainers"),
        ("Agent commissions", "commissions"),
        ("Internet", "technology"),
        ("Software", "technology"),
        ("Insurance", "other"),
        ("Events", "other"),
    ],
)
async def test_each_seeded_category_lands_in_its_head(client, db_session, name, key):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await approved_expense(client, db_session, name, date(year, month, 5), "250.00")
    after = await dashboard(client, month_param(year, month))
    assert delta(before, after, key) == (Decimal("250.00"), Decimal("250.00"))


@pytest.mark.asyncio
async def test_a_custom_category_counts_under_other(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    custom = await category(client)
    await approved_expense(client, db_session, "", date(year, month, 5), "75.50", category_id=custom["id"])
    after = await dashboard(client, month_param(year, month))
    assert delta(before, after, "other") == (Decimal("75.50"), Decimal("75.50"))
    assert any(c["label"] == custom["name"] and c["group"] == "other" for c in after["categories"])


@pytest.mark.asyncio
async def test_unapproved_entries_and_income_never_count(client, db_session):
    year, month = a_month()
    on = date(year, month, 12)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    rent = await seeded(client, "Office rent")
    await create(client, rent, entry_date=on.isoformat())  # draft
    submitted = await create(client, rent, entry_date=on.isoformat())
    await post(client, submitted["id"], "submit")
    rejected = await create(client, rent, entry_date=on.isoformat())
    await post(client, rejected["id"], "submit")
    income = await category(client, kind="income")
    paid_in = await create(client, income["id"], kind="income", entry_date=on.isoformat())
    await post(client, paid_in["id"], "submit")
    await as_user(client, db_session, "partner")
    await post(client, rejected["id"], "reject", reason="Wrong month")
    await post(client, paid_in["id"], "approve")
    await paid_payment(db_session, when=ist(year, month, 12))  # automatic income
    after = await dashboard(client, month_param(year, month))
    assert after["totals"] == before["totals"]


@pytest.mark.asyncio
async def test_a_reversal_nets_the_expense_out(client, db_session):
    month = TODAY.strftime("%Y-%m")  # a reversal is dated today (ML11)
    await as_user(client, db_session)
    before = await dashboard(client, month)
    entry = await approved_expense(client, db_session, "Software", TODAY, "999.00")
    partner = await login_back(client, db_session)
    reversal = (await post(client, entry["id"], "reverse", reason="Duplicate")).json()
    await login(client, partner)
    assert (await post(client, reversal["id"], "approve")).status_code == 200
    after = await dashboard(client, month)
    assert delta(before, after, "technology") == (Decimal("0.00"), Decimal("0.00"))


@pytest.mark.asyncio
async def test_a_category_that_nets_to_zero_is_not_listed(client, db_session):
    """Browser QA-01: a category whose only expense was reversed adds a ₹0.00 / ₹0.00 row that says nothing."""
    month = TODAY.strftime("%Y-%m")
    await as_user(client, db_session)
    custom = await category(client)
    entry = await approved_expense(client, db_session, "", TODAY, "40.00", category_id=custom["id"])
    partner = await login_back(client, db_session)
    reversal = (await post(client, entry["id"], "reverse", reason="Duplicate")).json()
    await login(client, partner)
    assert (await post(client, reversal["id"], "approve")).status_code == 200
    data = await dashboard(client, month)
    assert custom["name"] not in [c["label"] for c in data["categories"]]


async def login_back(client, db):
    """Switch to a fresh accountant and return a fresh partner (who did not create the reversal) to approve it."""
    partner = await make_user(db, "partner", "global")
    await as_user(client, db)
    return partner


@pytest.mark.asyncio
async def test_automatic_commissions_and_trip_expenses_count(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await paid_commission(db_session, when=ist(year, month, 8), amount=15000)
    await paid_commission(db_session, when=ist(year, month, 8), amount=500, status="approved")  # not paid
    await trip_expense(db_session, on=date(year, month, 9), amount="1800.00")
    await trip_expense(db_session, on=date(year, month, 9), approval="submitted", amount="700.00")  # trip not approved
    after = await dashboard(client, month_param(year, month))
    assert delta(before, after, "commissions") == (Decimal("15000.00"), Decimal("15000.00"))
    assert delta(before, after, "travel") == (Decimal("1800.00"), Decimal("1800.00"))


@pytest.mark.asyncio
async def test_other_currencies_are_not_counted_but_listed(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await paid_commission(db_session, when=ist(year, month, 8), amount=300, currency="GBP")
    after = await dashboard(client, month_param(year, month))
    assert after["totals"] == before["totals"]
    (ba, bc), (aa, ac) = not_counted(before, "GBP"), not_counted(after, "GBP")
    assert (aa - ba, ac - bc) == (Decimal("300.00"), 1)


@pytest.mark.asyncio
async def test_march_belongs_to_the_previous_financial_year(client, db_session):
    year = random.randint(2001, 2024)
    await as_user(client, db_session)
    march_before, april_before = await dashboard(client, month_param(year, 3)), await dashboard(client, month_param(year, 4))
    await approved_expense(client, db_session, "Utilities", date(year, 3, 31), "100.00")
    march_after, april_after = await dashboard(client, month_param(year, 3)), await dashboard(client, month_param(year, 4))
    assert delta(march_before, march_after, "other") == (Decimal("100.00"), Decimal("100.00"))
    assert delta(april_before, april_after, "other") == (Decimal("0.00"), Decimal("0.00"))


# --- the backlog's acceptance criteria -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_total_is_the_sum_of_the_heads_and_annual_is_the_sum_of_the_months(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    await approved_expense(client, db_session, "Office rent", date(year, month, 3), "10.00")
    await approved_expense(client, db_session, "Events", date(year, month, 4), "20.00")
    await paid_commission(db_session, when=ist(year, month, 5), amount=30)
    data = await dashboard(client, month_param(year, month))
    assert sum(Decimal(g["month"]) for g in data["groups"]) == Decimal(data["totals"]["month"])
    assert sum(Decimal(g["year"]) for g in data["groups"]) == Decimal(data["totals"]["year"])
    assert sum(Decimal(c["year"]) for c in data["categories"]) == Decimal(data["totals"]["year"])
    assert sum(Decimal(m["total"]) for m in data["months"]) == Decimal(data["totals"]["year"])
    assert Decimal(data["months"][-1]["total"]) == Decimal(data["totals"]["month"])
    if Decimal(data["totals"]["year"]) > 0:
        assert abs(sum(Decimal(str(g["share"])) for g in data["groups"]) - 100) <= Decimal("0.5")
