"""bdm-010 -- AC13 abuse cases (spec §12.3): IDOR, mass assignment, wrong roles, filter widening."""

import uuid

import pytest

from tests.bdm001_helpers import make_user
from tests.bdm010_helpers import APPROVALS, TEAM_TRIPS, TRIPS, act, bdm_pair, make_trip, sign_in, trip_body


@pytest.mark.asyncio
async def test_another_bdms_trip_is_404_on_every_owner_route(client, db_session):
    manager, owner = await bdm_pair(client, db_session)
    trip = await make_trip(client)
    await bdm_pair(client, db_session, manager=manager)  # a second BDM of the same manager
    base = f"{TRIPS}/{trip['id']}"
    calls = [client.get(base), client.patch(base, json={"remarks": "x"}),
             *(client.post(f"{base}/{a}") for a in ("submit", "withdraw", "start", "complete", "cancel")),
             client.post(f"{base}/expenses", json={"category": "food", "amount": "1", "expense_date": trip["travel_date"]}),
             client.patch(f"{base}/expenses/{uuid.uuid4()}", json={"amount": "1"}), client.delete(f"{base}/expenses/{uuid.uuid4()}")]
    for call in calls:
        response = await call
        assert (response.status_code, response.json()["detail"]) == (404, "Trip not found"), response.request.url


@pytest.mark.asyncio
async def test_expense_id_from_another_trip_is_404(client, db_session):
    manager, bdm = await bdm_pair(client, db_session)
    first, second = await make_trip(client), await make_trip(client)
    for trip in (first, second):
        await act(client, trip["id"], "submit")
    await sign_in(client, manager)
    for trip in (first, second):
        await client.post(f"{TEAM_TRIPS}/{trip['id']}/approve")
    await sign_in(client, bdm)
    line = (await client.post(f"{TRIPS}/{first['id']}/expenses",
                              json={"category": "food", "amount": "10", "expense_date": first["travel_date"]})).json()["expenses"][0]
    response = await client.delete(f"{TRIPS}/{second['id']}/expenses/{line['id']}")
    assert (response.status_code, response.json()["detail"]) == (404, "Expense not found")


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("code", "TRV-000001"), ("bdm_user_id", str(uuid.uuid4())), ("approval_status", "approved"),
                                         ("travel_status", "completed"), ("currency", "USD"), ("decided_by_user_id", str(uuid.uuid4()))])
async def test_server_owned_fields_are_refused(client, db_session, field, value):
    await bdm_pair(client, db_session)
    assert (await client.post(TRIPS, json=trip_body(**{field: value}))).status_code == 422
    trip = await make_trip(client)
    assert (await client.patch(f"{TRIPS}/{trip['id']}", json={field: value})).status_code == 422


@pytest.mark.asyncio
async def test_roles_are_kept_apart(client, db_session):
    manager, _ = await bdm_pair(client, db_session)
    for url in (TEAM_TRIPS, APPROVALS):
        assert (await client.get(url)).status_code == 403  # a bdm on manager routes
    await sign_in(client, manager)
    assert (await client.get(TRIPS)).status_code == 403  # a manager on BDM routes
    await sign_in(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(APPROVALS)).status_code == 403


@pytest.mark.asyncio
async def test_bdm_filter_cannot_widen_a_managers_scope(client, db_session):
    _, bdm = await bdm_pair(client, db_session)
    await make_trip(client)
    await sign_in(client, await make_user(db_session, "bdm_manager", "global"))
    page = (await client.get(TEAM_TRIPS, params={"bdm_user_id": str(bdm.id)})).json()
    assert page["total"] == 0 and page["items"] == []
