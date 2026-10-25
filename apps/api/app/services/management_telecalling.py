"""mgmt-019 (EVID-017 §14, spec TC1-TC16): the company-wide Telecalling dashboard -- the eight §14 figures, telecaller conversion and the
Calls → Interested → Counseling → Registration chain, per telecaller, per team and for the company.

A thin wrapper over the Telecaller CRM's own counts: `telecaller_metrics.flow_counts_by_user` (tel-021) and `leads_received` (tel-023
P1), so the company totals equal the sum of the tel-023 rows (AC1). Interested and Lost, which tel-021 does not count, are one grouped
query over the stage history, the same shape as its Qualified (D11). Reads only; counts and staff names only (TC14)."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import LeadStageHistory, TelecallerProfile, User
from app.services import telecaller_metrics
from app.services.bdm_activities import day_range
from app.services.telecaller import TEAM_LABEL, TEAMS

# (response key, tel-021 flow count) for the figures `flow_counts_by_user` already has (TC4, TC6-TC8).
FLOW = (
    ("calls", "calls"),
    ("connected", "connected_calls"),
    ("follow_ups", "follow_ups_completed"),
    ("appointments", "new_appointments"),
    ("converted", "converted_leads"),
    ("counselling", "counselor_appointments"),
)
FIGURES = ("leads", "calls", "connected", "interested", "follow_ups", "appointments", "converted", "lost", "counselling")
CHAIN = (
    ("calls", "Calls", "calls"),
    ("interested", "Interested", "interested"),
    ("counselling", "Counseling", "counselling"),
    ("registration", "Registration", "converted"),
)  # (key, the source's word, the figure it reads)


def _share(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def _with_conversion(figures: dict) -> dict:
    """TC10: converted ÷ leads assigned, one decimal; None when no lead was assigned."""
    return figures | {"conversion": _share(figures["converted"], figures["leads"])}


def _sum(rows: list[dict]) -> dict:
    return _with_conversion({key: sum(row[key] for row in rows) for key in FIGURES})


async def _outcomes(db: AsyncSession, user_ids: list[UUID], start, end) -> dict[UUID | None, tuple[int, int]]:
    """TC5 / TC9: each telecaller's own stage moves to Interested and into a closed outcome in [start, end)."""
    actor = LeadStageHistory.actor_user_id
    rows = await db.execute(
        select(actor, func.count().filter(LeadStageHistory.to_stage == "interested"), func.count().filter(LeadStageHistory.to_stage.in_(CLOSED - {"duplicate"})))  # ccrm-006 D10
        .where(actor.in_(user_ids), LeadStageHistory.created_at >= start, LeadStageHistory.created_at < end)
        .group_by(actor)
    )
    return {user_id: (interested, lost) for user_id, interested, lost in rows}


async def dashboard(db: AsyncSession, first: date, last: date) -> dict:
    """TC1-TC12 over the IST days `first`..`last` (the route has applied tel-023's range rules)."""
    start, end = day_range(first)[0], day_range(last)[1]
    people = (
        await db.execute(select(User.id, User.full_name, User.active, TelecallerProfile.team).join(TelecallerProfile, TelecallerProfile.user_id == User.id).where(User.role == "telecaller"))
    ).all()
    ids = [person.id for person in people]
    flows = await telecaller_metrics.flow_counts_by_user(db, ids, start, end)
    outcomes = await _outcomes(db, ids, start, end)
    rows = []
    for person in people:
        interested, lost = outcomes.get(person.id, (0, 0))
        figures = {key: flows[person.id][count] for key, count in FLOW} | {
            "leads": await telecaller_metrics.leads_received(db, person.id, start, end),
            "interested": interested,
            "lost": lost,
        }
        rows.append({"user_id": person.id, "full_name": person.full_name, "team": TEAM_LABEL.get(person.team, person.team), "active": person.active, **_with_conversion(figures)})
    rows.sort(key=lambda row: (row["full_name"].casefold(), str(row["user_id"])))
    totals = _sum(rows)
    teams = []
    for team in TEAMS:  # TC12: both teams, even one with no telecallers
        members = [row for row in rows if row["team"] == TEAM_LABEL[team]]
        teams.append({"team": team, "label": TEAM_LABEL[team], "telecallers": len(members), **_sum(members)})
    # TC11 (QA19-03): each later step's share of the calls the chain starts from. The steps are activity in the period, not a cohort
    # (counselling bookings are not a subset of Interested moves), so a share of the step before could read over 100%.
    chain = [{"key": key, "label": label, "value": totals[figure], "share": None if index == 0 else _share(totals[figure], totals["calls"])} for index, (key, label, figure) in enumerate(CHAIN)]
    return {"date_from": first, "date_to": last, "totals": totals, "teams": teams, "telecallers": rows, "chain": chain}
