"""AGN-018 -- the agency dashboard: one read-only aggregate (DEC-SCOPE-062; spec §5).

AGN-004's gate (agency members of an active agency; super admin refused), no input, no write, no audit row (reads are not audited,
DEC-SCOPE-051 R7). The body is per-user, so it is never cached. The log line carries ids and timing only."""

import logging
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import AgentDashboardOut
from app.services.agent_dashboard import dashboard

logger = logging.getLogger("app.agent_dashboard")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-dashboard"])


@router.get("/dashboard", response_model=AgentDashboardOut)
async def get_dashboard(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    started = time.perf_counter()
    payload = await dashboard(db, user)
    response.headers["Cache-Control"] = "private, no-store"
    logger.info(
        "agent_dashboard.read",
        extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "scope": payload["scope"], "duration_ms": round((time.perf_counter() - started) * 1000)}},
    )
    return payload
