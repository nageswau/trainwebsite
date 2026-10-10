"""upc-029 (spec §3, GD1-GD17): the §31 complete global partnership dashboard, for management.

Read-only and computed live over the caller's scope (GD2: head = team + unowned, super_admin = all): the three columns and the Management
§19 pipeline from `services.partnership_metrics.global_figures` (they add up to upc-022's D1-D4), and the funnel and commission totals from
upc-018's `ranking` for the period (they equal `/partnership/performance`'s). Nothing is stored, logged or audited. A fixed number of
statements."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.partnership_performance import FROM, STEPS_OUT, TO, commission_totals, ranking, request_period, step_counts
from app.core.database import get_db
from app.models import User
from app.schemas import GlobalPartnershipDashboard
from app.services import partnership_universities as universities
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.partnership_metrics import global_figures

router = APIRouter(prefix="/partnership", tags=["partnership-global-dashboard"])
READERS = frozenset({"partnership_head", "super_admin"})  # GD1: management; a manager's figures are upc-022's dashboard


@router.get("/global-dashboard", response_model=GlobalPartnershipDashboard, response_model_exclude_unset=True)
async def global_dashboard(first: str | None = FROM, last: str | None = TO, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The columns and pipeline are now; the funnel and commission cover the period (default this IST month to date)."""
    if user.role not in READERS:
        raise HTTPException(403, "The global partnership dashboard is for partnership heads and super admins")
    first_day, last_day = await request_period(db, first, last)
    team = await universities.team_of(db, user)
    today = india_date(await db_now(db))
    figures = await global_figures(db, user, team, today)
    _, totals, money = await ranking(db, user, team, first_day, last_day)
    out = {"today": today, "from": first_day, "to": last_day, **figures, "funnel": {"steps": STEPS_OUT, "totals": step_counts(totals)}}
    if money is not None:  # U2
        out["commission"] = commission_totals(money)
    return out
