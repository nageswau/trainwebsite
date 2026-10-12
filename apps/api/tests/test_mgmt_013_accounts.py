"""mgmt-013 -- accounts dashboard (spec AD1-AD14; AC1 receivables reconcile with unpaid payments + outstanding external invoices, AC2
super_admin 403, edge: a month without balances shows "not entered").

The stack DB is shared and never emptied. Receivables are live (as of today), so each test reads them before and after adding its own
rows and asserts the difference; month figures use a random far-past month, also compared before and after."""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, Invoice, Job, LedgerCategory, LedgerEntry, Payment, RecruiterInvoice, RecruiterPayment, UniversityCommissionReceipt
from app.services import ledger, management_audit
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_005_auto_lines import trip_expense
from tests.upc019_helpers import agreement, enrolled, staff, term

ACCOUNTS = "/api/v1/management/accounts"
BALANCES = "/api/v1/management/accounts/balances"
TODAY = ledger.today()
D = Decimal


def tag() -> str:
    return uuid.uuid4().hex[:8]


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, number: int) -> str:
    return f"{year:04d}-{number:02d}"


async def as_user(client, db, role: str = "accountant"):
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def view(client, month: str | None = None) -> dict:
    response = await client.get(ACCOUNTS, params={"month": month} if month else {})
    assert response.status_code == 200, response.text
    return response.json()


def head(section: dict, key: str) -> D:
    return D(next(h for h in section["heads"] if h["key"] == key)["amount"])


def diff(before: dict, after: dict, *path: str) -> D:
    a, b = before, after
    for key in path:
        a, b = a[key], b[key]
    return D(b) - D(a)


# --- data builders ---------------------------------------------------------------------------------------------------------------
async def fee(db, amount: str, *, status: str = "pending", due: date | None = None, reference_type: str = "enrollment_fee", currency: str = "INR", invoice: bool = True) -> Payment:
    payer = await make_user(db, "it_student", "it")
    payment = Payment(user_id=payer.id, division="it", reference_type=reference_type, amount=D(amount), currency=currency, status=status, due_date=due)
    db.add(payment)
    await db.flush()
    if invoice:
        db.add(Invoice(payment_id=payment.id, user_id=payer.id, division="it", invoice_no=f"INV-T-{tag()}", amount=payment.amount, currency=currency, file_url="invoices/test.pdf"))
    await db.commit()
    return payment


async def recruiter_invoice(db, amount: str, *, received: str | None = None, due: date = TODAY, cancelled: bool = False) -> RecruiterInvoice:
    creator = await make_user(db, "recruiter", "global")
    company = Company(name=f"Accounts Co {tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Role {tag()}", location="Pune", description="", skills=[], status="requirement_received")
    db.add(job)
    await db.flush()
    invoice = RecruiterInvoice(job_id=job.id, invoice_number=f"INV-{tag()}", invoice_date=due - timedelta(days=30), due_date=due, amount=D(amount), created_by_user_id=creator.id)
    if cancelled:
        invoice.cancelled_at, invoice.cancelled_by_user_id, invoice.cancel_reason = ledger.now(), creator.id, "Raised in error"
    db.add(invoice)
    await db.flush()
    if received:
        db.add(RecruiterPayment(invoice_id=invoice.id, received_on=TODAY, amount=D(received), created_by_user_id=creator.id))
    await db.commit()
    return invoice


async def university_owed(db, *, expected: str, received: str | None = None, currency: str = "INR") -> None:
    """A fresh university with one enrolled application whose fixed term makes `expected` due, and optionally a receipt."""
    uni, by = await mk_university(db), await staff(db)
    await term(db, await agreement(db, uni, by), by, percent=None, fixed=expected, currency=currency)
    await enrolled(db, uni)
    if received:
        db.add(UniversityCommissionReceipt(university_id=uni.id, amount=D(received), currency=currency, received_on=TODAY, reference=f"UC-{tag()}", created_by_user_id=by.id))
        await db.commit()


async def entry(db, year: int, number: int, *, kind: str, category: str, amount: str, vertical: str = "shared", status: str = "approved") -> None:
    category_id = await db.scalar(select(LedgerCategory.id).where(LedgerCategory.kind == kind, LedgerCategory.name == category))
    author = await make_user(db, "accountant", "global")
    db.add(LedgerEntry(entry_date=date(year, number, 10), kind=kind, category_id=category_id, amount=D(amount), description="Test", vertical=vertical,
                       status=status, created_by_user_id=author.id, updated_by_user_id=author.id))  # fmt: skip
    await db.commit()


