"""mgmt-026 (spec PN1-PN16): EVID-017 §25's next month plan and §26's target vs actual.

A plan is one IST month's items per vertical. A KPI item's actual is counted live by `management_metrics` (revenue is mgmt-009's P&L
figure, partners only, PN7); a free-text item is ticked done. The operational tier (partner, super_admin) reads and writes; every write
locks the plan row, adds a `mgmt.plan` audit row (field names only) and the routes in `api/management_plans.py` commit once. Logs carry
ids and field names, never item text. Spec: docs/superpowers/specs/2026-10-14-mgmt-026-next-month-plan-design.md.
"""

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ManagementPlan, ManagementPlanItem, ManagementTask, User
from app.services import management_metrics as metrics
from app.services import management_pnl
from app.services.bdm_travel import india_today
from app.services.ledger import field_error
from app.services.management_access import can_view_partner_only
from app.services.management_discussions import person
from app.services.management_expenses import month_key, next_month

logger = logging.getLogger("app.management")
VERTICALS = {"abroad": "Abroad Education", "it": "IT Training", "school": "Schools", "recruitment": "Recruitment", "other": "Other"}
MONTHS_AHEAD = 12  # PN2
COUNT_MAX = Decimal(1_000_000)
AMOUNT_MAX = Decimal(1_000_000_000_000)
ITEM_FIELDS = ("vertical", "text", "kpi", "target", "done")

NOT_FOUND = "Plan not found"
ITEM_NOT_FOUND = "Plan item not found"
DUPLICATE = "This month already has a plan"
CLOSED = "This plan is closed. Reopen it to change it."
REVENUE_PARTNERS_ONLY = "Only partners can set a revenue target"
_VERTICAL_ORDER = case({key: index for index, key in enumerate(VERTICALS)}, value=ManagementPlanItem.vertical)


