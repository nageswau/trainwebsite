"""mgmt-023 (EVID-017 §19, spec UD1-UD14): the University partnership dashboard -- the twelve §19 KPIs, the Management §19 pipeline and
the expected partnerships. A read-through of the UPC figures over every university (UD2), so the totals equal upc-029's global dashboard
for the same period: its pipeline and Active column (`global_figures`), upc-018's funnel totals (`ranking`), upc-019's commission and
upc-023's expected rows. Nothing is stored, logged or audited; a fixed number of statements."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.partnership_expected import _row, chosen_rows, expected_rows, window_figures
from app.api.partnership_performance import commission_sums, commission_totals, ranking
from app.models import University, User
from app.services.management_access import can_view_university_commission
from app.services.partnership_metrics import global_figures
from app.services.university_search import _exclusivity

NO_TEAM: frozenset = frozenset()  # both readers are global (upc-018 PF6)
NEXT_MONTH_ROWS = 25  # UD12
# UD5: a KPI counts the universities at or past the first pipeline step it names (an index into upc-029's `pipeline.steps`).
FROM_STEP = (("contacted", "Contacted", 1), ("meetings", "Meetings", 2), ("negotiations", "Negotiations", 4), ("mous", "MoUs", 5), ("signed", "Signed", 6))


async def _exclusive(db: AsyncSession) -> int:
    """UD7: active, not-lost universities with an in-force exclusive agreement now (upc-025 MP8)."""
    stmt = select(func.count()).select_from(University).where(University.active.is_(True), University.lost_at.is_(None), _exclusivity("exclusive"))
    return int((await db.scalar(stmt)) or 0)


async def dashboard(db: AsyncSession, user: User, first: date, last: date, today: date) -> dict:
    figures = await global_figures(db, user, NO_TEAM, today)
    ranked, totals, _ = await ranking(db, user, NO_TEAM, first, last)
    steps = [step["count"] for step in figures["pipeline"]["steps"]]
    kpis = [{"key": "identified", "label": "Universities identified", "value": figures["pipeline"]["total"]}]  # UD4
    kpis += [{"key": key, "label": label, "value": sum(steps[index:])} for key, label, index in FROM_STEP]
    kpis += [
        {"key": "active", "label": "Active", "value": figures["active"]["count"]},  # UD6
        {"key": "exclusive", "label": "Exclusive", "value": await _exclusive(db)},
        {"key": "countries", "label": "Countries", "value": len(figures["active"]["countries"])},  # UD8
        {"key": "applications", "label": "Applications", "value": totals["applications"]},  # UD9
        {"key": "enrollments", "label": "Enrollments", "value": totals["enrolled"]},
    ]
    rows = await expected_rows(db, user, NO_TEAM)
    upcoming = chosen_rows(rows, "next_month", today)
    out = {
        "today": today, "from_": first, "to": last, "kpis": kpis, "pipeline": figures["pipeline"],
        "expected": {
            "windows": window_figures(rows, today), "undated": sum(1 for uni, *_ in rows if uni.expected_agreement_date is None),
            "next_month": {"total": len(upcoming), "items": [_row(*r) for r in upcoming[:NEXT_MONTH_ROWS]]},
        },
    }  # fmt: skip
    if can_view_university_commission(user):  # UD10 (M3): the partners only; super_admin has no finance figures (M13)
        out["revenue"] = commission_totals(await commission_sums(db, [uni.id for uni, *_ in ranked], first, last))
    return out