# --- AC1: receivables reconcile ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_receivables_move_by_exactly_the_unpaid_fees_and_outstanding_invoices(client, db_session):
    await as_user(client, db_session)
    before = await view(client)
    await fee(db_session, "10000", due=TODAY + timedelta(days=10))  # owed, not yet due
    await fee(db_session, "2500", due=TODAY - timedelta(days=1))  # past its due date
    await fee(db_session, "1000", status="overdue", invoice=False)  # marked overdue, no invoice on file
    await fee(db_session, "7000", status="paid")  # paid: not owed
    await fee(db_session, "99000", reference_type="agent_deposit")  # pass-through: never EduSphere's receivable
    await fee(db_session, "300", currency="USD")  # another currency: listed, not added
    await recruiter_invoice(db_session, "90000", received="50000", due=TODAY - timedelta(days=3))  # 40 000 outstanding, overdue
    await recruiter_invoice(db_session, "20000", due=TODAY + timedelta(days=5))  # 20 000 outstanding
    await recruiter_invoice(db_session, "5000", cancelled=True)  # cancelled: counts nowhere
    await recruiter_invoice(db_session, "8000", received="8000")  # fully paid
    await university_owed(db_session, expected="60000", received="15000")  # 45 000 outstanding
    await university_owed(db_session, expected="10000", received="12000")  # over-received: floors at 0, never offsets another university
    after = await view(client)

    assert diff(before, after, "receivables", "fees") == D("13500.00")
    assert diff(before, after, "receivables", "recruitment") == D("60000.00")
    assert diff(before, after, "receivables", "university") == D("45000.00")
    assert diff(before, after, "receivables", "total") == D("118500.00")
    assert diff(before, after, "receivables", "overdue") == D("43500.00")  # 2 500 + 1 000 fees + 40 000 recruitment
    usd = lambda out: sum((D(x["amount"]) for x in out["receivables"]["not_counted"] if x["currency"] == "USD"), D(0))  # noqa: E731
    assert usd(after) - usd(before) == D("300.00")
    r = after["receivables"]
    assert D(r["total"]) == D(r["fees"]) + D(r["recruitment"]) + D(r["university"])


@pytest.mark.asyncio
async def test_pending_invoices_count_fee_invoices_still_owed_and_open_recruitment_invoices(client, db_session):
    await as_user(client, db_session)
    before = (await view(client))["pending_invoices"]
    await fee(db_session, "4000")  # invoiced and unpaid
    await fee(db_session, "6000", status="paid")  # invoiced and paid
    await fee(db_session, "900", invoice=False)  # unpaid but never invoiced
    await recruiter_invoice(db_session, "30000", received="10000")
    await recruiter_invoice(db_session, "5000", cancelled=True)
    await university_owed(db_session, expected="1000")  # receipts, no invoice
    after = (await view(client))["pending_invoices"]
    assert after["count"] - before["count"] == 2
    assert D(after["amount"]) - D(before["amount"]) == D("24000.00")


# --- AC2: finance tier only -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "it_admin", "telecaller"])
async def test_ac2_only_the_finance_tier_reads_or_writes(client, db_session, role):
    await as_user(client, db_session, role)
    read = await client.get(ACCOUNTS)
    write = await client.put(BALANCES, params={"month": "2020-01"}, json={"cash_bank": "1", "payables": "1", "tax_liabilities": "1"})
    assert read.status_code == 403 and write.status_code == 403
    if role == "super_admin":
        assert read.json()["detail"] == "Finance access required"


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(ACCOUNTS)).status_code == 401


@pytest.mark.asyncio
async def test_a_partner_reads_and_writes(client, db_session):
    await as_user(client, db_session, "partner")
    month = month_param(*a_month())
    response = await client.put(BALANCES, params={"month": month}, json={"cash_bank": "100", "payables": None, "tax_liabilities": None})
    assert response.status_code == 200, response.text
    assert response.json()["balances"]["cash_bank"] == "100.00"


# --- income, expenses, profit -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_income_and_expense_heads_follow_the_section_22_mapping_and_add_up(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    await entry(db_session, year, number, kind="income", category="School projects", amount="40000", vertical="school")
    await entry(db_session, year, number, kind="income", category="Other", amount="3000", vertical="shared")  # shared income -> Other
    await entry(db_session, year, number, kind="income", category="IT training", amount="900", vertical="it", status="draft")  # not counted
    await entry(db_session, year, number, kind="expense", category="Office rent", amount="30000")
    await entry(db_session, year, number, kind="expense", category="Software", amount="5000")
    await entry(db_session, year, number, kind="expense", category="Internet", amount="1500")
    await entry(db_session, year, number, kind="expense", category="Events", amount="2000")
    await entry(db_session, year, number, kind="expense", category="Utilities", amount="700")
    await entry(db_session, year, number, kind="expense", category="Trainer payments", amount="12000")
    await trip_expense(db_session, on=date(year, number, 12), amount="1800.00")  # automatic "Travel" line
    after = await view(client, month)

    def moved(section: str, key: str) -> D:
        return head(after[section], key) - head(before[section], key)

    assert [h["key"] for h in after["income"]["heads"]] == ["abroad", "it", "recruitment", "school", "other"]
    assert [h["key"] for h in after["expenses"]["heads"]] == ["salaries", "rent", "marketing", "travel", "trainers", "commissions", "operations", "technology"]
    assert moved("income", "school") == D("40000.00") and moved("income", "other") == D("3000.00") and moved("income", "it") == 0
    assert moved("expenses", "rent") == D("30000.00")
    assert moved("expenses", "technology") == D("6500.00")
    assert moved("expenses", "marketing") == D("2000.00")
    assert moved("expenses", "operations") == D("700.00")
    assert moved("expenses", "trainers") == D("12000.00")
    assert moved("expenses", "travel") == D("1800.00")
    for section in ("income", "expenses"):
        assert sum((D(h["amount"]) for h in after[section]["heads"]), D(0)) == D(after[section]["total"])
    assert D(after["profit"]) == D(after["income"]["total"]) - D(after["expenses"]["total"])
    technology = next(h for h in after["expenses"]["heads"] if h["key"] == "technology")
    assert {p["label"] for p in technology["parts"]} >= {"Software", "Internet"}


