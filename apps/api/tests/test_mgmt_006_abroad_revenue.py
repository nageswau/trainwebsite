"""mgmt-006 -- the Abroad Education revenue dashboard (spec MR1-MR12; AC: every breakdown + unattributed = Abroad revenue, contribution
= revenue - expenses; an accountant sees no university commission), read with `GET /management/revenue/abroad?month=YYYY-MM`.

The stack DB is shared and never emptied, so each test works in a random far-past month and compares the dashboard before and after it
adds its own money (deltas). Countries, universities, intakes and agencies get unique names, so their rows are read absolutely."""

import random
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models import OverseasApplication, UniversityCommissionReceipt
from tests.agn001_helpers import mk_active_org
from tests.agn014_helpers import mk_commission
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import TODAY, as_user, category, create, post
from tests.test_mgmt_005_auto_lines import ist, paid_commission, paid_payment, trip_expense

REVENUE = "/api/v1/management/revenue/abroad"
KINDS = ["service_fees", "other_payments", "university_commission", "manual"]
BREAKDOWNS = ["country", "university", "intake", "agency"]
ZERO = (Decimal(0), Decimal(0))


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def dashboard(client, month: str | None = None) -> dict:
    response = await client.get(REVENUE, params={"month": month} if month else None)
    assert response.status_code == 200, response.text
    return response.json()


def pair(figure: dict) -> tuple[Decimal, Decimal]:
    return Decimal(figure["month"]), Decimal(figure["year"])


def kind(data: dict, key: str) -> tuple[Decimal, Decimal]:
    rows = [k for k in data["kinds"] if k["key"] == key]
    return pair(rows[0]) if rows else ZERO


def breakdown(data: dict, key: str) -> dict:
    (found,) = [b for b in data["breakdowns"] if b["key"] == key]
    return found


def row(data: dict, key: str, label: str) -> tuple[Decimal, Decimal]:
    rows = [r for r in breakdown(data, key)["rows"] if r["label"] == label]
    return pair(rows[0]) if rows else ZERO


def unattributed(data: dict, key: str) -> tuple[Decimal, Decimal]:
    return pair(breakdown(data, key)["unattributed"])


def expense(data: dict, label: str) -> tuple[Decimal, Decimal]:
    rows = [e for e in data["expenses"] if e["label"] == label]
    return pair(rows[0]) if rows else ZERO


def minus(a: tuple, b: tuple) -> tuple[Decimal, Decimal]:
    return a[0] - b[0], a[1] - b[1]


def assert_reconciles(data: dict) -> None:
    """AC: the kinds and every breakdown (+ unattributed) add up to revenue; contribution = revenue - expenses."""
    revenue = pair(data["revenue"])
    for period in (0, 1):
        assert sum((pair(k)[period] for k in data["kinds"]), Decimal(0)) == revenue[period]
        for b in data["breakdowns"]:
            assert sum((pair(r)[period] for r in b["rows"]), Decimal(0)) + pair(b["unattributed"])[period] == revenue[period], b["key"]
        assert sum((pair(e)[period] for e in data["expenses"]), Decimal(0)) == pair(data["expense_total"])[period]
        assert pair(data["contribution"])[period] == revenue[period] - pair(data["expense_total"])[period]


async def linked_application(db, *, agency: bool = True) -> tuple[OverseasApplication, dict]:
    """An application with unique country, university and intake names, owned by an agency's Master (or by no agency)."""
    names = {"country": f"Country {tag()}", "university": f"University {tag()}", "intake": f"Sep {tag()}"}
    ctx = await mk_active_org(db, name=f"Agency {tag()}")
    commission = await mk_commission(db, ctx, status="estimated", country_name=names["country"], university_name=names["university"], intake=names["intake"])
    application = await db.get(OverseasApplication, commission.application_id)
    if agency:
        names["agency"] = ctx["org"].name
    else:
        application.agent_id = None
        await db.commit()
    return application, names


async def overseas_payment(db, on: date, *, amount: str = "40000.00", reference_type: str = "service_fee", application=None, **kwargs):
    payment = await paid_payment(db, when=ist(on.year, on.month, on.day), division="overseas", reference_type=reference_type, amount=amount, **kwargs)
    if application is not None:
        payment.reference_id = application.id
        await db.commit()
    return payment


async def approved_entry(client, db, *, kind: str, vertical: str, on: date, amount: str, approve: bool = True) -> dict:
    """An accountant's entry in a new category of `kind`, submitted and (unless `approve=False`) approved by a partner."""
    await as_user(client, db)
    cat = await category(client, kind)
    entry = await create(client, cat["id"], kind=kind, vertical=vertical, entry_date=on.isoformat(), amount=amount, description="Abroad test entry")
    if approve:
        assert (await post(client, entry["id"], "submit")).status_code == 200
        await as_user(client, db, "partner")
        assert (await post(client, entry["id"], "approve")).status_code == 200
    return entry


