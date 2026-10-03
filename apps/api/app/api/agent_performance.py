"""AGN-019 -- staff performance and the student funnel: one read-only Master-only aggregate (DEC-SCOPE-066; spec §5.1).

Guards first, then the dates (AGN-014's order), so a refused caller never sees a 422. No write, no audit row (reads are not audited,
DEC-SCOPE-051 R7). The body is per-agency, so it is never cached. The log line carries ids, a flag and timing only."""

import logging
import time

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate, _require_master_action
from app.api.deps import get_current_user
from app.api.workflows import report_range
from app.core.database import get_db
from app.models import User
from app.schemas import AgentPerformanceOut
from app.services.agent_performance import performance

logger = logging.getLogger("app.agent_performance")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-performance"])

MASTER_ONLY = "Only an agency Master can view staff performance"
DATE_FROM = Query(None, description="Optional. YYYY-MM-DD: the first UTC day (inclusive) on which the students' agency records were created.")
DATE_TO = Query(None, description="Optional. YYYY-MM-DD: the last UTC day (inclusive) of that range; before 9999-12-31.")


@router.get("/performance", response_model=AgentPerformanceOut)
async def get_performance(
    response: Response,
    date_from: str | None = DATE_FROM,
    date_to: str | None = DATE_TO,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    _require_master_action(user, MASTER_ONLY)
    start, end = report_range(date_from, date_to)
    started = time.perf_counter()
    payload = await performance(db, user, start, end)
    response.headers["Cache-Control"] = "private, no-store"
    logger.info(
        "agent_performance.read",
        extra={
            "extra_fields": {
                "org_id": str(membership.org_id),
                "actor_id": str(user.id),
                "filtered": bool(start or end),
                "rows": len(payload["rows"]),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        },
    )
    return payload
