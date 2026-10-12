"""mgmt-013 (spec AD1-AD14): the accounts dashboard -- EVID-017 §22's income heads, expense heads and financial position for a month.

Finance tier only (M13): the routes call `ledger.require_finance` first. Income, expenses and profit are the month's counted ledger lines
(`ledger.lines()`, mgmt-005), so nothing is copied. Receivables and pending invoices are read live from the modules that bill (payments,
rec-031, upc-019) as of today. Only cash/bank, payables and tax liabilities are typed in (`finance_balances`); a save adds a
`management_audit` row (field names, never amounts) in the caller's transaction and the route commits once.
Spec: docs/superpowers/specs/2026-10-12-mgmt-013-accounts-dashboard-design.md.
"""

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FinanceBalance, Invoice, OverseasApplication, Payment, RecruiterInvoice, RecruiterPayment, User
from app.schemas import FinanceBalancesIn
from app.services import ledger, management_audit, university_commission
from app.services.agent_deposits import REFERENCE_TYPE as AGENT_DEPOSIT
from app.services.salaries import month_key

logger = logging.getLogger("app.management")
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
FUTURE = "Accounts can be shown up to the current month"
UNPAID = ("pending", "overdue")  # a fee still owed (the codebase's own reading, workflows.py)
FIGURES = ("cash_bank", "payables", "tax_liabilities")

# AD2: the five §22 income heads are the ledger verticals; company-wide ("shared") income is shown under Other.
INCOME_HEADS = (("abroad", "Abroad education"), ("it", "IT training"), ("recruitment", "Recruitment"), ("school", "School projects"), ("other", "Other"))
# AD3: the eight §22 expense heads, in source order, and the ledger category labels each takes (any other label -> Operations).
EXPENSE_HEADS = (
    ("salaries", "Salaries"), ("rent", "Rent"), ("marketing", "Marketing"), ("travel", "Travel"), ("trainers", "Trainers"),
    ("commissions", "Commissions"), ("operations", "Operations"), ("technology", "Technology"),
)  # fmt: skip
EXPENSE_LABELS = {
    "salaries": "salaries", "office rent": "rent", "marketing": "marketing", "events": "marketing", "travel": "travel",
    "trainer payments": "trainers", "agent commissions": "commissions", "internet": "technology", "software": "technology",
}  # fmt: skip


def expense_head(label: str) -> str:
    return EXPENSE_LABELS.get(label.strip().lower(), "operations")


def income_head(vertical: str) -> str:
    return "other" if vertical == "shared" else vertical


def log(event: str, user: User, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), **extra}})


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENTS)


def _section(heads: tuple[tuple[str, str], ...], parts: dict[str, dict[str, Decimal]], total: Decimal) -> dict:
    out = []
    for key, label in heads:
        found = parts.get(key, {})
        listed = [{"label": k, "amount": _money(v)} for k, v in sorted(found.items()) if v != 0]  # QA-03: a label netting to 0 says nothing
        out.append({"key": key, "label": label, "amount": _money(sum(found.values(), ZERO)), "parts": listed})
    return {"heads": out, "total": total}


async def income_expense(db: AsyncSession, month: date) -> dict:
    """AD2-AD4: the month's counted lines grouped into heads (one query), with the totals and not-counted list of `lines_totals`."""
    table = ledger.lines()
    c = table.c
    where = ledger.list_filters(month=month_key(month), kind=None, category_id=None, vertical=None, table=table)
    rows = await db.execute(select(c.kind, c.vertical, c.category_label, func.sum(c.signed_amount)).where(*where, c.counted).group_by(c.kind, c.vertical, c.category_label))
    parts: dict[str, dict[str, dict[str, Decimal]]] = {"income": defaultdict(lambda: defaultdict(Decimal)), "expense": defaultdict(lambda: defaultdict(Decimal))}
    for kind, vertical, label, amount in rows.all():
        key = income_head(vertical) if kind == "income" else expense_head(label)
        parts[kind][key][label] += Decimal(amount)
    totals = await ledger.lines_totals(db, table, where)
    return {
        "income": _section(INCOME_HEADS, parts["income"], totals["income"]),
        "expenses": _section(EXPENSE_HEADS, parts["expense"], totals["expense"]),
        "profit": totals["net"],
        "not_counted": totals["not_counted"],
    }


def _recruiter_outstanding():
    """rec-031: each invoice that is not cancelled, at amount − received."""
    received = select(RecruiterPayment.invoice_id, func.sum(RecruiterPayment.amount).label("received")).group_by(RecruiterPayment.invoice_id).subquery()
    outstanding = (RecruiterInvoice.amount - func.coalesce(received.c.received, 0)).label("outstanding")
    return (
        select(RecruiterInvoice.due_date, outstanding)
        .outerjoin(received, received.c.invoice_id == RecruiterInvoice.id)
        .where(RecruiterInvoice.cancelled_at.is_(None))
        .subquery()
    )


