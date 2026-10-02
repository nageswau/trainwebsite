"""AGN-012 AC9 -- agency visa writes are serialised on the application row: a start or an advance that arrives while another writer
holds the row waits for it, then sees its result (one case; a stale stage is 409). The interleaving is forced with a separate
transaction holding the row lock (AGN-008/013's method), not left to timing; the gather tests add the plain two-callers case."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import OverseasApplication, VisaCase
from tests.agn001_helpers import client_for
from tests.agn012_helpers import VISA, case_of, count_cases, mk_case, visa_audits, visa_world


@asynccontextmanager
async def _holding_the_application(app_id, write):
    """Lock the application row FOR UPDATE in its own transaction, run `write(session)` and commit on exit (another writer landing)."""
    session = SessionLocal()
    try:
        await session.scalar(select(OverseasApplication).where(OverseasApplication.id == app_id).with_for_update())
        await write(session)
        await session.flush()
        yield
        await session.commit()
    finally:
        await session.close()


async def _waits_then(c, method, url, body, holder):
    async with holder:
        task = asyncio.create_task(getattr(c, method)(url, json=body))
        await asyncio.sleep(0.7)
        assert not task.done(), "the request did not wait for the application row lock"
    return await asyncio.wait_for(task, timeout=20)


@pytest.mark.asyncio
async def test_a_start_queued_behind_another_start_sees_the_case(db_session):
    w = await visa_world(db_session)

    async def other_start(session):
        session.add(VisaCase(application_id=w["app"].id, status="checklist", checklist=[]))

    async with client_for(w["master"].email) as c:
        r = await _waits_then(c, "post", VISA.format(w["app"].id), {"expected_status": "offer"}, _holding_the_application(w["app"].id, other_start))
    assert (r.status_code, r.json()["detail"]) == (409, "A visa case already exists for this application")
    assert await count_cases(db_session, w["app"]) == 1


@pytest.mark.asyncio
async def test_an_advance_queued_behind_another_advance_is_stale(db_session):
    w = await visa_world(db_session)
    case = await mk_case(db_session, w["app"], status="documentation")

    async def other_advance(session):
        row = await session.get(VisaCase, case.id)
        row.status = "tracking"

    async with client_for(w["staff"]["user"].email) as c:
        body = {"expected_stage": "documentation", "to_stage": "interview_prep"}
        r = await _waits_then(c, "patch", VISA.format(w["app"].id), body, _holding_the_application(w["app"].id, other_advance))
    assert r.status_code == 409
    assert (await case_of(db_session, w["app"])).status == "tracking" and await visa_audits(db_session, w["app"]) == []


@pytest.mark.asyncio
async def test_two_simultaneous_starts_create_one_case(db_session):
    w = await visa_world(db_session)
    url, body = VISA.format(w["app"].id), {"expected_status": "offer"}
    async with client_for(w["master"].email) as a, client_for(w["staff"]["user"].email) as b:
        first, second = await asyncio.gather(a.post(url, json=body), b.post(url, json=body))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert await count_cases(db_session, w["app"]) == 1


@pytest.mark.asyncio
async def test_two_simultaneous_advances_one_wins(db_session):
    w = await visa_world(db_session)
    await mk_case(db_session, w["app"], status="documentation")
    url = VISA.format(w["app"].id)
    async with client_for(w["master"].email) as a, client_for(w["staff"]["user"].email) as b:
        first, second = await asyncio.gather(
            a.patch(url, json={"expected_stage": "documentation", "to_stage": "interview_prep"}),
            b.patch(url, json={"expected_stage": "documentation", "to_stage": "tracking"}),
        )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert (await case_of(db_session, w["app"])).status in {"interview_prep", "tracking"}
    assert len(await visa_audits(db_session, w["app"])) == 1
