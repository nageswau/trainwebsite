"""mgmt-009 (spec PL1-PL12): the §7 company profitability dashboard -- revenue, expenses, contribution and margin per vertical and in
total, for a month, its financial-year quarter or its financial year to date. Read-only; one grouped read of the counted
`ledger.lines()`, so every rupee lands in exactly one row and the total is the rows' sum (AC). Shared costs are their own row, never
allocated (PL4, Q-04). University commission is in the figures for partners only (PL7, M3). Spec:
docs/superpowers/specs/2026-10-13-mgmt-009-company-profitability-design.md."""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import ledger
from app.services.management_access import can_view_university_commission
from app.services.management_expenses import financial_year_start, month_key
from app.services.management_it_revenue import period_range

# PL3/PL4: the ledger verticals in the §7/§22 order, the unallocated shared costs last.
ROWS = (
    ("abroad", "Abroad Education"),
    ("it", "IT Training"),
    ("recruitment", "Recruitment"),
    ("school", "School projects"),
    ("other", "Other"),
    ("shared", "Shared (company-wide, not allocated)"),
)
QUARTERS = {4: "Q1 (April–June)", 7: "Q2 (July–September)", 10: "Q3 (October–December)", 1: "Q4 (January–March)"}


def _label(month_start: date, start: date, period: str) -> str:
    fy = financial_year_start(month_start).year
    year = f"{fy}-{(fy + 1) % 100:02d}"
    if period == "year":
        return f"Financial year {year} to date"
    if period == "quarter":
        return f"{QUARTERS[start.month]} of {year} to date"
    return month_start.strftime("%B %Y")


def _figures(revenue: Decimal, expenses: Decimal) -> dict:
    """PL5: contribution = revenue - expenses; margin = contribution / revenue in per cent, none without revenue."""
    contribution = revenue - expenses
    return {
        "revenue": revenue.quantize(ledger.CENTS),
        "expenses": expenses.quantize(ledger.CENTS),
        "contribution": contribution.quantize(ledger.CENTS),
        "margin": round(float(contribution / revenue * 100), 1) if revenue > 0 else None,
    }


async def dashboard(db: AsyncSession, user: User, month_start: date, period: str) -> dict:
    start, end = period_range(month_start, period)
    commission_visible = can_view_university_commission(user)
    c = ledger.lines().c
    where = [c.entry_date >= start, c.entry_date < end]
    if not commission_visible:
        where.append(c.source != "university_commission")  # PL7: never fetched, so no figure can carry it

    sums = {(vertical, kind): Decimal(0) for vertical, _ in ROWS for kind in ("income", "expense")}
    grouped = await db.execute(select(c.vertical, c.kind, func.sum(c.signed_amount)).where(*where, c.counted).group_by(c.vertical, c.kind))
    for vertical, kind, amount in cast(Sequence[tuple[str, str, Decimal]], grouped.all()):  # the union subquery's columns are untyped
        sums[(vertical, kind)] += amount
    other = await db.execute(
        select(c.currency, c.kind, func.sum(c.amount), func.count()).where(*where, c.source != "manual", c.counted.is_(False)).group_by(c.currency, c.kind).order_by(c.currency, c.kind)
    )

    rows = [{"key": key, "label": label, **_figures(sums[(key, "income")], sums[(key, "expense")])} for key, label in ROWS]
    revenue = sum((sums[(key, "income")] for key, _ in ROWS), Decimal(0))
    expenses = sum((sums[(key, "expense")] for key, _ in ROWS), Decimal(0))
    return {
        "month": month_key(month_start),
        "period": period,
        "start": start,
        "end": end - timedelta(days=1),
        "label": _label(month_start, start, period),
        "commission_visible": commission_visible,
        "rows": rows,
        "total": _figures(revenue, expenses),
        "not_counted": [
            {"currency": cur, "kind": kind, "amount": Decimal(amount).quantize(ledger.CENTS), "count": count} for cur, kind, amount, count in cast(Sequence[tuple[str, str, Decimal, int]], other.all())
        ],
    }
