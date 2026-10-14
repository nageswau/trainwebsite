"""mgmt-032 (EVID-017 §32, spec MR1-MR14): the Monthly Business Review. A beat job on the 1st (IST) drafts the previous month; partners
can generate or regenerate a draft, write the §9 Problems and §10 narrative, then finalise. The computed sections are a snapshot of the
merged dashboards' figures as a partner sees them (mgmt-009 P&L, mgmt-010 expenses, mgmt-011 salaries, mgmt-012 marketing, mgmt-014
investments, mgmt-026 KPIs), copied when drafted, so a later ledger change never moves a review (AC2) and the screen and the PDF
render the same stored document (AC3). Spec: docs/superpowers/specs/2026-10-14-mgmt-032-monthly-review-design.md."""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Investment, ManagementPlan, MonthlyReview, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services import investments, ledger, management_audit, management_marketing, management_plans, management_pnl, salaries
from app.services import management_metrics as metrics
from app.services.management_expenses import dashboard as expense_dashboard
from app.services.management_expenses import month_key, next_month

logger = logging.getLogger("app.management")

PROBLEM_KEYS = {"went_wrong": "What went wrong?", "delayed": "What is delayed?", "intervention": "What needs management intervention?"}
NEXT_MONTH_KEYS = {"initiatives": "New initiatives", "hiring": "Hiring", "investments": "Investments", "partnerships": "Partnerships"}
NARRATIVE_KEYS = (*PROBLEM_KEYS, *NEXT_MONTH_KEYS)
REVENUE_LINES = (("abroad", "Abroad Education"), ("it", "IT Training"), ("recruitment", "Recruitment"), ("other", "Other"))
OTHER_REVENUE = ("school", "other", "shared")  # MR5: everything outside the three named verticals
# MR6: the mgmt-010 heads in §32 order; §32's "Operations" has no head of its own, so the Technology head (internet, software) stands in.
EXPENSE_LINES = (
    ("salaries", "Salaries"), ("rent", "Rent"), ("marketing", "Marketing"), ("technology", "Operations (technology)"),
    ("trainers", "Trainers"), ("travel", "Travel"), ("commissions", "Commissions"), ("other", "Other"),
)  # fmt: skip
SALES_KPIS = {"students": "it_students", "applications": "applications", "enrollments": "enrollments", "placements": "placements"}
PARTNERSHIP_KPIS = {"agents": "agents", "schools": "school_mous", "universities": "universities", "companies": "companies"}
MARKETING_FIGURES = ("budget", "spend", "leads", "customers", "conversion", "revenue", "roi")

NOT_FOUND = "No review for this month yet"
FINAL = "This review is final and cannot change"
UNFINISHED = "Only a finished month can be reviewed"
ACTION_URL = "/management/reviews/{month}"


