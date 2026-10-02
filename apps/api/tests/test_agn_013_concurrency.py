"""AGN-013 AC07 -- two confirmations at once, and a counselor's enrolment landing first: exactly one commission either way. The
second interleaving is forced with a separate transaction holding the row lock (AGN-008's method), not left to timing."""

import asyncio
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AgentCommission, ApplicationStatusHistory, OverseasApplication
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, agency_world, count_rows, mk_application

BODY = {"enrollment_date": "2027-09-20", "expected_status": "status_tracking"}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="status_tracking")
    return w


@pytest.mark.asyncio
async def test_two_simultaneous_confirmations_create_one_commission(db_session, world):
    url = f"{APPS}/{world['app'].id}/enrollment"
    async with client_for(world["master"].email) as a, client_for(world["master"].email) as b:
        first, second = await asyncio.gather(a.put(url, json=BODY), b.put(url, json=BODY))
    assert sorted([first.status_code, second.status_code]) == [200, 409]  # the loser saw `enrolled`, not the status_tracking it expected
    assert await count_rows(db_session, AgentCommission, world["app"].id) == 1
    assert await count_rows(db_session, ApplicationStatusHistory, world["app"].id) == 1


@asynccontextmanager
async def _counselor_enrolling(app_id):
    """Lock the row FOR UPDATE and set `enrolled` in its own transaction; commit on exit (a counselor's enrolment landing)."""
    session = SessionLocal()
    try:
        row = await session.scalar(select(OverseasApplication).where(OverseasApplication.id == app_id).with_for_update())
        row.status = "enrolled"
        await session.flush()
        yield
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_counselor_enrolment_landing_first_turns_the_agency_call_into_a_stale_refusal(db_session, world):
    async with client_for(world["master"].email) as c:
        async with _counselor_enrolling(world["app"].id):
            task = asyncio.create_task(c.put(f"{APPS}/{world['app'].id}/enrollment", json=BODY))
            await asyncio.sleep(0.7)
            assert not task.done(), "the request did not wait for the application row lock"
        r = await asyncio.wait_for(task, timeout=20)
    assert r.status_code == 409, r.text  # the screen showed status_tracking: reload, then a re-save is a correction
    assert await count_rows(db_session, AgentCommission, world["app"].id) == 0  # the agency call created none
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    assert (row.status, row.enrollment_date) == ("enrolled", None)
