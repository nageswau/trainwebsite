"""upc-022 (DEC-SCOPE-168, spec §3): the §22 partnership manager dashboard -- Appendix B D1-D14 and the §20 follow-up bands.

Read-only and computed live: the figures come from `services.partnership_metrics.dashboard_figures` over the caller's scope (DB1: manager =
primary/backup, head = team + unowned, super_admin = all) and the IST month of the database clock (DB3); D13 is upc-023's E1, from the same
rows `/partnership/expected` reads. Nothing is stored, logged or audited. A fixed number of statements."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.partnership_expected import READERS, expected_rows, window_figures
from app.core.database import get_db
from app.models import User
from app.schemas import PartnershipDashboard
from app.services import partnership_universities as universities
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.partnership import partnership_context
from app.services.partnership_metrics import dashboard_figures

router = APIRouter(prefix="/partnership", tags=["partnership-dashboard"])


@router.get("/dashboard", response_model=PartnershipDashboard)
async def dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DB15: partnership managers (with a profile), heads and super_admin; any other role is a 403."""
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)
    elif user.role not in READERS:
        raise HTTPException(403, "The partnership dashboard is for partnership managers and heads")
    today = india_date(await db_now(db))
    team = await universities.team_of(db, user)
    figures = await dashboard_figures(db, user, team, today)
    expected = next(w for w in window_figures(await expected_rows(db, user, team), today) if w["key"] == "this_month")
    return {
        "today": today, "month": {"first": expected["first"], "last": expected["last"]}, **figures,
        "this_month": figures["this_month"] | {"expected_count": expected["count"], "expected_weighted": expected["weighted"]},
    }  # fmt: skip
