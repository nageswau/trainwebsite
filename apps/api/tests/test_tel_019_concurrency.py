"""tel-019 -- races (plan Review Focus 1). Two real sessions through the app, the bdm-006 pattern: the request row lock decides."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmAppointment, BdmMeetingRequest
from tests.bdm001_helpers import login
from tests.bdm002_helpers import create_org
from tests.tel019_helpers import accept_body, accept_url, decline_url, file_request, make_bdm, make_manager, telecaller


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _final(db, request_id) -> BdmMeetingRequest:
    return await db.scalar(select(BdmMeetingRequest).where(BdmMeetingRequest.id == uuid.UUID(request_id)).execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_two_bdms_accepting_one_pool_request_make_exactly_one_appointment(client, db_session):
    req = await file_request(client, await telecaller(db_session), request_type="agent")
    manager = await make_manager(db_session)
    first, second = await make_bdm(db_session, manager, "agent"), await make_bdm(db_session, manager, "agent")
    async with _client() as one, _client() as two:
        await login(one, first)
        await login(two, second)
        org_one, org_two = await create_org(one), await create_org(two)
        results = await asyncio.gather(one.post(accept_url(req["id"]), json=accept_body(org_one, appointment_type="agent_meeting")),
                                       two.post(accept_url(req["id"]), json=accept_body(org_two, appointment_type="agent_meeting")))
    assert sorted(r.status_code for r in results) == [200, 404]  # the loser's scope no longer holds once the winner took it
    row = await _final(db_session, req["id"])
    assert row.status == "accepted" and row.bdm_user_id in (first.id, second.id)
    made = await db_session.scalar(select(func.count()).select_from(BdmAppointment).where(BdmAppointment.organization_id.in_(
        [uuid.UUID(org_one["id"]), uuid.UUID(org_two["id"])])))
    assert made == 1


@pytest.mark.asyncio
async def test_accept_and_decline_race_leaves_one_decision(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "college")
    req = await file_request(client, await telecaller(db_session), bdm_user_id=str(bdm.id))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one)
        results = await asyncio.gather(one.post(accept_url(req["id"]), json=accept_body(org)),
                                       two.post(decline_url(req["id"]), json={"reason": "Clash"}))
    assert sorted(r.status_code for r in results) == [200, 409]
    row = await _final(db_session, req["id"])
    assert row.status in ("accepted", "declined")
    made = await db_session.scalar(select(func.count()).select_from(BdmAppointment).where(BdmAppointment.organization_id == uuid.UUID(org["id"])))
    assert made == (1 if row.status == "accepted" else 0)
