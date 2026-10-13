"""mgmt-007 (spec IR1-IR12): the §5 IT Training revenue dashboard. Read-only; every money figure is a counted `ledger.lines()` row of
the IT vertical (approved manual entries, reversals negative, + rupee automatic lines), attributed to a course and batch: a payment
through the enrolment it references, a manual entry through its batch / course tags (IR4). Spec:
docs/superpowers/specs/2026-10-13-mgmt-007-it-revenue-dashboard-design.md."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Enrollment, LedgerEntry, Payment, Program, Receipt
from app.services import ledger
from app.services.management_expenses import financial_year_start, head_of, month_key, next_month

ENROLMENT_REFERENCES = ("enrollment_fee", "enrollment")  # `workflows.py:437` bills `enrollment_fee`; the seed's legacy rows say `enrollment`
INCOME = (("enrolment_fees", "Enrolment fees"), ("other_fees", "Other IT fees"), ("manual", "Manual income"))  # IR3
COSTS = (("trainer", "Trainer"), ("marketing", "Marketing"), ("operational", "Operational"))  # IR7, from the mgmt-010 heads
COST_OF_HEAD = {"trainers": "trainer", "marketing": "marketing"}
NO_COURSE = "Choose a course from the list"
NO_BATCH = "Choose a batch from the list"
ONE_SCOPE = "Choose one course, one batch or the payments not linked to a course"


def quarter_start(month_start: date) -> date:
    """mgmt-009 PL1: the first day of `month_start`'s financial-year quarter (Apr, Jul, Oct, Jan)."""
    return month_start.replace(month=month_start.month - (month_start.month - 1) % 3)


def period_range(month_start: date, period: str) -> tuple[date, date]:
    """IR1: [start, end) of the month, or of the Indian financial year (mgmt-009: or its quarter) to the end of the month."""
    start = {"year": financial_year_start, "quarter": quarter_start}.get(period)
    return (start(month_start) if start else month_start), next_month(month_start)


def _attributed(table):
    """IR4: `lines()` with each line's batch and course. Every join is on a primary key, and only the matching source joins."""
    c = table.c
    batch_id = func.coalesce(Enrollment.batch_id, LedgerEntry.batch_id)
    joined = (
        table.outerjoin(Payment, and_(c.source == "payment", Payment.id == c.id))
        .outerjoin(Enrollment, and_(Payment.reference_type.in_(ENROLMENT_REFERENCES), Enrollment.id == Payment.reference_id))
        .outerjoin(LedgerEntry, and_(c.source == "manual", LedgerEntry.id == c.id))
        .outerjoin(Batch, Batch.id == batch_id)
    )
    income_kind = case((c.source == "manual", "manual"), (Payment.reference_type.in_(ENROLMENT_REFERENCES), "enrolment_fees"), else_="other_fees")
    return joined, batch_id, func.coalesce(Batch.program_id, LedgerEntry.program_id), income_kind


def _in_period(c, start: date, end: date) -> list:
    return [c.vertical == "it", c.entry_date >= start, c.entry_date < end]


def _money() -> dict:
    return {"revenue": Decimal(0), "costs": Decimal(0)}


