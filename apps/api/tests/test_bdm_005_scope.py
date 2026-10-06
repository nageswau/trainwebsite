"""bdm-005 -- every organization MoU route x the bdm-002 actors (AC8; spec §6.4, §7 IDOR / elevation; M3)."""

import uuid

import pytest

from tests.bdm001_helpers import login
from tests.bdm005_helpers import change, mou_url, start, world

# actor -> (read, create, change)
EXPECTED = {
    "owner": (200, 201, 200),
    "peer": (200, 403, 403),
    "other_type": (404, 404, 404),
    "manager": (200, 403, 403),
    "other_manager": (404, 404, 404),
    "super_admin": (200, 201, 200),
    "it_admin": (403, 403, 403),
    "student": (403, 403, 403),
    "no_profile": (403, 403, 403),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", list(EXPECTED))
async def test_scope_matrix(client, db_session, actor):
    w = await world(client, db_session)
    read, created, changed = EXPECTED[actor]
    await login(client, w[actor])
    assert (await client.get(mou_url(w["org"]["id"]))).status_code == read
    assert (await start(client, w["org"])).status_code == created
    if created != 201:  # give the change something to act on
        await login(client, w["owner"])
        await start(client, w["org"])
        await login(client, w[actor])
    assert (await change(client, w["org"], notes="x")).status_code == changed


@pytest.mark.asyncio
async def test_read_only_callers_see_no_write_permissions(client, db_session):
    w = await world(client, db_session)
    await start(client, w["org"])
    for actor in ("peer", "manager"):
        await login(client, w[actor])
        body = (await client.get(mou_url(w["org"]["id"]))).json()
        assert body["can_start"] is False
        assert body["current"]["permissions"] == {"can_edit": False, "can_upload": False, "can_renew": False}


@pytest.mark.asyncio
async def test_refusals_are_explained_and_unknown_ids_look_out_of_scope(client, db_session):
    w = await world(client, db_session)
    await login(client, w["peer"])
    assert (await start(client, w["org"])).json()["detail"] == "Only the assigned BDM can edit this organization"
    await login(client, w["other_type"])
    out_of_scope = await client.get(mou_url(w["org"]["id"]))
    missing = await client.get(mou_url(str(uuid.uuid4())))
    assert out_of_scope.json() == missing.json() == {"detail": "Organization not found"}


@pytest.mark.asyncio
async def test_server_owned_fields_cannot_be_sent(client, db_session):
    w = await world(client, db_session)
    response = await start(client, w["org"], created_by_user_id=str(w["peer"].id), is_current=False)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    w = await world(client, db_session)
    await client.post("/api/v1/auth/logout")
    assert (await client.get(mou_url(w["org"]["id"]))).status_code == 401
    assert (await start(client, w["org"])).status_code == 401
