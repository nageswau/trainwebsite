"""AGN-018 -- the agency dashboard: one read-only aggregate (DEC-SCOPE-062; spec §5).

AGN-004's gate (agency members of an active agency; super admin refused), no input, no write, no audit row (reads are not audited,
DEC-SCOPE-051 R7). The body is per-user, so it is never cached. The log line carries ids and timing only."""

import logging
import time

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.api.workflows import report_range
from app.core.database import get_db
from app.models import User
from app.schemas import AgentDashboardOut
from app.services.agent_dashboard import dashboard

logger = logging.getLogger("app.agent_dashboard")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-dashboard"])


DATE_FROM = Query(None, description="Optional (nehn-038). YYYY-MM-DD: the first UTC day (inclusive) on which the students' agency records were created.")
DATE_TO = Query(None, description="Optional (nehn-038). YYYY-MM-DD: the last UTC day (inclusive) of that range; before 9999-12-31.")


@router.get("/dashboard", response_model=AgentDashboardOut)
async def get_dashboard(
    response: Response,
    date_from: str | None = DATE_FROM,
    date_to: str | None = DATE_TO,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    start, end = report_range(date_from, date_to)  # after the gate, so a refused caller never sees a 422 (AGN-019's order)
    started = time.perf_counter()
    payload = await dashboard(db, user, start, end)
    response.headers["Cache-Control"] = "private, no-store"
    logger.info(
        "agent_dashboard.read",
        extra={
            "extra_fields": {
                "org_id": str(membership.org_id),
                "actor_id": str(user.id),
                "scope": payload["scope"],
                "filtered": bool(start or end),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        },
    )
    return payload