def _plain(value):
    """JSON-safe, as the API would send it: money as its exact decimal string, dates as ISO."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def check_finished(month: date) -> None:
    if month >= ledger.today().replace(day=1):
        raise HTTPException(422, UNFINISHED)


# --- the computed sections (MR5-MR13) ------------------------------------------------------------------------------------------
async def _next_month(db: AsyncSession, viewer: User, month: date) -> dict:
    """§10's computed parts: the next month's mgmt-026 KPI targets and its mgmt-012 marketing budget total."""
    plan = await db.scalar(select(ManagementPlan).where(ManagementPlan.month == month))
    items = await management_plans._items(db, viewer, plan) if plan else []
    targets = [
        {"vertical": management_plans.VERTICALS[i.vertical], "text": i.text, "kpi": metrics.PLAN_KPIS[i.kpi][0], "unit": metrics.PLAN_KPIS[i.kpi][1], "target": i.target}
        for i in items if i.kpi and i.target is not None
    ]  # fmt: skip
    budgets = await management_marketing._budgets(db, month)
    return {"month": month_key(month), "label": management_plans.label(month), "targets": targets, "budget": sum(budgets.values(), Decimal("0.00")) if budgets else None}


async def compute(db: AsyncSession, month: date) -> dict:
    """Sections 1-8 and §10's computed parts for `month` (its 1st), each the figure its own page shows a partner for that month."""
    viewer = User(role="partner")  # the review is partner-only (MR1): every figure is the partner's view, never stored or flushed
    end = next_month(month)
    pnl = await management_pnl.dashboard(db, viewer, month, "month")
    revenue = {row["key"]: row["revenue"] for row in pnl["rows"]}
    revenue["other"] = sum((revenue[k] for k in OTHER_REVENUE), Decimal("0.00"))
    expenses = await expense_dashboard(db, month)
    heads = {g["key"]: g["month"] for g in expenses["groups"]}
    marketing = (await management_marketing.dashboard(db, viewer, month))["totals"]
    counts = await metrics.plan_actuals(db, {*SALES_KPIS.values(), *PARTNERSHIP_KPIS.values()}, month, end)
    people = await salaries.month_view(db, month)
    entered = [row for row in people["rows"] if row["entered"]]
    headcount = people["totals"]["headcount"] if entered else None
    total = pnl["total"]
    in_month = await investments.totals(db, [Investment.invested_on >= month, Investment.invested_on < end])
    to_date = await investments.totals(db, [Investment.invested_on < end])
    return _plain({
        "revenue": {"lines": [{"key": k, "label": label, "amount": revenue[k]} for k, label in REVENUE_LINES], "total": total["revenue"]},
        "expenses": {"lines": [{"key": k, "label": label, "amount": heads[k]} for k, label in EXPENSE_LINES], "total": expenses["totals"]["month"]},
        "profitability": {"revenue": total["revenue"], "expenses": total["expenses"], "net_profit": total["contribution"], "margin": total["margin"]},
        "sales": {"leads": marketing["leads"], **{k: counts[kpi] for k, kpi in SALES_KPIS.items()}},
        "partnerships": {k: counts[kpi] for k, kpi in PARTNERSHIP_KPIS.items()},
        "people": {
            "employees": headcount,
            "departments": [{"name": r["department"]["name"], "headcount": r["headcount"], "total_cost": r["total_cost"]} for r in entered],
            "attendance": None, "attendance_note": "Not tracked",  # Q-31: no staff attendance is recorded anywhere
            "productivity": (total["revenue"] / headcount).quantize(ledger.CENTS) if headcount else None,
        },
        "marketing": {k: marketing[k] for k in MARKETING_FIGURES},
        "investments": {"new_count": in_month["count"], "new_amount": in_month["invested"], "total": to_date["invested"], "return": to_date["actual_return"], "roi": to_date["roi"]},
        "next_month": await _next_month(db, viewer, end),
    })  # fmt: skip


# --- reads ---------------------------------------------------------------------------------------------------------------------
async def _find(db: AsyncSession, month: date, *, lock: bool = False) -> MonthlyReview | None:
    stmt = select(MonthlyReview).where(MonthlyReview.month == month).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def load(db: AsyncSession, month: date, *, lock: bool = False) -> MonthlyReview:
    review = await _find(db, month, lock=lock)
    if review is None:
        raise HTTPException(404, NOT_FOUND)
    return review


async def _person(db: AsyncSession, user_id) -> dict | None:
    user = await db.get(User, user_id) if user_id else None
    return {"id": user.id, "full_name": user.full_name} if user else None


async def out(db: AsyncSession, review: MonthlyReview) -> dict:
    await db.refresh(review)  # `updated_at` is set by the database on update, so it is expired after a write
    return {
        "id": review.id, "month": month_key(review.month), "label": management_plans.label(review.month), "status": review.status,
        "snapshot": review.snapshot, "narrative": {k: (review.narrative or {}).get(k, "") for k in NARRATIVE_KEYS},
        "generated_at": review.generated_at, "finalised_at": review.finalised_at, "finalised_by": await _person(db, review.finalised_by_user_id),
        "updated_at": review.updated_at, "updated_by": await _person(db, review.updated_by_user_id),
    }  # fmt: skip