def test_a_category_added_later_falls_into_operations_and_known_labels_ignore_case():
    from app.services.accounts import expense_head

    assert expense_head("Office Rent") == "rent" and expense_head("agent commissions") == "commissions"
    assert expense_head("Courier charges") == "operations"


@pytest.mark.asyncio
async def test_a_future_month_is_422_and_no_month_is_the_current_month(client, db_session):
    await as_user(client, db_session)
    nxt = (TODAY.replace(day=28) + timedelta(days=5)).replace(day=1)
    assert (await client.get(ACCOUNTS, params={"month": month_param(nxt.year, nxt.month)})).status_code == 422
    assert (await client.get(ACCOUNTS, params={"month": "2026-13"})).status_code == 422
    out = await view(client)
    assert out["month"] == out["current_month"] == month_param(TODAY.year, TODAY.month) and out["as_of"] == TODAY.isoformat()


# --- balances (AD7-AD9, AD11) -------------------------------------------------------------------------------------------------------
async def put(client, month: str, **body):
    return await client.put(BALANCES, params={"month": month}, json={"cash_bank": None, "payables": None, "tax_liabilities": None, **body})


def balance_month() -> str:
    return month_param(random.randint(1950, 1999), random.randint(1, 12))


@pytest.mark.asyncio
async def test_a_month_without_balances_is_not_entered_then_saves_and_clears(client, db_session):
    user = await as_user(client, db_session)
    month = balance_month()
    assert (await put(client, month)).status_code == 200  # all null: the month is "not entered"
    empty = (await view(client, month))["balances"]
    assert empty == {"cash_bank": None, "payables": None, "tax_liabilities": None, "updated_at": None, "updated_by": None}
    saved = await put(client, month, cash_bank="-2500.50", payables="18000", tax_liabilities=None)  # an overdraft; tax not known yet
    assert saved.status_code == 200, saved.text
    b = saved.json()["balances"]
    assert (b["cash_bank"], b["payables"], b["tax_liabilities"]) == ("-2500.50", "18000.00", None)
    assert b["updated_by"]["id"] == str(user.id) and b["updated_at"]
    assert (await view(client, month))["balances"]["payables"] == "18000.00"
    assert (await put(client, month)).json()["balances"]["cash_bank"] is None  # all null removes the row


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "field"),
    [({"payables": "-1"}, "payables"), ({"tax_liabilities": "-0.01"}, "tax_liabilities"), ({"cash_bank": "10.123"}, "cash_bank"),
     ({"cash_bank": "abc"}, "cash_bank"), ({"payables": "1000000000000"}, "payables"), ({"cash_bank": "-1000000000000"}, "cash_bank")],
)  # fmt: skip
async def test_invalid_balances_are_422_on_their_field(client, db_session, body, field):
    await as_user(client, db_session)
    response = await put(client, balance_month(), **body)
    assert response.status_code == 422
    assert any(item["loc"][-1] == field or field in item["loc"] for item in response.json()["detail"])


@pytest.mark.asyncio
async def test_an_unknown_field_or_a_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    assert (await client.put(BALANCES, params={"month": "2020-01"}, json={"cash": "1"})).status_code == 422
    nxt = (TODAY.replace(day=28) + timedelta(days=5)).replace(day=1)
    assert (await put(client, month_param(nxt.year, nxt.month), cash_bank="1")).status_code == 422
    assert (await client.put(BALANCES, json={"cash_bank": "1", "payables": None, "tax_liabilities": None})).status_code == 422  # month required


@pytest.mark.asyncio
async def test_a_save_writes_one_audit_row_with_field_names_only_and_a_no_op_writes_none(client, db_session):
    await as_user(client, db_session)
    month = balance_month()
    await put(client, month)
    rows = lambda: db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "mgmt.balance", AuditLog.entity_id == month).order_by(AuditLog.created_at))  # noqa: E731
    start = len((await rows()).all())
    await put(client, month, cash_bank="500", payables="20")
    await put(client, month, cash_bank="500", payables="20")  # nothing changed
    await put(client, month, cash_bank="750", payables="20")
    logged = (await rows()).all()[start:]
    assert [a.metadata_json["fields"] for a in logged] == [["cash_bank", "payables"], ["cash_bank"]]
    assert all("values" not in a.metadata_json for a in logged)


def test_audit_catalogue_registers_the_balance_kind_as_finance():
    assert management_audit.KINDS["mgmt.balance"][1] == "finance"
