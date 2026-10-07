"""tel-023 (DEC-SCOPE-109, spec §2-§4): the manager performance comparison -- Appendix B P1-P6 per telecaller in scope over a date range.

Every figure comes from `telecaller_metrics` (P2-P6 are tel-021's flow counts over the whole range, so each equals the sum of the daily
figures; P1 is `leads_received`). One `flow_counts` call per telecaller: tel-024 brings a grouped variant to that module, to switch to
once it merges. Reads only; the CSV route owns its audit write."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelecallerProfile, User
from app.services import telecaller_metrics as metrics
from app.services.bdm_activities import day_range
from app.services.telecaller import TEAM_LABEL, TEAMS, admin_team_filter, creatable_teams, team_filter

COUNTS = ("leads", "calls", "connected", "qualified", "appointments", "conversions")
SORTS = ("name", *COUNTS)
COLUMNS = [
    {"key": "full_name", "label": "Telecaller"}, {"key": "team", "label": "Team"}, {"key": "status", "label": "Status"},
    {"key": "leads", "label": "Leads"}, {"key": "calls", "label": "Calls"}, {"key": "connected", "label": "Connected"},
    {"key": "qualified", "label": "Qualified"}, {"key": "appointments", "label": "Appointments"}, {"key": "conversions", "label": "Conversions"},
]
# P2-P6: the tel-021 flow count each column sums (Appendix B).
FLOW = {"calls": "calls", "connected": "connected_calls", "qualified": "qualified_leads", "appointments": "new_appointments", "conversions": "converted_leads"}
MAX_DAYS = 366
REFUSED = "Telecaller performance is for managers and administrators"


def scope(user: User, team: str | None) -> tuple[list, list[str]]:
    """PF1 / T24: the telecallers the caller may compare, and the teams they may filter by. `team` only narrows; a division admin naming
    another team is refused (403) by `admin_team_filter`."""
    if user.role == "telecaller_manager":
        return team_filter(user) + ([TelecallerProfile.team == team] if team else []), list(TEAMS)
    if user.role in ("super_admin", "it_admin", "overseas_admin"):
        return admin_team_filter(user, team), sorted(creatable_teams(user))
    raise HTTPException(403, REFUSED)


def date_range(date_from: date | None, date_to: date | None, today: date) -> tuple[date, date]:
    """PF4: default the 1st of the month → today; at most 366 days, never past today."""
    last = date_to or today
    first = date_from or last.replace(day=1)
    if first > last:
        raise HTTPException(422, "The start date must not be after the end date")
    if last > today:
        raise HTTPException(422, "The range can't end in the future")
    if (last - first).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"The range can't be longer than {MAX_DAYS} days")
    return first, last


async def _row(db: AsyncSession, person: User, team: str, start, end) -> dict:
    flow = await metrics.flow_counts(db, person.id, start, end)
    return {
        "user_id": person.id, "full_name": person.full_name, "team": TEAM_LABEL[team], "active": person.active,
        "status": "Active" if person.active else "Inactive", "leads": await metrics.leads_received(db, person.id, start, end),
        **{column: flow[count] for column, count in FLOW.items()},
    }


async def performance(db: AsyncSession, user: User, *, team: str | None, first: date, last: date, sort: str, direction: str) -> dict:
    filters, teams = scope(user, team)
    start, end = day_range(first)[0], day_range(last)[1]
    people = (await db.execute(
        select(User, TelecallerProfile.team).join(TelecallerProfile, TelecallerProfile.user_id == User.id).where(User.role == "telecaller", *filters)
    )).all()
    items = [await _row(db, person, person_team, start, end) for person, person_team in people]
    items.sort(key=lambda row: row["full_name"].casefold())  # ties stay in name order: both sorts are stable
    if sort != "name":
        items.sort(key=lambda row: row[sort], reverse=direction == "desc")
    elif direction == "desc":
        items.reverse()
    totals = {"full_name": "Total", "team": "", "status": "", **{key: sum(row[key] for row in items) for key in COUNTS}}
    return {"date_from": first, "date_to": last, "team": team, "sort": sort, "dir": direction, "teams": teams, "columns": COLUMNS,
            "items": items, "totals": totals}
