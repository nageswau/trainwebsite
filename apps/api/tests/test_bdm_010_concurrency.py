"""bdm-010 -- AC9: approve and withdraw race on one trip; the row lock lets exactly one win."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm010_helpers import TEAM_TRIPS, TRIPS, act, bdm_pair, make_trip


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_approve_and_withdraw_race_one_wins(client, db_session):
    manager, bdm = await bdm_pair(client, db_session)
    trip = await make_trip(client)
    await act(client, trip["id"], "submit")
    async with _client() as as_manager, _client() as as_bdm:
        await login(as_manager, manager)
        await login(as_bdm, bdm)
        results = await asyncio.gather(
            as_manager.post(f"{TEAM_TRIPS}/{trip['id']}/approve"), as_bdm.post(f"{TRIPS}/{trip['id']}/withdraw"))
    assert sorted(r.status_code for r in results) == [200, 409]
    final = (await client.get(f"{TRIPS}/{trip['id']}")).json()["approval_status"]
    assert final == ("approved" if results[0].status_code == 200 else "draft")