async def reviews(db: AsyncSession) -> dict:
    rows = (await db.scalars(select(MonthlyReview).order_by(MonthlyReview.month.desc()).limit(240))).all()  # 20 years of months
    return {"items": [{"month": month_key(r.month), "label": management_plans.label(r.month), "status": r.status, "generated_at": r.generated_at, "finalised_at": r.finalised_at} for r in rows]}


# --- writes (each locks the row first, so a finalise racing a save serialises and the loser sees 409) -------------------------
def _writable(review: MonthlyReview) -> MonthlyReview:
    if review.status == "final":
        raise HTTPException(409, FINAL)
    return review


async def generate(db: AsyncSession, month: date, actor: User | None, *, refresh: bool = True) -> tuple[MonthlyReview, bool]:
    """MR3/MR4: a draft for `month`, created (True) or, when `refresh`, its snapshot recomputed with the narrative kept (False).
    No commit: the caller commits once. A concurrent insert of the same month loses the unique constraint and refreshes instead."""
    snapshot = await compute(db, month)
    review = await _find(db, month, lock=True)
    if review is None:
        review = MonthlyReview(month=month, status="draft", snapshot=snapshot, narrative={}, updated_by_user_id=actor.id if actor else None)
        try:
            async with db.begin_nested():
                db.add(review)
        except IntegrityError:
            review = await _find(db, month, lock=True)
            if review is None:
                raise
        else:
            if actor:
                management_audit.record(db, actor, "mgmt.review", "create", str(review.id), fields=["snapshot"])
            return review, True
    if not refresh:
        return review, False
    _writable(review)
    review.snapshot, review.generated_at = snapshot, datetime.now(UTC)
    if actor:
        review.updated_by_user_id = actor.id
        management_audit.record(db, actor, "mgmt.review", "update", str(review.id), fields=["snapshot"])
    return review, False


async def update_narrative(db: AsyncSession, actor: User, month: date, changes: dict[str, str]) -> MonthlyReview:
    review = _writable(await load(db, month, lock=True))
    narrative = {k: (review.narrative or {}).get(k, "") for k in NARRATIVE_KEYS}
    changed = sorted(k for k, v in changes.items() if narrative[k] != v.strip())
    if changed:
        review.narrative = narrative | {k: changes[k].strip() for k in changed}
        review.updated_by_user_id = actor.id
        management_audit.record(db, actor, "mgmt.review", "update", str(review.id), fields=changed)  # names only: the text is the partners'
    return review


async def finalise(db: AsyncSession, actor: User, month: date) -> MonthlyReview:
    """MR13/MR14: needs every Problems answer; freezes the stored snapshot as it is; every active partner gets a link (no figures)."""
    review = _writable(await load(db, month, lock=True))
    missing = [label for k, label in PROBLEM_KEYS.items() if not (review.narrative or {}).get(k)]
    if missing:
        raise HTTPException(422, f"Answer every Problems question before finalising: {', '.join(missing)}")
    review.status, review.finalised_at, review.finalised_by_user_id, review.updated_by_user_id = "final", datetime.now(UTC), actor.id, actor.id
    management_audit.record(db, actor, "mgmt.review", "complete", str(review.id), fields=["status"])
    title = f"Monthly business review for {management_plans.label(month)} is final"
    for partner in (await db.scalars(select(User).where(User.role == "partner", User.active.is_(True)))).all():
        note = Notification(user_id=partner.id, title=title, body=f"{actor.full_name} finalised it. Open the review to read it.", read=False, action_url=ACTION_URL.format(month=month_key(month)))
        db.add(note)
        await queue_deliveries(db, note, partner, channels=["email"])
    return review


# --- the beat job (MR3, AC1) ---------------------------------------------------------------------------------------------------
async def draft_previous_month(db: AsyncSession, today: date) -> bool:
    """Drafts the IST month before `today`'s unless a review for it exists (never overwritten); True when one was created."""
    month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    _, created = await generate(db, month, None, refresh=False)
    await db.commit()
    if created:
        logger.info("monthly_review_drafted", extra={"extra_fields": {"month": month_key(month)}})
    return created


async def run_monthly_reviews() -> bool:
    """The beat task's entry point: its own session, today's IST date."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await draft_previous_month(db, ledger.today())