async def receivables(db: AsyncSession, today: date) -> dict:
    """AD5 (R8): what is owed to EduSphere today -- unpaid fees, open recruitment invoices and university commission still expected."""
    owed = [Payment.status.in_(UNPAID), Payment.reference_type != AGENT_DEPOSIT]
    late = or_(Payment.status == "overdue", Payment.due_date < today)
    fees = await db.execute(
        select(Payment.currency, func.sum(Payment.amount), func.sum(case((late, Payment.amount), else_=0)), func.count()).where(*owed).group_by(Payment.currency)
    )
    fee_total, fee_overdue, not_counted = ZERO, ZERO, []
    for currency, amount, overdue, count in fees.all():
        if currency == ledger.CURRENCY:
            fee_total, fee_overdue = _money(amount), _money(overdue)
        else:
            not_counted.append({"currency": currency, "kind": "fees", "amount": _money(amount), "count": count})
    rec = _recruiter_outstanding()
    rec_total, rec_overdue = (
        await db.execute(select(func.sum(rec.c.outstanding), func.sum(case((rec.c.due_date < today, rec.c.outstanding), else_=0))).where(rec.c.outstanding > 0))
    ).one()
    university, other = await university_outstanding(db)
    not_counted += other
    recruitment = _money(rec_total)
    return {
        "total": fee_total + recruitment + university,
        "overdue": fee_overdue + _money(rec_overdue),
        "fees": fee_total,
        "recruitment": recruitment,
        "university": university,
        "not_counted": not_counted,
    }


async def university_outstanding(db: AsyncSession) -> tuple[Decimal, list[dict]]:
    """AD5(c): per university and currency, Expected − received floored at 0 (an over-payment never offsets another university); the
    rupee total, and the other currencies listed. Only universities with an enrolled application can be owed anything."""
    ids = list((await db.scalars(select(OverseasApplication.university_id).where(OverseasApplication.status == "enrolled", OverseasApplication.university_id.is_not(None)).distinct())).all())
    expected = await university_commission.expected_rows(db, ids)
    received = await university_commission.received_sums(db, ids)
    by_currency: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for university_id, rows in expected.items():
        for currency, amount in university_commission.currency_sums(rows).items():
            owed = amount - received.get(university_id, {}).get(currency, ZERO)
            if owed > 0:
                by_currency[currency] += owed
                counts[currency] += 1
    other = [{"currency": cur, "kind": "university", "amount": _money(v), "count": counts[cur]} for cur, v in sorted(by_currency.items()) if cur != ledger.CURRENCY]
    return _money(by_currency.get(ledger.CURRENCY)), other


async def pending_invoices(db: AsyncSession) -> dict:
    """AD6 (R9): fee invoices whose payment is still owed + recruitment invoices with an outstanding amount. Rupees only."""
    fee_count, fee_amount = (
        await db.execute(
            select(func.count(), func.sum(Invoice.amount))
            .join(Payment, Payment.id == Invoice.payment_id)
            .where(Payment.status.in_(UNPAID), Payment.reference_type != AGENT_DEPOSIT, Invoice.currency == ledger.CURRENCY)
        )
    ).one()
    rec = _recruiter_outstanding()
    rec_count, rec_amount = (await db.execute(select(func.count(), func.sum(rec.c.outstanding)).where(rec.c.outstanding > 0))).one()
    return {"count": fee_count + rec_count, "amount": _money(fee_amount) + _money(rec_amount)}


async def balances(db: AsyncSession, month: date) -> dict:
    """AD7/AD9: the month's entered figures; null where not entered, no carry-forward."""
    row = await db.scalar(select(FinanceBalance).where(FinanceBalance.month == month))
    editor = await db.get(User, row.updated_by_user_id) if row else None
    return {
        **{f: (getattr(row, f) if row else None) for f in FIGURES},
        "updated_at": row.updated_at if row else None,
        "updated_by": {"id": editor.id, "full_name": editor.full_name} if editor else None,
    }


async def view(db: AsyncSession, month: date) -> dict:
    today = ledger.today()
    return {
        "month": month_key(month),
        "current_month": month_key(today),
        "as_of": today,
        **await income_expense(db, month),
        "receivables": await receivables(db, today),
        "pending_invoices": await pending_invoices(db),
        "balances": await balances(db, month),
    }


async def save_balances(db: AsyncSession, user: User, month: date, body: FinanceBalancesIn) -> list[str]:
    """AD8/AD11: the month's row becomes `body` (all null removes it). A transaction-scoped advisory lock serialises two saves of one
    month; one audit row names the changed fields, and a save that changes nothing writes none. Returns the changed field names."""
    key = month_key(month)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"finance_balance:{key}"))))
    row = await db.scalar(select(FinanceBalance).where(FinanceBalance.month == month))
    values = body.model_dump()
    current = {f: (getattr(row, f) if row else None) for f in FIGURES}
    changed = [f for f in FIGURES if current[f] != values[f]]
    if not changed:
        return []
    if row is None:
        db.add(FinanceBalance(month=month, created_by_user_id=user.id, updated_by_user_id=user.id, **values))
    elif all(v is None for v in values.values()):
        await db.delete(row)
    else:
        for f in changed:
            setattr(row, f, values[f])
        row.updated_by_user_id = user.id
    await db.flush()
    management_audit.record(db, user, "mgmt.balance", "create" if row is None else "update", key, fields=changed)
    return changed
