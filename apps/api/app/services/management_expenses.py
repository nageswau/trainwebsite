"""mgmt-010 (spec ME1-ME10): the §8 expense dashboard. Read-only; every figure comes from `ledger.lines()` (approved manual expenses,
reversals negative, + automatic expense lines in rupees), grouped into the eight §8 heads for the selected month and the Indian
financial year to date. Spec: docs/superpowers/specs/2026-10-12-mgmt-010-expense-dashboard-design.md."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ledger

# ME1: the §8 heads in source order and the categories (manual names or automatic labels, lower case) that make each one up.
# Everything not named here -- the other seeded categories and any added or renamed later (ME2) -- is Other.
HEADS = (
    ("rent", "Rent", ("office rent",)),
    ("salaries", "Salaries", ("salaries",)),
    ("marketing", "Marketing", ("marketing",)),
    ("travel", "Travel", ("travel",)),
    ("trainers", "Trainers", ("trainer payments",)),
    ("commissions", "Commissions", ("agent commissions",)),
    ("technology", "Technology", ("internet", "software")),
    ("other", "Other", ()),
)
HEAD_OF = {name: key for key, _, names in HEADS for name in names}
FY_START_MONTH = 4  # ME4: the Indian financial year runs 1 April - 31 March


def head_of(label: str) -> str:
    return HEAD_OF.get(label.lower(), "other")


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def financial_year_start(month_start: date) -> date:
    return date(month_start.year if month_start.month >= FY_START_MONTH else month_start.year - 1, FY_START_MONTH, 1)


def next_month(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


async def dashboard(db: AsyncSession, month_start: date) -> dict:
    """The heads, categories and month-by-month totals for `month_start`'s month and its financial year to date (ME3-ME7)."""
    year_start, end = financial_year_start(month_start), next_month(month_start)
    table = ledger.lines()
    c = table.c
    in_range = [c.kind == "expense", c.entry_date >= year_start, c.entry_date < end]
    month_col = func.date_trunc("month", c.entry_date).label("month")
    rows = (await db.execute(select(c.category_label, month_col, func.sum(c.signed_amount)).where(*in_range, c.counted).group_by(c.category_label, month_col))).all()

    months: dict[str, Decimal] = {}
    day = year_start
    while day < end:
        months[month_key(day)] = Decimal(0)
        day = next_month(day)
    by_label: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"month": Decimal(0), "year": Decimal(0)})
    for label, month, amount in rows:
        key = month_key(month)  # date_trunc returns a timestamp; only its year and month are read
        months[key] += amount
        by_label[label]["year"] += amount
        if key == month_key(month_start):
            by_label[label]["month"] += amount

    heads = {key: {"month": Decimal(0), "year": Decimal(0)} for key, _, _ in HEADS}
    for label, sums in by_label.items():
        for period in ("month", "year"):
            heads[head_of(label)][period] += sums[period]
    year_total = sum((h["year"] for h in heads.values()), Decimal(0))

    def share(amount: Decimal) -> float:
        return round(float(max(amount, Decimal(0)) / year_total * 100), 1) if year_total > 0 else 0.0

    other = await db.execute(select(c.currency, func.sum(c.amount), func.count()).where(*in_range, c.source != "manual", c.counted.is_(False)).group_by(c.currency).order_by(c.currency))
    q = ledger.CENTS
    return {
        "month": month_key(month_start),
        "year_start": year_start,
        "year_label": f"{year_start.year}-{(year_start.year + 1) % 100:02d}",
        "groups": [{"key": key, "label": label, "month": heads[key]["month"].quantize(q), "year": heads[key]["year"].quantize(q), "share": share(heads[key]["year"])} for key, label, _ in HEADS],
        "categories": [
            {"label": label, "group": head_of(label), "month": sums["month"].quantize(q), "year": sums["year"].quantize(q)}
            for label, sums in sorted(by_label.items(), key=lambda item: (-item[1]["year"], item[0].lower()))
            if sums["month"] or sums["year"]  # browser QA-01: a category netted to zero by a reversal says nothing
        ],
        "months": [{"month": key, "total": total.quantize(q)} for key, total in months.items()],
        "totals": {"month": sum((h["month"] for h in heads.values()), Decimal(0)).quantize(q), "year": year_total.quantize(q)},
        "not_counted": [{"currency": currency, "amount": Decimal(amount).quantize(q), "count": count} for currency, amount, count in other.all()],
    }