# --- access (MR11) and the commission rule's helper (MR7) -----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_reads_the_dashboard(client, db_session, role):
    await as_user(client, db_session, role)
    data = await dashboard(client)
    assert [b["key"] for b in data["breakdowns"]] == BREAKDOWNS
    assert [b["label"] for b in data["breakdowns"]] == ["Country-wise", "University-wise", "Intake-wise", "Agency-wise"]
    assert data["commission_visible"] is (role == "partner")
    expected = KINDS if role == "partner" else [k for k in KINDS if k != "university_commission"]
    assert [k["key"] for k in data["kinds"]] == expected
    assert_reconciles(data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,division,detail", [("super_admin", "global", "Finance access required"), ("it_admin", "it", "Management access required"), ("student", "it", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(REVENUE)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(REVENUE)).status_code == 401


@pytest.mark.asyncio
async def test_only_partners_may_view_university_commission(db_session):
    from app.services.management_access import can_view_university_commission

    for role, allowed in (("partner", True), ("accountant", False), ("super_admin", False), ("partnership_head", False)):
        assert can_view_university_commission(await make_user(db_session, role, "global")) is allowed, role


# --- period and validation (MR1, MR10) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_month_is_the_current_ist_month(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client)
    assert data["month"] == TODAY.strftime("%Y-%m")


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-13", "abc", "1999-12", "2024-1"])
async def test_bad_months_are_422(client, db_session, month):
    await as_user(client, db_session)
    assert (await client.get(REVENUE, params={"month": month})).status_code == 422


@pytest.mark.asyncio
async def test_a_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    future = date(TODAY.year + 1, TODAY.month, 1)
    response = await client.get(REVENUE, params={"month": future.strftime("%Y-%m")})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose this month or an earlier one"


@pytest.mark.asyncio
async def test_financial_year_runs_april_to_the_selected_month(client, db_session):
    """MR1: a March payment is in the previous financial year; an April one counts for May's year but not May's month."""
    year = random.randint(2001, 2024)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, 5))
    await overseas_payment(db_session, date(year, 3, 20), amount="1111.00")
    await overseas_payment(db_session, date(year, 4, 2), amount="2222.00")
    after = await dashboard(client, month_param(year, 5))
    assert minus(pair(after["revenue"]), pair(before["revenue"])) == (Decimal("0.00"), Decimal("2222.00"))
    assert after["year_start"] == f"{year}-04-01"
    assert after["year_label"] == f"{year}-{(year + 1) % 100:02d}"


# --- revenue kinds and attribution (MR2-MR5) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_unlinked_service_fee_is_a_service_fee_and_unattributed(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await overseas_payment(db_session, date(year, month, 10), amount="25000.00")
    after = await dashboard(client, month_param(year, month))
    added = (Decimal("25000.00"), Decimal("25000.00"))
    assert minus(kind(after, "service_fees"), kind(before, "service_fees")) == added
    assert minus(pair(after["revenue"]), pair(before["revenue"])) == added
    for key in BREAKDOWNS:
        assert minus(unattributed(after, key), unattributed(before, key)) == added, key
    assert minus(pair(after["agent_generated"]), pair(before["agent_generated"])) == ZERO
    assert_reconciles(after)


@pytest.mark.asyncio
async def test_a_payment_linked_to_an_agency_application_is_attributed(client, db_session):
    year, month = a_month()
    application, names = await linked_application(db_session)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await overseas_payment(db_session, date(year, month, 12), amount="18000.00", reference_type="application_fee", application=application)
    after = await dashboard(client, month_param(year, month))
    added = (Decimal("18000.00"), Decimal("18000.00"))
    assert minus(kind(after, "other_payments"), kind(before, "other_payments")) == added
    for key in BREAKDOWNS:
        assert row(after, key, names[key]) == added, key
        assert unattributed(after, key) == unattributed(before, key), key
    assert minus(pair(after["agent_generated"]), pair(before["agent_generated"])) == added
    assert_reconciles(after)


@pytest.mark.asyncio
async def test_a_linked_application_without_an_agency_is_direct(client, db_session):
    year, month = a_month()
    application, names = await linked_application(db_session, agency=False)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await overseas_payment(db_session, date(year, month, 5), amount="7000.00", application=application)
    after = await dashboard(client, month_param(year, month))
    added = (Decimal("7000.00"), Decimal("7000.00"))
    assert row(after, "country", names["country"]) == added
    assert minus(row(after, "agency", "Direct (no agency)"), row(before, "agency", "Direct (no agency)")) == added
    assert minus(pair(after["agent_generated"]), pair(before["agent_generated"])) == ZERO
    assert_reconciles(after)


