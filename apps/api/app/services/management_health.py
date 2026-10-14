"""mgmt-030 (EVID-017 §30, Appendix B "Business health", spec BH1-BH14): the business health score -- twelve factors, each scored 0-100
against the month before (BH3/BH5), weighted into one overall score whose whole points add up to it (upc-028's `health_score`, BH8).
A read-through of the figures the merged dashboards own: mgmt-009's P&L, mgmt-013's balances, mgmt-011's headcount, mgmt-012's ROI
and mgmt-026's plan KPIs. Finance factors are never queried for super_admin (BH1, M13). Nothing is stored, logged or audited.
Weights, scales and bands are constants here (BH14, Q-29 interim). Spec: docs/superpowers/specs/2026-10-14-mgmt-030-business-health-score-design.md."""

from datetime import date, timedelta
from decimal import Decimal
from math import floor

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enquiry, FinanceBalance, SalaryMonthTotal, User
from app.services import ledger, management_marketing, management_pnl
from app.services import management_metrics as metrics
from app.services.management_access import can_view_finance
from app.services.management_expenses import month_key, next_month
from app.services.partnership_metrics import Factor, health_score

# BH4/BH7: H1-H12 in source order with their weights (Σ 100).
FACTORS = (
    Factor("revenue", "Revenue", 15, True),
    Factor("profit", "Profit", 15, True),
    Factor("cash_flow", "Cash flow", 10, True),
    Factor("sales_pipeline", "Sales pipeline", 10, True),
    Factor("student_growth", "Student growth", 8, True),
    Factor("enrollment", "Enrollment", 8, True),
    Factor("agent_growth", "Agent growth", 5, True),
    Factor("school_growth", "School growth", 5, True),
    Factor("universities", "University partnerships", 5, True),
    Factor("productivity", "Employee productivity", 7, True),
    Factor("marketing_roi", "Marketing ROI", 6, True),
    Factor("expenses", "Expenses", 6, True),
)
OPERATIONAL_KEYS = frozenset({"sales_pipeline", "student_growth", "enrollment", "agent_growth", "school_growth", "universities"})  # BH10
UNITS = {"revenue": "inr", "profit": "percent", "cash_flow": "inr", "productivity": "inr", "marketing_roi": "percent", "expenses": "inr"}
# BH4: each operational factor is a sum of mgmt-026 plan KPIs (PN5), plus new leads for the sales pipeline.
PLAN_KEYS = {
    "sales_pipeline": ("applications",), "student_growth": ("it_students", "school_students"), "enrollment": ("enrollments",),
    "agent_growth": ("agents",), "school_growth": ("school_mous",), "universities": ("universities",),
}  # fmt: skip
NOTHING = "Nothing recorded in either month"


def _clamp(value: float) -> int:
    return max(0, min(100, floor(value + 0.5 + 1e-9)))


def growth_score(current: Decimal, previous: Decimal) -> tuple[int, float | None] | None:
    """BH5/BH6: (score, growth %) for a month-on-month change; −10% → 0, flat → 50, +10% → 100. Nothing before: 100 for new activity
    (no growth % to show), and no basis at all when both months are 0."""
    if previous == 0:
        return None if current == 0 else (100 if current > 0 else 0, None)
    growth = float((current - previous) / abs(previous) * 100)
    return _clamp(50 + 5 * growth), round(growth, 1)


def margin_score(margin: float) -> int:
    """BH5 H2: −20% → 0, 0% → 40, 15% → 70, 30% → 100."""
    return _clamp(2 * (margin + 20))


def roi_score(roi: float) -> int:
    """BH5 H11: −100% → 0, 0% → 50, +100% → 100."""
    return _clamp(50 + roi / 2)


def expense_score(gap: float) -> int:
    """BH5 H12: `gap` = expense growth − revenue growth in points; expenses growing 10 points slower than revenue → 100."""
    return _clamp(50 - 5 * gap)


def rag(score: int) -> str:
    """BH9: green ≥ 70, amber 40-69, red < 40."""
    return "green" if score >= 70 else "amber" if score >= 40 else "red"


def _figure(current=None, previous=None, change=None, score=None, note=None) -> dict:
    return {"current": current, "previous": previous, "change": change, "score": score, "note": note}


def _growth(current: Decimal, previous: Decimal, note: str = NOTHING) -> dict:
    scored = growth_score(current, previous)
    if scored is None:
        return _figure(current, previous, note=note)
    return _figure(current, previous, scored[1], scored[0])


