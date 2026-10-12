"""mgmt-005 -- automatic ledger sources (spec MA1-MA12; AC1-AC4): paid payments, paid agent commissions, approved BDM trip expenses,
rec-031 recruiter payments and upc-019 university commission receipts, read with `GET /management/ledger?include=auto`.

The stack DB is shared and never emptied, so every test works in its own random far-past month and finds its lines by id."""

import random
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.api.payments import PAID_STATUSES
from app.models import (
    AgentCommission,
    BdmProfile,
    BdmTrip,
    BdmTripExpense,
    Company,
    Job,
    LedgerEntry,
    OverseasApplication,
    Payment,
    Receipt,
    RecruiterInvoice,
    RecruiterPayment,
    UniversityCommissionReceipt,
    User,
)
from tests.agn014_helpers import mk_commission
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import as_user, category, create, post

LEDGER = "/api/v1/management/ledger"
IST = ZoneInfo("Asia/Kolkata")


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def ist(year: int, month: int, day: int = 15, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST).astimezone(UTC)


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def paid_payment(
    db,
    *,
    when: datetime | None,
    division: str = "it",
    reference_type: str = "enrollment_fee",
    amount: str = "32500.00",
    currency: str = "INR",
    status: str = "paid",
    installment_no: int | None = None,
    updated_at: datetime | None = None,
) -> Payment:
    """A payment with the receipt the paid move issues (`when`); `when=None` leaves it without a receipt (a seeded or admin-paid row)."""
    payer = await make_user(db, "it_student" if division == "it" else "overseas_student", division)
    payment = Payment(
        user_id=payer.id,
        division=division,
        reference_type=reference_type,
        amount=Decimal(amount),
        currency=currency,
        status=status,
        installment_no=installment_no,
        **({"updated_at": updated_at} if updated_at else {}),
    )
    db.add(payment)
    await db.flush()
    if when is not None:
        db.add(Receipt(payment_id=payment.id, user_id=payer.id, division=division, receipt_no=f"RCP-{tag()}", amount=payment.amount, currency=currency, file_url="receipts/test.pdf", issued_at=when))
    await db.commit()
    return payment


async def paid_commission(db, *, when: datetime, amount: float = 15000, currency: str = "INR", status: str = "paid") -> AgentCommission:
    agent = await make_user(db, "agent", "overseas")
    commission = await mk_commission(db, {}, agent=agent, amount=amount, currency=currency, status=status)
    commission.paid_at = when if status == "paid" else None
    await db.commit()
    return commission


async def trip_expense(db, *, on: date, bdm_type: str | None = "college", approval: str = "approved", amount: str = "1800.00") -> BdmTripExpense:
    bdm = await make_user(db, "bdm", "global")
    if bdm_type:
        manager = await make_user(db, "bdm_manager", "global")
        db.add(BdmProfile(user_id=bdm.id, bdm_type=bdm_type, employee_id=f"E-{tag()}", reporting_manager_user_id=manager.id))
    trip = BdmTrip(
        code=f"T{tag()}",
        bdm_user_id=bdm.id,
        travel_date=on,
        return_date=on,
        from_place="Hyderabad",
        to_place="Vijayawada",
        purpose="Visits",
        mode="train",
        estimated_cost=Decimal("2500"),
        approval_status=approval,
    )
    db.add(trip)
    await db.flush()
    expense = BdmTripExpense(trip_id=trip.id, category="travel", amount=Decimal(amount), expense_date=on, created_by_user_id=bdm.id)
    db.add(expense)
    await db.commit()
    return expense


async def recruiter_payment(db, *, on: date, amount: str = "50000.00") -> RecruiterPayment:
    creator = await make_user(db, "recruiter", "global")
    company = Company(name=f"Ledger Co {tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Java Dev {tag()}", location="Pune", description="", skills=[], status="requirement_received")
    db.add(job)
    await db.flush()
    invoice = RecruiterInvoice(job_id=job.id, invoice_number=f"INV-{tag()}", invoice_date=on, due_date=on, amount=Decimal("90000"), created_by_user_id=creator.id)
    db.add(invoice)
    await db.flush()
    payment = RecruiterPayment(invoice_id=invoice.id, received_on=on, amount=Decimal(amount), created_by_user_id=creator.id)
    db.add(payment)
    await db.commit()
    return payment


async def university_receipt(db, *, on: date, amount: str = "200000.00", currency: str = "INR") -> UniversityCommissionReceipt:
    commission = await paid_commission(db, when=ist(on.year, on.month), status="estimated")  # only for its university
    creator = await make_user(db, "partnership_head", "global")
    university_id = await db.scalar(select(OverseasApplication.university_id).where(OverseasApplication.id == commission.application_id))
    receipt = UniversityCommissionReceipt(university_id=university_id, amount=Decimal(amount), currency=currency, received_on=on, reference=f"UC-{tag()}", created_by_user_id=creator.id)
    db.add(receipt)
    await db.commit()
    return receipt