@pytest.mark.asyncio
async def test_deposits_it_unpaid_and_other_currencies_are_not_revenue(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    on = date(year, month, 8)
    await overseas_payment(db_session, on, reference_type="agent_deposit")
    await paid_payment(db_session, when=ist(year, month, 8), division="it", amount="9000.00")
    await overseas_payment(db_session, on, status="pending")
    await overseas_payment(db_session, on, amount="300.00", currency="GBP")
    after = await dashboard(client, month_param(year, month))
    assert pair(after["revenue"]) == pair(before["revenue"])
    gbp = [n for n in after["not_counted"] if n["currency"] == "GBP" and n["kind"] == "income"]
    old = [n for n in before["not_counted"] if n["currency"] == "GBP" and n["kind"] == "income"]
    assert Decimal(gbp[0]["amount"]) - (Decimal(old[0]["amount"]) if old else 0) == Decimal("300.00")


@pytest.mark.asyncio
async def test_approved_manual_abroad_income_is_recorded_in_the_ledger_kind(client, db_session):
    year, month = a_month()
    on = date(year, month, 3)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await approved_entry(client, db_session, kind="income", vertical="abroad", on=on, amount="5000.00")
    await approved_entry(client, db_session, kind="income", vertical="abroad", on=on, amount="999.00", approve=False)  # a draft
    await approved_entry(client, db_session, kind="income", vertical="it", on=on, amount="888.00")
    after = await dashboard(client, month_param(year, month))
    added = (Decimal("5000.00"), Decimal("5000.00"))
    assert minus(kind(after, "manual"), kind(before, "manual")) == added
    assert minus(unattributed(after, "agency"), unattributed(before, "agency")) == added
    assert minus(pair(after["revenue"]), pair(before["revenue"])) == added


# --- university commission (MR7) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_university_commission_is_shown_to_partners_only(client, db_session):
    year, month = a_month()
    await as_user(client, db_session, "partner")
    partner_before = await dashboard(client, month_param(year, month))
    await as_user(client, db_session, "accountant")
    accountant_before = await dashboard(client, month_param(year, month))
    application, names = await linked_application(db_session)
    creator = await make_user(db_session, "partnership_head", "global")
    db_session.add(
        UniversityCommissionReceipt(
            university_id=application.university_id,
            amount=Decimal("60000.00"),
            currency="INR",
            received_on=date(year, month, 20),
            reference=f"UC-{tag()}",
            application_ids=[str(application.id)],
            created_by_user_id=creator.id,
        )
    )
    await db_session.commit()
    added = (Decimal("60000.00"), Decimal("60000.00"))

    await as_user(client, db_session, "partner")
    partner = await dashboard(client, month_param(year, month))
    assert minus(kind(partner, "university_commission"), kind(partner_before, "university_commission")) == added
    assert row(partner, "university", names["university"]) == added
    assert row(partner, "country", names["country"]) == added
    assert minus(unattributed(partner, "intake"), unattributed(partner_before, "intake")) == added
    assert minus(unattributed(partner, "agency"), unattributed(partner_before, "agency")) == added
    assert minus(pair(partner["revenue"]), pair(partner_before["revenue"])) == added
    assert_reconciles(partner)

    await as_user(client, db_session, "accountant")
    accountant = await dashboard(client, month_param(year, month))
    assert accountant["commission_visible"] is False
    assert "university_commission" not in [k["key"] for k in accountant["kinds"]]
    assert pair(accountant["revenue"]) == pair(accountant_before["revenue"])
    assert row(accountant, "university", names["university"]) == ZERO
    assert pair(accountant["contribution"]) == pair(accountant_before["contribution"])
    assert_reconciles(accountant)


# --- expenses and contribution (MR6, MR8) ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_abroad_expenses_and_contribution(client, db_session):
    year, month = a_month()
    on = date(year, month, 14)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await paid_commission(db_session, when=ist(year, month, 14), amount=4000)
    await trip_expense(db_session, on=on, bdm_type="agent", amount="1500.00")
    await trip_expense(db_session, on=on, bdm_type="college", amount="700.00")  # IT, not Abroad
    await approved_entry(client, db_session, kind="expense", vertical="abroad", on=on, amount="2500.00")
    await approved_entry(client, db_session, kind="expense", vertical="shared", on=on, amount="10000.00")
    await overseas_payment(db_session, on, amount="30000.00")
    after = await dashboard(client, month_param(year, month))
    assert minus(expense(after, "Agent commissions"), expense(before, "Agent commissions")) == (Decimal("4000.00"), Decimal("4000.00"))
    assert minus(expense(after, "Travel"), expense(before, "Travel")) == (Decimal("1500.00"), Decimal("1500.00"))
    assert minus(pair(after["expense_total"]), pair(before["expense_total"])) == (Decimal("8000.00"), Decimal("8000.00"))
    assert minus(pair(after["shared_expenses"]), pair(before["shared_expenses"])) == (Decimal("10000.00"), Decimal("10000.00"))
    assert minus(pair(after["contribution"]), pair(before["contribution"])) == (Decimal("22000.00"), Decimal("22000.00"))
    assert_reconciles(after)


@pytest.mark.asyncio
async def test_a_period_with_no_expenses_has_contribution_equal_to_revenue(client, db_session):
    """Backlog edge case: a far-past month with nothing in it reads zero everywhere and still reconciles."""
    await as_user(client, db_session, "partner")
    data = await dashboard(client, "2000-01")
    assert_reconciles(data)
    assert pair(data["contribution"]) == minus(pair(data["revenue"]), pair(data["expense_total"]))