def _percent(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def _operational(db: AsyncSession, month: date, previous: date, end: date) -> dict[str, dict]:
    keys = {key for parts in PLAN_KEYS.values() for key in parts}
    now, before = await metrics.plan_actuals(db, keys, month, end), await metrics.plan_actuals(db, keys, previous, month)
    lo, mid, hi = metrics._ist_start(previous), metrics._ist_start(month), metrics._ist_start(end)
    leads = (await db.execute(select(func.count().filter(Enquiry.created_at >= mid), func.count().filter(Enquiry.created_at < mid)).where(Enquiry.created_at >= lo, Enquiry.created_at < hi))).one()
    out = {}
    for key, parts in PLAN_KEYS.items():
        current, earlier = sum(now[p] for p in parts), sum(before[p] for p in parts)
        if key == "sales_pipeline":
            current, earlier = current + leads[0], earlier + leads[1]
        out[key] = _growth(Decimal(current), Decimal(earlier))
    return out


async def _finance(db: AsyncSession, user: User, month: date, previous: date, end: date) -> dict[str, dict]:
    pnl = (await management_pnl.dashboard(db, user, month, "month"))["total"]
    pnl_before = (await management_pnl.dashboard(db, user, previous, "month"))["total"]
    revenue, revenue_before = Decimal(pnl["revenue"]), Decimal(pnl_before["revenue"])
    expenses, expenses_before = Decimal(pnl["expenses"]), Decimal(pnl_before["expenses"])
    out = {"revenue": _growth(revenue, revenue_before, "No revenue in either month")}

    margin = pnl["margin"]
    out["profit"] = _figure(_percent(margin), _percent(pnl_before["margin"]), score=margin_score(margin)) if margin is not None else _figure(note="No revenue in the month")

    cash = dict((await db.execute(select(FinanceBalance.month, FinanceBalance.cash_bank).where(FinanceBalance.month.in_((month, previous))))).all())
    if cash.get(month) is None or cash.get(previous) is None:
        out["cash_flow"] = _figure(cash.get(month), cash.get(previous), note="Cash/bank balance not entered for both months")
    else:
        out["cash_flow"] = _growth(cash[month], cash[previous])

    heads = dict((await db.execute(select(SalaryMonthTotal.month, func.sum(SalaryMonthTotal.headcount)).where(SalaryMonthTotal.month.in_((month, previous))).group_by(SalaryMonthTotal.month))).all())
    if not heads.get(month) or not heads.get(previous):
        out["productivity"] = _figure(note="Salary headcount not entered for both months")
    else:
        per_head, per_head_before = (revenue / heads[month]).quantize(ledger.CENTS), (revenue_before / heads[previous]).quantize(ledger.CENTS)
        out["productivity"] = _growth(per_head, per_head_before, "No revenue in either month")

    spend = sum((await management_marketing._spend(db, month, end)).values(), Decimal(0))
    returned = sum((await management_marketing._revenue(db, month, end)).values(), Decimal(0))
    roi = management_marketing.roi(returned, spend)
    out["marketing_roi"] = _figure(_percent(roi), score=roi_score(roi)) if roi is not None else _figure(note="No marketing spend tagged in the month")

    if revenue_before > 0 and expenses_before > 0:
        gap = float((expenses - expenses_before) / expenses_before * 100 - (revenue - revenue_before) / revenue_before * 100)
        out["expenses"] = _figure(expenses, expenses_before, round(gap, 1), expense_score(gap))
    else:
        out["expenses"] = _figure(expenses, expenses_before, note="Needs revenue and expenses in the earlier month")
    return out


async def health(db: AsyncSession, user: User, month: date, this_month: date) -> dict:
    """BH1-BH11 for `month` (its 1st) against the month before. The finance tier among the readers (partner) gets all twelve factors;
    super_admin the operational six, scored on their own (BH1)."""
    previous, end = (month - timedelta(days=1)).replace(day=1), next_month(month)
    full = can_view_finance(user)
    figures = await _operational(db, month, previous, end)
    if full:
        figures |= await _finance(db, user, month, previous, end)
    factors = tuple(f for f in FACTORS if full or f.key in OPERATIONAL_KEYS)
    values = {key: f["score"] / 100 for key, f in figures.items() if f["score"] is not None}
    score, points = health_score(values, factors) if values else (None, {})
    return {
        "month": month_key(month), "previous_month": month_key(previous), "partial": month == this_month,
        "scope": "business" if full else "operational", "score": score, "rag": rag(score) if score is not None else None,
        "factors": [
            {
                "key": f.key, "label": f.label, "tier": "operational" if f.key in OPERATIONAL_KEYS else "finance", "weight": f.weight,
                "unit": UNITS.get(f.key, "count"), **figures[f.key], "points": points.get(f.key),
                "rag": rag(figures[f.key]["score"]) if figures[f.key]["score"] is not None else None,
            }
            for f in factors
        ],
    }  # fmt: skip