async def dashboard(db: AsyncSession, month_start: date, period: str) -> dict:
    start, end = period_range(month_start, period)
    table = ledger.lines()
    c = table.c
    joined, batch_id, program_id, income_kind = _attributed(table)
    grouped = await db.execute(
        select(c.kind, income_kind, c.category_label, program_id, batch_id, func.sum(c.signed_amount))
        .select_from(joined)
        .where(*_in_period(c, start, end), c.counted)
        .group_by(c.kind, income_kind, c.category_label, program_id, batch_id)
    )
    rows = cast(Sequence[tuple[str, str, str, UUID | None, UUID | None, Decimal]], grouped.all())  # the union subquery's columns are untyped
    enrolled = (
        await db.execute(
            select(Batch.program_id, Enrollment.batch_id, func.count())
            .join(Batch, Batch.id == Enrollment.batch_id)
            .where(Enrollment.enrolled_on >= start, Enrollment.enrolled_on < end)
            .group_by(Batch.program_id, Enrollment.batch_id)
        )
    ).all()

    income = dict.fromkeys((key for key, _ in INCOME), Decimal(0))
    costs = dict.fromkeys((key for key, _ in COSTS), Decimal(0))
    unlinked = _money()
    courses: dict = defaultdict(lambda: {**_money(), "enrolments": 0, "unbatched": _money(), "batches": defaultdict(lambda: {**_money(), "enrolments": 0})})
    for kind, kind_of_income, label, course_id, batch, amount in rows:
        field = "revenue" if kind == "income" else "costs"
        if kind == "income":
            income[kind_of_income] += amount
        else:
            costs[COST_OF_HEAD.get(head_of(label), "operational")] += amount
        if course_id is None:
            unlinked[field] += amount
            continue
        courses[course_id][field] += amount
        (courses[course_id]["batches"][batch] if batch else courses[course_id]["unbatched"])[field] += amount
    for course_id, batch, count in enrolled:
        courses[course_id]["enrolments"] += count
        courses[course_id]["batches"][batch]["enrolments"] += count

    titles = dict((await db.execute(select(Program.id, Program.title).where(Program.id.in_(list(courses))))).all()) if courses else {}
    batch_ids = [b for course in courses.values() for b in course["batches"]]
    names = dict((await db.execute(select(Batch.id, Batch.name).where(Batch.id.in_(batch_ids)))).all()) if batch_ids else {}
    q = ledger.CENTS

    def figures(item: dict) -> dict:
        return {"revenue": item["revenue"].quantize(q), "costs": item["costs"].quantize(q)}

    def listed(item: dict) -> bool:  # IR10
        return bool(item["revenue"] or item["costs"] or item.get("enrolments"))

    course_rows = [
        {
            "program_id": course_id,
            "title": titles[course_id],
            "enrolments": course["enrolments"],
            **figures(course),
            "contribution": (course["revenue"] - course["costs"]).quantize(q),
            "batches": sorted(
                ({"batch_id": b, "name": names[b], "enrolments": item["enrolments"], **figures(item)} for b, item in course["batches"].items() if listed(item)),
                key=lambda row: (-row["revenue"], row["name"].lower()),
            ),
            "unbatched": figures(course["unbatched"]),
        }
        for course_id, course in courses.items()
        if listed(course)
    ]
    course_rows.sort(key=lambda row: (-row["revenue"], row["title"].lower()))
    revenue, cost = sum(income.values(), Decimal(0)), sum(costs.values(), Decimal(0))
    other = await db.execute(
        select(c.currency, func.sum(c.amount), func.count()).where(*_in_period(c, start, end), c.source != "manual", c.counted.is_(False)).group_by(c.currency).order_by(c.currency)
    )
    return {
        "month": month_key(month_start),
        "period": period,
        "start": start,
        "end": end - timedelta(days=1),
        "label": f"Financial year {start.year}-{(start.year + 1) % 100:02d} to date" if period == "year" else month_start.strftime("%B %Y"),
        "totals": {"revenue": revenue.quantize(q), "costs": cost.quantize(q), "contribution": (revenue - cost).quantize(q), "enrolments": sum(r["enrolments"] for r in course_rows)},
        "income": [{"key": key, "label": label, "amount": income[key].quantize(q)} for key, label in INCOME],
        "costs": [{"key": key, "label": label, "amount": costs[key].quantize(q)} for key, label in COSTS],
        "courses": course_rows,
        "unlinked": figures(unlinked),
        "placement": None,  # IR9: rec-031 invoices are per job, not per candidate -- not tracked
        "not_counted": [{"currency": currency, "amount": amount.quantize(q), "count": count} for currency, amount, count in cast(Sequence[tuple[str, Decimal, int]], other.all())],
    }


async def payments(db: AsyncSession, month_start: date, period: str, *, program_id=None, batch_id=None, unlinked: bool = False, limit: int, offset: int) -> dict:
    """IR11: the counted IT payment lines of one course, one batch or none, newest first. No student names or emails (Q-32 open)."""
    if sum((program_id is not None, batch_id is not None, unlinked)) != 1:
        raise HTTPException(422, ONE_SCOPE)
    if program_id is not None and await db.get(Program, program_id) is None:
        raise HTTPException(422, NO_COURSE)
    if batch_id is not None and await db.get(Batch, batch_id) is None:
        raise HTTPException(422, NO_BATCH)
    start, end = period_range(month_start, period)
    table = ledger.lines()
    c = table.c
    joined, _, _, income_kind = _attributed(table)
    scope = Batch.program_id == program_id if program_id is not None else Enrollment.batch_id == batch_id if batch_id is not None else Enrollment.id.is_(None)
    where = [*_in_period(c, start, end), c.counted, c.source == "payment", scope]
    total = await db.scalar(select(func.count()).select_from(joined).where(*where))
    kind = case((income_kind == "enrolment_fees", "Enrolment fee"), else_="Other IT fee")
    rows = await db.execute(
        select(
            c.id,
            c.entry_date,
            kind.label("kind"),
            c.amount,
            c.currency,
            Payment.installment_no,
            Receipt.receipt_no,
            Enrollment.enrollment_code,
            Program.title.label("course"),
            Batch.name.label("batch"),
        )
        .select_from(joined.outerjoin(Receipt, Receipt.payment_id == Payment.id).outerjoin(Program, Program.id == Batch.program_id))
        .where(*where)
        .order_by(c.entry_date.desc(), c.created_at.desc(), c.id)
        .limit(limit)
        .offset(offset)
    )
    return {"items": [dict(row._mapping) for row in rows], "total": total, "limit": limit, "offset": offset}
