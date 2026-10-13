"""mgmt-012 (spec MK1-MK14): EVID-017 §10 Budget -> Spend -> Leads -> Conversions -> Revenue -> ROI per marketing channel, and the §15
marketing figures, for one month.

A channel is a lead source (MK1), so budgets, ledger spend tags and `enquiries.source` share one key. Spend is the approved manual
expenses tagged with the channel (ML6, ML10: a reversal counts negative); automatic ledger lines carry no channel, so nothing is counted
twice (AC2). Revenue is the month's counted ledger payment lines paid by students of the channel's converted leads, on or after the
link (MK8). Money is only queried for the finance tier (MK11). Budgets are the only figures typed in; a save adds a `management_audit`
row (channel names, never amounts) in the caller's transaction and the route commits once.
Spec: docs/superpowers/specs/2026-10-13-mgmt-012-marketing-roi-design.md.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Enquiry, LedgerEntry, MarketingBudget, Payment, TelCampaign, User
from app.schemas import MarketingBudgetIn
from app.services import ledger, management_audit, telecaller_metrics
from app.services.bdm_activities import day_range
from app.services.management_access import can_view_finance
from app.services.management_expenses import next_month
from app.services.salaries import month_key
from app.services.telecaller_reports import SOURCE_LABELS, _count
from app.tel_sources import TEL_SOURCES

KIND = "mgmt.marketing_budget"
FUTURE = "Marketing can be shown up to the current month"
CENTS = ledger.CENTS
ZERO = Decimal("0.00")
# MK2: the §15 source groups. Influencer leads have no source, so they are not tracked (null).
GROUPS = (
    ("social", ("instagram", "facebook", "whatsapp")), ("website", ("website",)), ("school", ("school",)), ("college", ("college",)),
    ("agent", ("agent",)), ("events", ("exhibition_event",)),
)  # fmt: skip


def roi(revenue: Decimal, spend: Decimal) -> float | None:
    """K7 (MK9): (revenue − spend) ÷ spend × 100, half-up to one decimal; none without spend."""
    if spend <= 0:
        return None
    return float(((revenue - spend) / spend * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def conversion(customers: int, leads: int) -> float | None:
    return round(customers * 100 / leads, 1) if leads else None


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENTS)


async def _lead_counts(db: AsyncSession, key, start, end) -> dict:
    """K3/K4 (MK6): leads created in the range per `key`, and how many reached Qualified (the tel-024 source-report rule)."""
    rows = await db.execute(select(key, func.count(), _count("qualified")).where(Enquiry.created_at >= start, Enquiry.created_at < end).group_by(key))
    return {k: (leads, qualified) for k, leads, qualified in rows.all()}


async def _customers(db: AsyncSession, key, start, end) -> dict:
    """K5 (MK7): leads still converted whose first conversion falls in the range (tel T5/DB2, as mgmt-019 counts them)."""
    first = telecaller_metrics.first_conversions()
    rows = await db.execute(
        select(key, func.count()).select_from(Enquiry).join(first, first.c.lead_id == Enquiry.id)
        .where(Enquiry.status == "converted", first.c.at >= start, first.c.at < end).group_by(key)
    )  # fmt: skip
    return dict(rows.all())


async def _spend(db: AsyncSession, month: date, end: date) -> dict:
    """K2 (MK5): approved expense entries tagged with a channel; a reversal (which copies the channel) counts negative."""
    signed = case((LedgerEntry.reversal_of_id.is_(None), LedgerEntry.amount), else_=-LedgerEntry.amount)
    rows = await db.execute(
        select(LedgerEntry.channel, func.sum(signed))
        .where(LedgerEntry.kind == "expense", LedgerEntry.status == "approved", LedgerEntry.channel.is_not(None), LedgerEntry.entry_date >= month, LedgerEntry.entry_date < end)
        .group_by(LedgerEntry.channel)
    )
    return {channel: _money(amount) for channel, amount in rows.all()}


async def _revenue(db: AsyncSession, month: date, end: date) -> dict:
    """K6 (MK8): the month's counted ledger payment lines (paid, INR, no agent deposits) of students linked to a still-converted lead,
    paid on or after the IST day of the link. A student has at most one lead, so a payment lands in one channel."""
    lines = ledger.lines()
    c = lines.c
    rows = await db.execute(
        select(Enquiry.source, func.sum(c.signed_amount))
        .select_from(lines)
        .join(Payment, Payment.id == c.id)
        .join(Enquiry, Enquiry.converted_user_id == Payment.user_id)
        .where(c.source == "payment", c.counted, c.entry_date >= month, c.entry_date < end, Enquiry.status == "converted", c.entry_date >= ledger.ist_day(Enquiry.converted_at))
        .group_by(Enquiry.source)
    )
    return {source: _money(amount) for source, amount in rows.all()}


async def _budgets(db: AsyncSession, month: date) -> dict:
    return dict((await db.execute(select(MarketingBudget.channel, MarketingBudget.amount).where(MarketingBudget.month == month))).all())


async def _last_save(db: AsyncSession, month: date) -> tuple:
    """Who saved the month's budgets last, from the audit row (a cleared channel leaves no budget row to read it from)."""
    row = (
        await db.execute(
            select(AuditLog.created_at, User.id, User.full_name)
            .join(User, User.id == AuditLog.user_id)
            .where(AuditLog.entity_type == KIND, AuditLog.entity_id == month_key(month))
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
    ).first()
    return (row.created_at, {"id": row.id, "full_name": row.full_name}) if row else (None, None)


def _figures(budget, spend, leads: int, qualified: int, customers: int, revenue, money: bool) -> dict:
    return {
        "budget": budget if money else None,
        "spend": spend if money else None,
        "leads": leads,
        "qualified": qualified,
        "customers": customers,
        "conversion": conversion(customers, leads),
        "revenue": revenue if money else None,
        "roi": roi(revenue, spend) if money else None,
    }


async def _campaigns(db: AsyncSession, month: date, end: date, start, stop) -> list[dict]:
    """MK10: campaigns that ran in the month or brought leads or customers in it, with their lead figures (no spend: tags are per channel)."""
    leads = await _lead_counts(db, Enquiry.campaign_id, start, stop)
    customers = await _customers(db, Enquiry.campaign_id, start, stop)
    ran = and_(TelCampaign.start_date < end, or_(TelCampaign.end_date.is_(None), TelCampaign.end_date >= month))
    ids = {i for i in (*leads, *customers) if i is not None}
    rows = (await db.scalars(select(TelCampaign).where(or_(ran, TelCampaign.id.in_(ids))).order_by(func.lower(TelCampaign.name), TelCampaign.id))).all()
    return [
        {
            "id": r.id, "name": r.name, "channel": r.source, "label": SOURCE_LABELS[r.source], "active": r.active,
            "leads": leads.get(r.id, (0, 0))[0], "qualified": leads.get(r.id, (0, 0))[1], "customers": customers.get(r.id, 0),
        }
        for r in rows
    ]  # fmt: skip


async def dashboard(db: AsyncSession, user: User, month: date) -> dict:
    """K1-K7 per channel and in total, the §15 groups and the campaigns for `month` (its 1st). Money only for the finance tier (MK11)."""
    end = next_month(month)
    start, stop = day_range(month)[0], day_range(end)[0]
    money = can_view_finance(user)
    leads = await _lead_counts(db, Enquiry.source, start, stop)
    customers = await _customers(db, Enquiry.source, start, stop)
    budgets, spend, revenue = (await _budgets(db, month), await _spend(db, month, end), await _revenue(db, month, end)) if money else ({}, {}, {})
    channels = []
    for ch in TEL_SOURCES:
        count, qualified = leads.get(ch, (0, 0))
        figures = _figures(budgets.get(ch), spend.get(ch, ZERO), count, qualified, customers.get(ch, 0), revenue.get(ch, ZERO), money)
        channels.append({"channel": ch, "label": SOURCE_LABELS[ch], **figures})
    total = {k: sum(r[k] for r in channels) for k in ("leads", "qualified", "customers")}
    budget_total = sum(budgets.values(), ZERO) if budgets else None
    updated_at, updated_by = await _last_save(db, month) if money else (None, None)
    return {
        "month": month_key(month),
        "current_month": month_key(ledger.today()),
        "money_visible": money,
        "channels": channels,
        "totals": _figures(budget_total, sum(spend.values(), ZERO), total["leads"], total["qualified"], total["customers"], sum(revenue.values(), ZERO), money),
        "groups": {key: sum(leads.get(s, (0, 0))[0] for s in sources) for key, sources in GROUPS} | {"influencer": None},
        "campaigns": await _campaigns(db, month, end, start, stop),
        "budgets_updated_at": updated_at,
        "budgets_updated_by": updated_by,
    }


async def save_budgets(db: AsyncSession, user: User, month: date, budgets: list[MarketingBudgetIn]) -> list[str]:
    """MK4/MK12/MK13: the month's budgets become `budgets` (channels left out are removed). A transaction-scoped advisory lock serialises
    two saves of one month; one audit row names the changed channels, and a save that changes nothing writes none."""
    key = month_key(month)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"marketing_budget:{key}"))))
    rows = {r.channel: r for r in (await db.scalars(select(MarketingBudget).where(MarketingBudget.month == month))).all()}
    wanted = {b.channel: b.amount for b in budgets}
    changed = [ch for ch in TEL_SOURCES if (rows[ch].amount if ch in rows else None) != wanted.get(ch)]
    if not changed:
        return []
    for ch in changed:
        if ch not in wanted:
            await db.delete(rows[ch])
        elif ch in rows:
            rows[ch].amount, rows[ch].updated_by_user_id = wanted[ch], user.id
        else:
            db.add(MarketingBudget(month=month, channel=ch, amount=wanted[ch], created_by_user_id=user.id, updated_by_user_id=user.id))
    await db.flush()
    management_audit.record(db, user, KIND, "update", key, fields=changed)
    return changed
