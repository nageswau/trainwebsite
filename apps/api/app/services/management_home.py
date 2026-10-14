"""mgmt-031 (EVID-017 §31 and §2, spec HM1-HM14): the partner home -- "Today's Business Snapshot" (7 figures) and the nine §31 panels,
each a read-through of the merged dashboard it links to, so every figure equals its page's (AC): mgmt-009's P&L, mgmt-013's
accounts, mgmt-003's snapshot, mgmt-026's plan KPIs, mgmt-030's health score and the mgmt-027/028/029 lists. Money is never queried
for super_admin (HM2, M13); the keys are left out of the response, not nulled. Read-only: nothing is stored, logged or audited.
Spec: docs/superpowers/specs/2026-10-14-mgmt-031-partner-home-design.md."""

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FinanceBalance, ManagementDiscussion, ManagementPlan, ManagementTask, User
from app.services import accounts, management_discussions, management_health, management_meetings, management_plans, management_pnl, management_tasks
from app.services import management_metrics as metrics
from app.services.management_access import can_view_finance
from app.services.management_expenses import month_key, next_month

PANEL_ROWS = 5  # HM6-HM12: each list panel shows its page's first five rows


async def _cash_month(db: AsyncSession, this_month: date) -> FinanceBalance | None:
    """HM4/HM9: the latest month up to this one with a cash/bank balance entered (balances never carry forward, AD7)."""
    stmt = select(FinanceBalance).where(FinanceBalance.month <= this_month, FinanceBalance.cash_bank.is_not(None)).order_by(FinanceBalance.month.desc()).limit(1)
    return await db.scalar(stmt)


async def _money(db: AsyncSession, user: User, this_month: date, today: date) -> tuple[dict, dict]:
    """The partner's money: the snapshot's four figures (HM4) and the financial position (HM9)."""
    pnl = (await management_pnl.dashboard(db, user, this_month, "month"))["total"]
    balance = await _cash_month(db, this_month)
    owed = await accounts.receivables(db, today)
    snapshot = {
        "revenue": pnl["revenue"], "expenses": pnl["expenses"], "profit": pnl["contribution"],
        "cash": {"amount": balance.cash_bank if balance else None, "month": month_key(balance.month) if balance else None},
    }  # fmt: skip
    position = {
        "receivables": owed["total"], "receivables_overdue": owed["overdue"], "pending_invoices": await accounts.pending_invoices(db),
        "balance_month": month_key(balance.month) if balance else None,
        **{f: getattr(balance, f) if balance else None for f in ("cash_bank", "payables", "tax_liabilities")},
    }  # fmt: skip
    return snapshot, position


async def _overdue_decisions(db: AsyncSession, today: date) -> int:
    """HM5: pending decisions (MD12: a named person, open or in progress) past their deadline."""
    pending = (ManagementDiscussion.responsible_user_id.is_not(None), ManagementDiscussion.status.in_(management_discussions.PENDING))
    return await db.scalar(select(func.count()).select_from(ManagementDiscussion).where(*pending, ManagementDiscussion.deadline < today)) or 0


async def _targets(db: AsyncSession, user: User, this_month: date) -> dict | None:
    """HM8: this month's plan progress (mgmt-026), the first rows; no plan, None."""
    try:
        progress = await management_plans.progress(db, user, this_month)
    except HTTPException as e:
        if e.status_code == 404:
            return None
        raise
    return {"month": progress["month"], "label": progress["label"], "rows": progress["rows"][:PANEL_ROWS], "row_total": len(progress["rows"]), "free_text": progress["free_text"]}


async def home(db: AsyncSession, user: User, today: date) -> dict:
    """HM1-HM14 for an operational-tier caller (the route checks the tier). Partners also get the money (finance tier)."""
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    following = next_month(this_month)
    business = can_view_finance(user)

    students = (await metrics.snapshot(db, today))["total_students"]
    counts = await metrics.plan_actuals(db, {"applications", "enrollments"}, this_month, following)
    snapshot: dict = {"students": students, "applications": counts["applications"], "enrollments": counts["enrollments"]}
    out: dict = {"as_of": today, "month": month_key(this_month), "label": management_plans.label(this_month), "scope": "business" if business else "operational"}

    health = await management_health.health(db, user, last_month, this_month)
    tasks = await management_tasks.page(db, where=[ManagementTask.owner_user_id == user.id], band=None, limit=PANEL_ROWS, offset=0)
    everyone = await management_tasks.counts(db, [], today)
    urgent = [
        {"key": "overdue_tasks", "label": "Overdue tasks", "count": everyone["overdue"]},
        {"key": "overdue_decisions", "label": "Overdue decisions", "count": await _overdue_decisions(db, today)},
        {"key": "red_health", "label": "Health factors in Red", "count": sum(f["rag"] == "red" for f in health["factors"])},
    ]
    if business:
        money, position = await _money(db, user, this_month, today)
        snapshot |= money
        out["financial_position"] = position
        urgent.append({"key": "overdue_receivables", "label": "Overdue receivables", "count": 1 if position["receivables_overdue"] > 0 else 0, "amount": position["receivables_overdue"]})

    next_plan = await management_plans._plans(db, user, ManagementPlan.month == following)
    return out | {
        "snapshot": snapshot,
        "urgent": [u for u in urgent if u["count"] > 0],
        "pending_decisions": await management_discussions.page(db, status=None, responsible=None, pending=True, limit=PANEL_ROWS, offset=0),
        "meetings": await management_meetings.calendar(db, date_from=today, date_to=today, kind=None, status=None),
        "targets": await _targets(db, user, this_month),
        "growth": {"month": health["month"], "score": health["score"], "rag": health["rag"], "factors": [{k: f[k] for k in ("key", "label", "change", "rag")} for f in health["factors"]]},
        "my_tasks": {"items": tasks["items"], "counts": tasks["counts"]},
        "recent_discussions": await management_discussions.page(db, status=None, responsible=None, pending=False, limit=PANEL_ROWS, offset=0),
        "next_plan": {"month": month_key(following), "label": management_plans.label(following), "plan": next_plan[0] if next_plan else None},
    }
