"""hrc-034 (DEC-SCOPE-415 I3/I4): write and expire `portal_events`. Ids only. The caller owns the transaction."""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import PortalEvent
from app.services.bdm_appointments import today_ist

logger = logging.getLogger("app.portal_events")

JOB_VIEW, APPLY_START, APPLY_SUBMIT = "job_view", "apply_start", "apply_submit"
RETENTION_DAYS = 400  # I4 (NEEDS_CONFIRMATION, Q-31): past the reports' 366-day limit


async def record(db: AsyncSession, user_id: UUID, kind: str, job_ids: Iterable[UUID]) -> None:
    """At most one row per person, job, kind and IST day; a repeat changes nothing."""
    day = today_ist(datetime.now(UTC))
    rows = [{"id": uuid4(), "kind": kind, "user_id": user_id, "job_id": job_id, "day": day} for job_id in job_ids]
    if rows:
        await db.execute(insert(PortalEvent).values(rows).on_conflict_do_nothing(constraint="uq_portal_events_once"))


async def run_retention() -> int:
    """Daily via beat. Returns the rows deleted."""
    cutoff = today_ist(datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)
    async with SessionLocal() as db:
        deleted = (await db.execute(delete(PortalEvent).where(PortalEvent.day < cutoff))).rowcount
        await db.commit()
    logger.info("portal_events_retention", extra={"extra_fields": {"deleted": deleted, "cutoff": cutoff.isoformat()}})
    return deleted
