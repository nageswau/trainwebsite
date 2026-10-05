"""bdm-004 -- every pipeline route x the bdm-002 actors (AC6; spec §6.4, §7 IDOR / elevation)."""

import uuid

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm004_helpers import move, url


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
    world["org"] = await create_org(client)
    return world


# actor -> (move, history read)
EXPECTED = {
    "owner": (200, 200),
    "peer": (403, 200),
    "other_type": (404, 404),
    "manager": (403, 200),
    "other_manager": (404, 404),
    "super_admin": (200, 200),
    "it_admin": (403, 403),
    "student": (403, 403),
    "no_profile": (403, 403),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", list(EXPECTED))
async def test_scope_matrix(client, db_session, actor):
    w = await _world(client, db_session)
    moved, history = EXPECTED[actor]
    await login(client, w[actor])
    assert (await move(client, w["org"], "contacted")).status_code == moved
    assert (await client.get(url(w["org"]["id"], "stage-history"))).status_code == history


@pytest.mark.asyncio
async def test_refusals_are_explained_and_unknown_ids_look_out_of_scope(client, db_session):
    w = await _world(client, db_session)
    await login(client, w["peer"])
    assert (await move(client, w["org"], "contacted")).json()["detail"] == "Only the assigned BDM can edit this organization"
    await login(client, w["other_type"])
    out_of_scope = await move(client, w["org"], "contacted")
    missing = await move(client, {**w["org"], "id": str(uuid.uuid4())}, "contacted")
    assert out_of_scope.json() == missing.json() == {"detail": "Organization not found"}


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    w = await _world(client, db_session)
    await client.post("/api/v1/auth/logout")
    assert (await move(client, w["org"], "contacted")).status_code == 401
    assert (await client.get(f"{ORGS}/{w['org']['id']}/stage-history")).status_code == 401
