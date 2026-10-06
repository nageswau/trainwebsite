"""bdm-011 -- the travel report (AC3): the trip summary, for the BDM and their manager, once the trip is completed."""

from datetime import timedelta

import pytest

from app.services.bdm_travel import india_today
from tests.bdm001_helpers import make_manager
from tests.bdm010_helpers import TEAM_TRIPS, TRIPS, act, sign_in
from tests.bdm011_helpers import bdm_trip

NOT_YET = "The travel report is available once the trip is completed"


async def _completed_trip(client, db):
    """A trip that ran yesterday: submitted, approved by the manager, completed by the BDM (who stays signed in)."""
    today = india_today()
    manager, bdm, org, trip = await bdm_trip(client, db, travel_date=str(today - timedelta(days=2)), return_date=str(today - timedelta(days=1)),
                                             remarks="Two colleges keen; follow up in a week")
    await act(client, trip["id"], "submit")
    await sign_in(client, manager)
    assert (await client.post(f"{TEAM_TRIPS}/{trip['id']}/approve")).status_code == 200
    await sign_in(client, bdm)
    assert (await act(client, trip["id"], "complete")).status_code == 200
    return manager, bdm, trip


@pytest.mark.asyncio
async def test_the_report_waits_for_completion(client, db_session):
    manager, _, _, trip = await bdm_trip(client, db_session)
    response = await client.get(f"{TRIPS}/{trip['id']}/report")
    assert (response.status_code, response.json()["detail"]) == (409, NOT_YET)
    await sign_in(client, manager)
    assert (await client.get(f"{TEAM_TRIPS}/{trip['id']}/report")).status_code == 409


@pytest.mark.asyncio
async def test_a_completed_trip_has_a_report_for_the_bdm_and_the_manager(client, db_session):
    manager, _, trip = await _completed_trip(client, db_session)
    mine = await client.get(f"{TRIPS}/{trip['id']}/report")
    assert mine.status_code == 200
    body = mine.json()
    assert (body["travel_status"], body["remarks"], body["itinerary"]) == ("completed", "Two colleges keen; follow up in a week", [])
    assert body["metrics"]["meetings_planned"] == 0
    await sign_in(client, manager)
    theirs = await client.get(f"{TEAM_TRIPS}/{trip['id']}/report")
    assert theirs.status_code == 200 and theirs.json()["code"] == trip["code"]


@pytest.mark.asyncio
async def test_the_report_is_scoped_like_the_trip(client, db_session):
    _, _, trip = await _completed_trip(client, db_session)
    await bdm_trip(client, db_session)  # another BDM
    assert (await client.get(f"{TRIPS}/{trip['id']}/report")).status_code == 404
    await sign_in(client, await make_manager(db_session))  # a manager of another team
    assert (await client.get(f"{TEAM_TRIPS}/{trip['id']}/report")).status_code == 404
