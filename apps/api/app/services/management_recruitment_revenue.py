"""mgmt-008 (spec RR1-RR12): the §6 Recruitment & Placement revenue dashboard. Read-only. Money is the counted `ledger.lines()` income of
the Recruitment vertical -- rec-031 invoice payments + approved manual income per category (RR3, Q-12) -- and only the finance tier gets
it (RR9: the super admin's read never touches the ledger). The flow KPIs are rec-033's Total for the same range (AC2), the stock KPIs the
Command Center's own S10/S15 and the open requirements. Spec: docs/superpowers/specs/2026-10-13-mgmt-008-recruitment-revenue-design.md."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, User
from app.services import ledger, management_metrics, recruiter_metrics
from app.services.bdm_appointments import today_ist
from app.services.management_access import MANAGEMENT_ROLES, can_view_finance
from app.services.management_expenses import month_key
from app.services.management_it_revenue import period_range

INVOICES = ("recruiter_invoices", "Recruiter invoice payments")  # RR3: rec-031, the recruitment / placement fees per requirement
FLOW = {"candidates": "candidates_sourced", "interviews": "interviews", "selections": "selected", "joining": "joined"}  # RR5: rec-033 P4/P6/P7/P8


async def revenue_by_kind(db: AsyncSession, start: date, end: date) -> dict:
    """RR2-RR4: the invoice row always, then each manual category with a non-zero sum, largest first; the total is their sum."""
    c = ledger.lines().c
    grouped = await db.execute(
        select(c.source, c.category_label, func.sum(c.signed_amount))
        .where(c.vertical == "recruitment", c.kind == "income", c.counted, c.entry_date >= start, c.entry_date < end)
        .group_by(c.source, c.category_label)
    )
    invoices, categories = Decimal(0), {}
    for source, label, amount in cast(Sequence[tuple[str, str, Decimal]], grouped.all()):  # the union subquery's columns are untyped
        if source == "manual":
            categories[label] = amount
        else:
            invoices += amount
    q = ledger.CENTS
    manual = sorted(((label, amount) for label, amount in categories.items() if amount), key=lambda item: (-item[1], item[0].lower()))
    return {
        "total": (invoices + sum(categories.values(), Decimal(0))).quantize(q),
        "kinds": [{"key": INVOICES[0], "label": INVOICES[1], "amount": invoices.quantize(q)}]
        + [{"key": f"ledger:{label}", "label": label, "amount": amount.quantize(q)} for label, amount in manual],
    }


async def dashboard(db: AsyncSession, user: User, month_start: date, period: str, now: datetime) -> dict:
    start, end = period_range(month_start, period)
    kpi_end = min(end - timedelta(days=1), today_ist(now))  # RR5: rec-033 refuses a range that ends in the future
    flow = (await recruiter_metrics.performance(db, user, None, start, kpi_end, now, roles=tuple(MANAGEMENT_ROLES)))["totals"]
    stock = (
        await db.execute(
            select(
                management_metrics.recruiters().label("recruiters"),
                management_metrics.partner_companies().label("partner_companies"),
                select(func.count()).where(Job.status.not_in(recruiter_metrics.PARKED_REQUIREMENTS)).scalar_subquery().label("open_positions"),
            )
        )
    ).one()
    kpis = {**stock._asdict(), **{kpi: flow[key] for kpi, key in FLOW.items()}}
    kpis["placement_pct"] = round(kpis["joining"] * 100 / kpis["candidates"], 1) if kpis["candidates"] else None  # RR7
    revenue = await revenue_by_kind(db, start, end) if can_view_finance(user) else None  # RR9: never queried for the super admin
    kpis["revenue_per_placement"] = (revenue["total"] / kpis["joining"]).quantize(ledger.CENTS) if revenue and kpis["joining"] else None  # RR8
    return {
        "month": month_key(month_start),
        "period": period,
        "start": start,
        "end": end - timedelta(days=1),
        "label": f"Financial year {start.year}-{(start.year + 1) % 100:02d} to date" if period == "year" else month_start.strftime("%B %Y"),
        "kpi_end": kpi_end,
        "revenue_visible": revenue is not None,
        "revenue": revenue,
        "kpis": kpis,
    }