def log(event: str, user: User, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entity_id": str(entity_id), **extra}})


# --- months (PN2, PN6) ---------------------------------------------------------------------------------------------------------
def parse_month(value: str) -> date:
    """A route-validated "YYYY-MM" as its 1st day."""
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def add_months(month_start: date, months: int) -> date:
    index = month_start.year * 12 + month_start.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def window() -> tuple[date, date]:
    """The months a plan can be created for: this IST month up to 12 ahead."""
    first = india_today().replace(day=1)
    return first, add_months(first, MONTHS_AHEAD)


def label(month_start: date) -> str:
    return month_start.strftime("%B %Y")


def state(month_start: date) -> str:
    current = india_today().replace(day=1)
    return "upcoming" if month_start > current else "running" if month_start == current else "ended"


def achievement(actual: Decimal, target: Decimal) -> int:
    """PN6: actual ÷ target, a whole per cent rounded half-up (27 of 30 = 90)."""
    return int((actual * 100 / target).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --- visibility (PN7) ----------------------------------------------------------------------------------------------------------
def visible(user: User) -> list:
    """Revenue items exist only for partners: everyone else's queries never fetch them."""
    if can_view_partner_only(user):
        return []
    return [or_(ManagementPlanItem.kpi.is_(None), ManagementPlanItem.kpi != metrics.REVENUE_KPI)]


def kpi_options(user: User) -> list[dict]:
    partner = can_view_partner_only(user)
    return [{"key": key, "label": lbl, "unit": unit, "definition": text} for key, (lbl, unit, text) in metrics.PLAN_KPIS.items() if partner or key != metrics.REVENUE_KPI]


# --- reads ---------------------------------------------------------------------------------------------------------------------
def _summary_counts(user: User):
    """(plan id, items, KPI items, free-text items done) over the items the caller may see."""
    return (
        select(
            ManagementPlanItem.plan_id,
            func.count().label("item_total"),
            func.count().filter(ManagementPlanItem.kpi.is_not(None)).label("kpi_total"),
            func.count().filter(ManagementPlanItem.done.is_(True)).label("done_total"),
        )
        .where(*visible(user))
        .group_by(ManagementPlanItem.plan_id)
        .subquery()
    )


async def _plans(db: AsyncSession, user: User, *where) -> list[dict]:
    counts = _summary_counts(user)
    rows = (
        await db.execute(
            select(ManagementPlan, User, counts.c.item_total, counts.c.kpi_total, counts.c.done_total)
            .join(User, User.id == ManagementPlan.created_by_user_id)
            .outerjoin(counts, counts.c.plan_id == ManagementPlan.id)
            .where(*where)
            .order_by(ManagementPlan.month.desc())
            .execution_options(populate_existing=True)
        )
    ).all()
    return [
        {"id": plan.id, "month": month_key(plan.month), "status": plan.status, "label": label(plan.month), "item_count": items or 0, "kpi_count": kpis or 0,
         "done_count": done or 0, "created_by": person(creator), "updated_at": plan.updated_at}
        for plan, creator, items, kpis, done in rows
    ]  # fmt: skip


async def plans(db: AsyncSession, user: User) -> dict:
    return {"items": await _plans(db, user)}


async def _items(db: AsyncSession, user: User, plan: ManagementPlan) -> list[ManagementPlanItem]:
    stmt = select(ManagementPlanItem).where(ManagementPlanItem.plan_id == plan.id, *visible(user))
    return list((await db.scalars(stmt.order_by(_VERTICAL_ORDER, ManagementPlanItem.position).execution_options(populate_existing=True))).all())


def item_out(item: ManagementPlanItem, task_count: int) -> dict:
    return {"id": item.id, "vertical": item.vertical, "text": item.text, "kpi": item.kpi, "target": item.target, "done": item.done, "task_count": task_count, "updated_at": item.updated_at}


async def _task_counts(db: AsyncSession, ids: list) -> dict:
    if not ids:
        return {}
    stmt = select(ManagementTask.source_id, func.count()).where(ManagementTask.source == "plan", ManagementTask.source_id.in_(ids)).group_by(ManagementTask.source_id)
    return dict((await db.execute(stmt)).all())


async def detail(db: AsyncSession, user: User, month_start: date) -> dict:
    found = await _plans(db, user, ManagementPlan.month == month_start)
    if not found:
        raise HTTPException(404, NOT_FOUND)
    plan = await db.get_one(ManagementPlan, found[0]["id"])
    items = await _items(db, user, plan)
    tasks = await _task_counts(db, [item.id for item in items])
    return {**found[0], "items": [item_out(item, tasks.get(item.id, 0)) for item in items]}


async def one_item(db: AsyncSession, item: ManagementPlanItem) -> dict:
    await db.refresh(item)
    return item_out(item, (await _task_counts(db, [item.id])).get(item.id, 0))


async def progress(db: AsyncSession, user: User, month_start: date) -> dict:
    """§26: every KPI item's target, live actual and achievement; the free-text items' done tally."""
    plan = await db.scalar(select(ManagementPlan).where(ManagementPlan.month == month_start))
    if plan is None:
        raise HTTPException(404, NOT_FOUND)
    items = await _items(db, user, plan)
    end = next_month(month_start)
    keys = {item.kpi for item in items if item.kpi}
    actuals: dict[str, Decimal] = {key: Decimal(value) for key, value in (await metrics.plan_actuals(db, keys, month_start, end)).items()}
    if metrics.REVENUE_KPI in keys:  # only ever a partner's (visible)
        actuals[metrics.REVENUE_KPI] = (await management_pnl.dashboard(db, user, month_start, "month"))["total"]["revenue"]
    rows = []
    for item in items:
        if item.kpi is None or item.target is None:
            continue
        kpi_label, unit, _ = metrics.PLAN_KPIS[item.kpi]
        actual = actuals[item.kpi]
        rows.append({"item_id": item.id, "vertical": item.vertical, "text": item.text, "kpi": item.kpi, "kpi_label": kpi_label, "unit": unit,
                     "target": item.target, "actual": actual, "achievement": achievement(actual, item.target)})  # fmt: skip
    free = [item for item in items if item.kpi is None]
    return {
        "month": month_key(month_start), "label": label(month_start), "state": state(month_start), "start": month_start, "end": end - timedelta(days=1),
        "rows": rows, "free_text": {"total": len(free), "done": sum(item.done for item in free)},
    }  # fmt: skip


# --- writes --------------------------------------------------------------------------------------------------------------------
def check_window(month_start: date) -> None:
    first, last = window()
    if not first <= month_start <= last:
        raise field_error("month", "Choose this month or one of the next 12")


async def lock(db: AsyncSession, month_start: date, *, writable: bool = True) -> ManagementPlan:
    """The plan row locked for a write (PN11); with `writable`, a closed plan is a 409 (PN3)."""
    plan = await db.scalar(select(ManagementPlan).where(ManagementPlan.month == month_start).with_for_update().execution_options(populate_existing=True))
    if plan is None:
        raise HTTPException(404, NOT_FOUND)
    if writable and plan.status == "closed":
        raise HTTPException(409, CLOSED)
    return plan


async def load_item(db: AsyncSession, user: User, plan: ManagementPlan, item_id) -> ManagementPlanItem:
    """An item of this plan only (another month's id is a 404), and one the caller may see (PN7)."""
    stmt = select(ManagementPlanItem).where(ManagementPlanItem.id == item_id, ManagementPlanItem.plan_id == plan.id, *visible(user))
    item = await db.scalar(stmt.execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, ITEM_NOT_FOUND)
    return item


def check_item(user: User, item: dict, changes: dict) -> None:
    """PN4/PN7 on the merged state; `changes` is what the client sent (a create sends everything)."""
    kpi, target = item["kpi"], item["target"]
    if kpi == metrics.REVENUE_KPI and "kpi" in changes and not can_view_partner_only(user):
        raise HTTPException(403, REVENUE_PARTNERS_ONLY)
    if kpi is None and target is not None:
        raise field_error("target", "Only a KPI item has a target")
    if kpi is not None and target is None:
        raise field_error("target", "Give the target for this KPI")
    if kpi is not None and target is not None:
        if metrics.PLAN_KPIS[kpi][1] == "count" and (target != target.to_integral_value() or target > COUNT_MAX):
            raise field_error("target", "Give a whole number from 1 to 1,000,000")
        if target > AMOUNT_MAX:
            raise field_error("target", "Give an amount up to ₹1,000,000,000,000")
    if kpi is not None and item["done"]:
        raise field_error("done", "Only a free-text item is marked done")


def merged(item: ManagementPlanItem | None, changes: dict) -> dict:
    """The item after `changes`. Turning an item into a KPI item clears its done tick unless the client sent one (PN4)."""
    before = {field: getattr(item, field) for field in ITEM_FIELDS} if item else {"kpi": None, "target": None, "done": False}
    state = {**before, **changes}
    if state["kpi"] is not None and "done" not in changes:
        state["done"] = False
    return state


async def next_position(db: AsyncSession, plan: ManagementPlan) -> int:
    """PN12: append order, under the plan lock."""
    return (await db.scalar(select(func.max(ManagementPlanItem.position)).where(ManagementPlanItem.plan_id == plan.id)) or 0) + 1
