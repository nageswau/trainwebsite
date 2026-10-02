"""AGN-008 final review -- an agent's withdraw that commits while a counselor/admin status write is in flight must not be
overwritten. A SEPARATE transaction holds the application row lock and sets `withdrawn`; the competing request is queued
behind it, then the lock is released by the commit: the interleaving is forced, not left to timing (ENH-011's method)."""

import asyncio
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import AgentCommission, OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import agency_world, mk_application

LEGACY = "/api/v1/workflows/overseas/applications"


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["counselor"] = await mk_user(db_session, role="counselor", full_name="Race Counselor")
    w["admin"] = await mk_user(db_session, role="overseas_admin", full_name="Race Admin")
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="status_tracking", counselor_id=w["counselor"].id)
    return w


@asynccontextmanager
async def _withdrawing(app_id):
    """Lock the row FOR UPDATE and set `withdrawn` in its own transaction; commit on exit (the agent's withdraw landing)."""
    session = SessionLocal()
    try:
        row = await session.scalar(select(OverseasApplication).where(OverseasApplication.id == app_id).with_for_update())
        row.status = "withdrawn"
        await session.flush()
        yield
        await session.commit()
    finally:
        await session.close()


async def _waiting(task) -> None:
    await asyncio.sleep(0.7)
    assert not task.done(), "the request did not wait for the application row lock"


async def _race(world, email, send):
    async with client_for(email) as c:
        async with _withdrawing(world["app"].id):
            task = asyncio.create_task(send(c))
            await _waiting(task)
        return await asyncio.wait_for(task, timeout=20)


async def _assert_still_withdrawn(db_session, world):
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == "withdrawn"
    assert await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id)) == 0


@pytest.mark.asyncio
async def test_counselor_advance_waits_for_a_withdraw_and_is_refused(db_session, world):
    r = await _race(world, world["counselor"].email, lambda c: c.post(f"{LEGACY}/{world['app'].id}/advance", json={"to_status": "enrolled"}))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "This application is withdrawn"
    await _assert_still_withdrawn(db_session, world)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["counselor", "admin"])
async def test_patch_status_waits_for_a_withdraw_and_is_refused(db_session, world, who):
    r = await _race(world, world[who].email, lambda c: c.patch(f"{LEGACY}/{world['app'].id}", json={"status": "enrolled"}))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "This application is withdrawn"
    await _assert_still_withdrawn(db_session, world)
