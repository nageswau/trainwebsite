"""bdm-002 -- every route x nine actors (AC3, §12.3 IDOR / role escalation; Review Focus 2)."""

import uuid

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm


async def _world(client, db):
    manager = await make_manager(db)
    owner, peer = await make_bdm(db, manager), await make_bdm(db, manager)
    world = {
        "owner": owner,
        "peer": peer,
        "other_type": await make_bdm(db, manager, "school"),
        "manager": manager,
        "other_manager": await make_manager(db),
        "super_admin": await make_user(db, "super_admin", "global"),
        "it_admin": await make_user(db, "it_admin", "it"),
        "student": await make_user(db, "student", "it"),
        "no_profile": await make_user(db, "bdm", "it"),
    }
    await login(client, owner)
    world["org"] = await create_org(client, contacts=[{"name": "A"}, {"name": "B"}])
    return world


# actor -> (read, listed, edit, contact add, assign to peer, archive, contact edit); `None` archive = not exercised (keeps it active);
# `None` listed = the list itself is 403.
EXPECTED = {
    "owner": (200, True, 200, 201, 403, None, 200),
    "peer": (200, True, 403, 403, 403, 403, 403),
    "other_type": (404, False, 404, 404, 404, 404, 404),
    "manager": (200, True, 403, 403, 200, 403, 403),
    "other_manager": (404, False, 404, 404, 404, 404, 404),
    "super_admin": (200, True, 200, 201, 200, None, 200),
    "it_admin": (403, None, 403, 403, 403, 403, 403),
    "student": (403, None, 403, 403, 403, 403, 403),
    "no_profile": (403, None, 403, 403, 403, 403, 403),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", list(EXPECTED))
async def test_scope_matrix(client, db_session, actor):
    w = await _world(client, db_session)
    read, listed, edit, contact_add, assign, archive, contact_edit = EXPECTED[actor]
    url = f"{ORGS}/{w['org']['id']}"
    cid = w["org"]["contacts"][0]["id"]
    await login(client, w[actor])
    assert (await client.get(url)).status_code == read
    page = await client.get(ORGS, params={"q": w["org"]["code"]})
    if listed is None:
        assert page.status_code == 403
    else:
        assert (w["org"]["id"] in {r["id"] for r in page.json()["items"]}) is listed
    assert (await client.patch(url, json={"state": "Goa"})).status_code == edit
    assert (await client.post(f"{url}/contacts", json={"name": "C"})).status_code == contact_add
    assert (await client.post(f"{url}/assign", json={"bdm_user_id": str(w["peer"].id)})).status_code == assign
    if archive is not None:
        assert (await client.post(f"{url}/archive")).status_code == archive
    assert (await client.patch(f"{url}/contacts/{cid}", json={"designation": "X"})).status_code == contact_edit


@pytest.mark.asyncio
async def test_unknown_ids_look_like_out_of_scope(client, db_session):
    w = await _world(client, db_session)
    await login(client, w["other_type"])
    out_of_scope = await client.get(f"{ORGS}/{w['org']['id']}")
    missing = await client.get(f"{ORGS}/{uuid.uuid4()}")
    assert out_of_scope.json() == missing.json() == {"detail": "Organization not found"}


@pytest.mark.asyncio
async def test_organizations_follow_the_bdm_to_a_new_manager(client, db_session):
    """Review Focus 2: bdm-001's PATCH moves the BDM; their organizations move with them (scope is computed, nothing migrates)."""
    w = await _world(client, db_session)
    new_manager = await make_manager(db_session)
    await login(client, w["super_admin"])
    moved = await client.patch(f"/api/v1/admin/users/{w['owner'].id}", json={"bdm_profile": {"reporting_manager_user_id": str(new_manager.id)}})
    assert moved.status_code == 200, moved.text
    await login(client, w["manager"])
    assert (await client.get(f"{ORGS}/{w['org']['id']}")).status_code == 404
    await login(client, new_manager)
    assert (await client.get(f"{ORGS}/{w['org']['id']}")).status_code == 200
