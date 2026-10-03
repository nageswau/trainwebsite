"""AGN-017 AC5 -- two reminder runs at once (two beat processes, a manual rerun) still create each reminder once: the partial unique
index on notifications.dedupe_key decides, not a read-then-write check."""

import asyncio
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Notification
from app.services import agent_notifications as notices_svc
from tests.agn008_helpers import agency_world, mk_application

D = date(2031, 4, 14)
MORNING = datetime(2031, 4, 14, 2, 30, tzinfo=UTC)


async def _one_run():
    async with SessionLocal() as db:
        return await notices_svc.send_daily_reminders(db, now=MORNING)


@pytest.mark.asyncio
async def test_two_concurrent_runs_create_each_reminder_once(db_session):
    world = await agency_world(db_session)
    app = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], application_deadline=D)
    await asyncio.gather(_one_run(), _one_run())
    keys = list(await db_session.scalars(select(Notification.dedupe_key).where(Notification.dedupe_key.like(f"agn017:deadline:{app.id}:%"))))
    assert len(keys) == 1
    staff_rows = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == world["staff"]["user"].id))
    assert staff_rows == 1
