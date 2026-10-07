"""bdm-024 (DEC-SCOPE-111, spec §4): management performance by BDM type for a period (the §5 table, Appendix B.6 P-01...P-08), its
drill-down (type -> BDMs -> one BDM's organizations and trips), and the master view (§6, V-A / V-S / V-C).

Scope is bdm-023's (`team_scope`): a manager's team, or for super_admin all teams or one manager's (P1). Read-only: no write, no audit,
no log line. Figures come from `services.bdm_performance`, summed level by level so the levels always agree (P8)."""

from collections import defaultdict
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm_manager_dashboard import team_scope
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmOrganization, BdmProfile, BdmTrip, User
from app.schemas import BdmHierarchyOut, BdmPerformanceBdmOut, BdmPerformanceOut
from app.services.bdm_appointments import db_now, today_ist
from app.services.bdm_performance import TYPES, figures, hierarchy, period, team_members, total, trip_filter

router = APIRouter(prefix="/bdm/manager", tags=["bdm-performance"])
BdmType = Literal["agent", "school", "college"]
NOT_FOUND = "BDM not found"
NOT_TRACKED = "Not tracked: no revenue is recorded for this BDM type (deposits and commissions are not BDM revenue)."

# (key, label, figure, definition; a dict = one definition per type). The definition goes out with every cell, so the page shows the
# same words (Appendix B.6).
ROWS: tuple[tuple[str, str, str | None, str | dict[str, str]], ...] = (
    ("P-01", "BDMs", None, "Active BDMs of this type in the team (today)."),
    ("P-02", "Meetings", "meetings", "Appointments completed in the period by these BDMs."),
    ("P-03", "Travel Trips", "trips", "Trips travelling in the period, except cancelled or rejected ones."),
    ("P-04", "New Organizations", "new_organizations", "Organizations these BDMs created in the period."),
    ("P-05", "MoUs", "mous", "MoUs these BDMs moved to Signed in the period."),
    ("P-06", "Leads", "leads", "Student leads these BDMs entered in the period."),
    ("P-07", "Students", "students", {
        "agent": "Active students added in the period in the agencies linked to these BDMs' organizations.",
        "school": "Students added in the period in the schools linked to these BDMs' organizations.",
        "college": "Students whose lead from these BDMs' organizations was converted in the period.",
    }),
    ("P-08", "Revenue", "revenue", {
        "agent": NOT_TRACKED,
        "school": NOT_TRACKED,
        "college": "Paid INR fees recorded in the period for the students of these BDMs' organizations (agent deposits excluded).",
    }),
)


def _definition(definition: str | dict[str, str], bdm_type: str) -> str:
    return definition if isinstance(definition, str) else definition[bdm_type]


async def _period(db: AsyncSession, from_: date | None, to: date | None) -> tuple[date, date]:
    return period(from_, to, today_ist(await db_now(db)))


@router.get("/performance", response_model=BdmPerformanceOut)
async def performance(
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    type: BdmType | None = None,  # noqa: A002 -- the backlog's query parameter name
    manager_user_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team, manager = await team_scope(db, user, manager_user_id)
    start, end = await _period(db, from_, to)
    members = await team_members(db, team)
    by_bdm = defaultdict(list)
    for (bdm_id, _org_id), row in (await figures(db, team, start, end)).items():
        by_bdm[bdm_id].append(row)
    per_bdm = {m.id: total(by_bdm[m.id], m.bdm_type) for m in members}
    per_type = {t: total([per_bdm[m.id] for m in members if m.bdm_type == t], t) for t in TYPES}
    active = {t: sum(1 for m in members if m.bdm_type == t and m.active) for t in TYPES}

    rows = []
    for key, label, figure, definition in ROWS:
        cells = []
        for t in TYPES:
            value = active[t] if figure is None else per_type[t][figure]
            cells.append({"type": t, "tracked": value is not None, "value": value, "definition": _definition(definition, t)})
        rows.append({"key": key, "label": label, "cells": cells})
    return {
        "from_": start, "to": end, "type": type, "rows": rows,
        "manager": {"id": manager.id, "full_name": manager.full_name} if manager else None,
        "bdms": [{"id": m.id, "full_name": m.full_name, "active": m.active, "figures": per_bdm[m.id]} for m in members if m.bdm_type == type],
    }


@router.get("/performance/bdms/{bdm_user_id}", response_model=BdmPerformanceBdmOut)
async def bdm_performance(
    bdm_user_id: UUID,
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One BDM's organizations (the ones with a figure in the period) and trips; out of the caller's team = 404 (no IDOR)."""
    team, _ = await team_scope(db, user, None)
    one = select(BdmProfile.user_id).where(BdmProfile.user_id == bdm_user_id, BdmProfile.user_id.in_(team))
    found = await team_members(db, one)
    if not found:
        raise HTTPException(404, NOT_FOUND)
    bdm = found[0]
    start, end = await _period(db, from_, to)
    rows = await figures(db, one, start, end)
    by_org = {org_id: row for (_bdm, org_id), row in rows.items() if org_id is not None}
    orgs = (await db.execute(select(BdmOrganization.id, BdmOrganization.code, BdmOrganization.name)
                             .where(BdmOrganization.id.in_(list(by_org))).order_by(BdmOrganization.name, BdmOrganization.id))).all()
    trips = (await db.execute(select(BdmTrip).where(*trip_filter(one, start, end)).order_by(BdmTrip.travel_date, BdmTrip.code))).scalars().all()
    return {
        "from_": start, "to": end,
        "bdm": {"id": bdm.id, "full_name": bdm.full_name, "active": bdm.active, "bdm_type": bdm.bdm_type},
        "totals": total(rows.values(), bdm.bdm_type),
        "organizations": [{"id": o.id, "code": o.code, "name": o.name, "figures": {**total([by_org[o.id]], bdm.bdm_type), "trips": None}}
                          for o in orgs],
        "trips": trips,
    }


@router.get("/hierarchy", response_model=BdmHierarchyOut)
async def master_view(manager_user_id: UUID | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§6 master view (P10): live, all time -- the organization panels' own figures, summed per BDM and per type."""
    team, manager = await team_scope(db, user, manager_user_id)
    return {
        "manager": {"id": manager.id, "full_name": manager.full_name} if manager else None,
        "as_of": await db_now(db),
        "types": await hierarchy(db, team),
    }