async def ledger(client, **params) -> dict:
    response = await client.get(LEDGER, params={"include": "auto", "limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


def lines_of(page: dict, row_id) -> list[dict]:
    return [item for item in page["items"] if item["id"] == str(row_id)]


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


# --- AC1-AC3 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_paid_it_enrolment_fee_appears_once_under_it_income(client, db_session):
    year, month = a_month()
    payment = await paid_payment(db_session, when=ist(year, month))
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    (line,) = lines_of(page, payment.id)
    assert line == {
        "source": "payment",
        "id": str(payment.id),
        "entry_date": f"{year:04d}-{month:02d}-15",
        "kind": "income",
        "vertical": "it",
        "category_label": "IT training",
        "amount": "32500.00",
        "currency": "INR",
        "description": line["description"],
        "counted": True,
    }
    assert line["description"].startswith("Enrolment fee · receipt RCP-")
    assert Decimal(page["totals"]["income"]) >= Decimal("32500.00")


@pytest.mark.asyncio
async def test_ac2_paid_agent_deposit_never_appears(client, db_session):
    year, month = a_month()
    deposit = await paid_payment(db_session, when=ist(year, month), division="overseas", reference_type="agent_deposit")
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    assert lines_of(page, deposit.id) == []
    assert all(item["id"] != str(deposit.id) for item in (await ledger(client))["items"])


@pytest.mark.asyncio
async def test_ac3_paid_agent_commission_is_an_expense_unpaid_is_not(client, db_session):
    year, month = a_month()
    paid = await paid_commission(db_session, when=ist(year, month))
    claimed = await paid_commission(db_session, when=ist(year, month), status="claimed")
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    (line,) = lines_of(page, paid.id)
    assert (line["source"], line["kind"], line["vertical"], line["category_label"], line["amount"]) == ("agent_commission", "expense", "abroad", "Agent commissions", "15000.00")
    assert line["description"].startswith("Agent commission · claim CLM-")
    assert lines_of(page, claimed.id) == []


# --- AC4: totals reconcile with the source tables ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac4_totals_reconcile_with_the_source_tables(client, db_session):
    year, month = a_month()
    first = date(year, month, 1)
    after = date(year + (month == 12), month % 12 + 1, 1)
    await paid_payment(db_session, when=ist(year, month, 3), amount="1000.50")
    await paid_payment(db_session, when=ist(year, month, 4), division="overseas", reference_type="service_fee", amount="2500.00")
    await paid_payment(db_session, when=ist(year, month, 5), division="overseas", reference_type="agent_deposit", amount="99999.00")
    await paid_payment(db_session, when=ist(year, month, 6), amount="400.00", currency="USD")
    await paid_commission(db_session, when=ist(year, month, 7), amount=700)
    await trip_expense(db_session, on=date(year, month, 8), amount="320.25")
    await recruiter_payment(db_session, on=date(year, month, 9), amount="5000.00")
    await university_receipt(db_session, on=date(year, month, 10), amount="8000.00")
    accountant = await as_user(client, db_session)
    cat = await category(client, kind="income", nature=None)
    entry = await create(client, cat["id"], kind="income", amount="111.00", entry_date=date(year, month, 11).isoformat(), vertical="other")
    assert (await post(client, entry["id"], "submit")).status_code == 200
    partner = await make_user(db_session, "partner", "global")
    await login(client, partner)
    assert (await post(client, entry["id"], "approve")).status_code == 200
    await login(client, accountant)

    def day(moment: datetime) -> date:
        return moment.astimezone(IST).date()

    income = expense = Decimal(0)
    for payment, issued in (await db_session.execute(select(Payment, Receipt.issued_at).outerjoin(Receipt, Receipt.payment_id == Payment.id))).all():
        if payment.status in PAID_STATUSES and payment.reference_type != "agent_deposit" and payment.currency == "INR" and first <= day(issued or payment.updated_at) < after:
            income += payment.amount
    for c in (await db_session.scalars(select(AgentCommission).where(AgentCommission.status == "paid"))).all():
        if c.currency == "INR" and c.amount > 0 and first <= day(c.paid_at or c.updated_at) < after:
            expense += c.amount
    trips = (
        select(BdmTripExpense.amount)
        .join(BdmTrip, BdmTrip.id == BdmTripExpense.trip_id)
        .where(BdmTrip.approval_status == "approved", BdmTripExpense.expense_date >= first, BdmTripExpense.expense_date < after)
    )
    expense += sum((await db_session.scalars(trips)).all(), Decimal(0))
    income += sum((await db_session.scalars(select(RecruiterPayment.amount).where(RecruiterPayment.received_on >= first, RecruiterPayment.received_on < after))).all(), Decimal(0))
    universities = select(UniversityCommissionReceipt.amount).where(
        UniversityCommissionReceipt.currency == "INR", UniversityCommissionReceipt.received_on >= first, UniversityCommissionReceipt.received_on < after
    )
    income += sum((await db_session.scalars(universities)).all(), Decimal(0))
    for e in (await db_session.scalars(select(LedgerEntry).where(LedgerEntry.status == "approved", LedgerEntry.entry_date >= first, LedgerEntry.entry_date < after))).all():
        signed = -e.amount if e.reversal_of_id else e.amount
        income, expense = (income + signed, expense) if e.kind == "income" else (income, expense + signed)

    totals = (await ledger(client, month=month_param(year, month)))["totals"]
    assert Decimal(totals["income"]) == income
    assert Decimal(totals["expense"]) == expense
    assert Decimal(totals["net"]) == income - expense
    assert {"currency": "USD", "kind": "income", "amount": "400.00", "count": 1} in totals["not_counted"]


# --- recognition, verticals, sources (MA2-MA7) --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_day_is_the_ist_receipt_day_and_falls_back_to_updated_at(client, db_session):
    year, month = a_month()
    late_night = await paid_payment(db_session, when=ist(year, month, 1, 0, 30))  # still the previous day in UTC
    no_receipt = await paid_payment(db_session, when=None, updated_at=ist(year, month, 3, 0, 15))
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    assert lines_of(page, late_night.id)[0]["entry_date"] == f"{year:04d}-{month:02d}-01"
    (fallback,) = lines_of(page, no_receipt.id)
    assert (fallback["entry_date"], fallback["description"]) == (f"{year:04d}-{month:02d}-03", "Enrolment fee")


@pytest.mark.asyncio
async def test_unpaid_payments_are_excluded_and_each_emi_instalment_counts_once(client, db_session):
    year, month = a_month()
    pending = await paid_payment(db_session, when=ist(year, month), status="pending")
    failed = await paid_payment(db_session, when=ist(year, month), status="failed")
    first = await paid_payment(db_session, when=ist(year, month, 2), reference_type="service_fee", installment_no=1, amount="5000.00")
    second = await paid_payment(db_session, when=ist(year, month, 20), reference_type="service_fee", installment_no=2, amount="5000.00", status="succeeded")
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    assert lines_of(page, pending.id) == lines_of(page, failed.id) == []
    assert [len(lines_of(page, p.id)) for p in (first, second)] == [1, 1]
    assert lines_of(page, first.id)[0]["description"].startswith("Service fee · instalment 1 · receipt RCP-")


@pytest.mark.asyncio
async def test_payment_verticals_by_division(client, db_session):
    year, month = a_month()
    overseas = await paid_payment(db_session, when=ist(year, month), division="overseas", reference_type="service_fee")
    other = await paid_payment(db_session, when=ist(year, month), division="global", reference_type="misc")
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    assert (lines_of(page, overseas.id)[0]["vertical"], lines_of(page, overseas.id)[0]["category_label"]) == ("abroad", "Abroad education")
    assert (lines_of(page, other.id)[0]["vertical"], lines_of(page, other.id)[0]["category_label"], lines_of(page, other.id)[0]["description"][:7]) == ("other", "Other", "Payment")


@pytest.mark.asyncio
async def test_trip_expenses_of_approved_trips_by_bdm_type(client, db_session):
    year, month = a_month()
    on = date(year, month, 12)
    college = await trip_expense(db_session, on=on, bdm_type="college")
    agent = await trip_expense(db_session, on=on, bdm_type="agent")
    school = await trip_expense(db_session, on=on, bdm_type="school")
    no_profile = await trip_expense(db_session, on=on, bdm_type=None)
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    assert [lines_of(page, e.id)[0]["vertical"] for e in (college, agent, school, no_profile)] == ["it", "abroad", "school", "shared"]
    line = lines_of(page, college.id)[0]
    assert (line["source"], line["kind"], line["category_label"], line["amount"], line["entry_date"]) == ("trip_expense", "expense", "Travel", "1800.00", on.isoformat())
    assert line["description"].startswith("Trip T") and line["description"].endswith(" · travel")


@pytest.mark.asyncio
async def test_recruiter_payment_and_university_receipt_are_income(client, db_session):
    year, month = a_month()
    on = date(year, month, 9)
    rec = await recruiter_payment(db_session, on=on)
    uni = await university_receipt(db_session, on=on)
    gbp = await university_receipt(db_session, on=on, amount="300.00", currency="GBP")
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    r, u, g = (lines_of(page, x.id)[0] for x in (rec, uni, gbp))
    assert (r["source"], r["kind"], r["vertical"], r["category_label"], r["amount"]) == ("recruiter_payment", "income", "recruitment", "Recruitment", "50000.00")
    assert r["description"].startswith("Invoice INV-") and r["description"].endswith(" payment")
    assert (u["source"], u["vertical"], u["category_label"], u["counted"]) == ("university_commission", "abroad", "University commission", True)
    assert (g["currency"], g["amount"], g["counted"]) == ("GBP", "300.00", False)
    assert {"currency": "GBP", "kind": "income", "amount": "300.00", "count": 1} in page["totals"]["not_counted"]


@pytest.mark.asyncio
async def test_descriptions_never_carry_person_names(client, db_session):
    year, month = a_month()
    payment = await paid_payment(db_session, when=ist(year, month))
    commission = await paid_commission(db_session, when=ist(year, month))
    names = {u.full_name for u in (await db_session.scalars(select(User).where(User.id.in_([payment.user_id, commission.agent_id])))).all()} | {"Report Student"}
    await as_user(client, db_session)
    page = await ledger(client, month=month_param(year, month))
    for row in (payment, commission):
        assert not any(name in lines_of(page, row.id)[0]["description"] for name in names)


# --- filters, paging, compatibility, access (MA9-MA12) ------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kind_and_vertical_filters_apply_category_and_status_drop_auto_lines(client, db_session):
    year, month = a_month()
    payment = await paid_payment(db_session, when=ist(year, month))
    commission = await paid_commission(db_session, when=ist(year, month))
    await as_user(client, db_session)
    m = month_param(year, month)
    assert lines_of(await ledger(client, month=m, kind="income"), payment.id) and not lines_of(await ledger(client, month=m, kind="income"), commission.id)
    assert lines_of(await ledger(client, month=m, vertical="abroad"), commission.id) and not lines_of(await ledger(client, month=m, vertical="abroad"), payment.id)
    cat = await category(client)
    for params in ({"category": cat["id"]}, {"status": "approved"}):
        page = await ledger(client, month=m, **params)
        assert all(item["source"] == "manual" for item in page["items"])
    other = month_param(year, month % 12 + 1) if month < 12 else month_param(year + 1, 1)
    assert not lines_of(await ledger(client, month=other), payment.id)


@pytest.mark.asyncio
async def test_paging_is_newest_first_across_sources(client, db_session):
    year, month = a_month()
    older = await paid_payment(db_session, when=ist(year, month, 2))
    newer = await trip_expense(db_session, on=date(year, month, 20))
    await as_user(client, db_session)
    m = month_param(year, month)
    first = (await client.get(LEDGER, params={"include": "auto", "month": m, "limit": 1})).json()
    second = (await client.get(LEDGER, params={"include": "auto", "month": m, "limit": 1, "offset": 1})).json()
    assert first["total"] == second["total"] >= 2
    assert first["items"][0]["entry_date"] >= second["items"][0]["entry_date"]
    ids = [item["id"] for item in (await ledger(client, month=m))["items"]]
    assert ids.index(str(newer.id)) < ids.index(str(older.id))


@pytest.mark.asyncio
async def test_without_include_the_mgmt_004_response_is_unchanged(client, db_session):
    year, month = a_month()
    payment = await paid_payment(db_session, when=ist(year, month))
    await as_user(client, db_session)
    page = (await client.get(LEDGER, params={"month": month_param(year, month)})).json()
    assert lines_of(page, payment.id) == []
    assert page["totals"] == {"income": "0.00", "expense": "0.00", "net": "0.00"}
    cat = await category(client)
    entry = await create(client, cat["id"])
    listed = (await client.get(LEDGER, params={"category": cat["id"]})).json()["items"]
    assert [item["source"] for item in listed] == ["manual"] and listed[0]["id"] == entry["id"] and listed[0]["can"]["edit"] is True


@pytest.mark.asyncio
async def test_unknown_include_is_422(client, db_session):
    await as_user(client, db_session)
    assert (await client.get(LEDGER, params={"include": "everything"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "overseas_admin", "bdm"])
async def test_only_the_finance_tier_reads_auto_lines(client, db_session, role):
    user = await make_user(db_session, role, "global" if role != "overseas_admin" else "overseas")
    await login(client, user)
    assert (await client.get(LEDGER, params={"include": "auto"})).status_code == 403


@pytest.mark.asyncio
async def test_partner_reads_auto_lines(client, db_session):
    year, month = a_month()
    payment = await paid_payment(db_session, when=ist(year, month))
    await login(client, await make_user(db_session, "partner", "global"))
    assert lines_of(await ledger(client, month=month_param(year, month)), payment.id)


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(LEDGER, params={"include": "auto"})).status_code == 401
