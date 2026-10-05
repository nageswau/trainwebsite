"""AGN-016 AC09 -- two completes of one task: the second waits for the row lock and is refused, never a double close. A SEPARATE
transaction holds the task row lock and closes it; the request is queued behind it, then the commit releases it: the interleaving is
forced, not left to timing (AGN-008's method)."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import AgentTask, AuditLog
from app.services import agent_tasks as service
from tests.agn001_helpers import client_for
from tests.agn008_helpers import agency_world
from tests.agn016_helpers import TASKS, mk_task


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["task"] = await mk_task(db_session, record=w["record"], author=w["master"])
    return w


@asynccontextmanager
async def _completing(task_id, user_id):
    session = SessionLocal()
    try:
        row = await session.scalar(select(AgentTask).where(AgentTask.id == task_id).with_for_update())
        row.status, row.closed_at, row.closed_by_user_id = "done", datetime.now(UTC), user_id
        await session.flush()
        yield
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_second_complete_waits_then_is_refused(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        async with _completing(world["task"].id, world["master"].id):
            request = asyncio.create_task(c.patch(f"{TASKS}/{world['task'].id}", json={"status": "cancelled"}))
            await asyncio.sleep(0.7)
            assert not request.done(), "the request did not wait for the task row lock"
        response = await request
    assert (response.status_code, response.json()["detail"]) == (409, service.CLOSED)
    row = await db_session.get(AgentTask, world["task"].id, populate_existing=True)
    assert (row.status, row.closed_by_user_id) == ("done", world["master"].id)
    closes = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(("agent_student.task_complete", "agent_student.task_cancel")), AuditLog.entity_id == str(world["record"].id))
    )
    assert closes == 0
