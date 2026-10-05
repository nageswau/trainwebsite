"""bdm-004 -- the pipeline view (S7; AC5): per-stage counts in scope, Lost apart, archived excluded, list per stage.

The shared database is never truncated: exact counts use a fresh BDM (`assigned=me`) or a fresh manager's team; whole-module counts
are compared as before / after deltas."""

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm004_helpers import PIPELINE, move, url


def _counts(view) -> dict:
    return {s["key"]: s["count"] for s in view["stages"]}


async def _seed(client, bdm):
    """Prospect x1, Contacted x2 (one of them lost), Proposal x1 archived."""
    await login(client, bdm)
    a = await create_org(client)
    b = (await move(client, await create_org(client), "contacted")).json()["organization"]
    c = (await move(client, await create_org(client), "contacted")).json()["organization"]
    await client.post(url(c["id"], "lost"), json={"reason": "No budget"})
    d = (await move(client, await create_org(client), "proposal")).json()["organization"]
    await client.post(f"{ORGS}/{d['id']}/archive")
    return a, b, c, d


@pytest.mark.asyncio
async def test_my_pipeline_counts_and_lists(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "college")
    a, b, c, _ = await _seed(client, bdm)
    view = (await client.get(PIPELINE, params={"assigned": "me"})).json()
    assert view["bdm_type"] == "college"
    counts = _counts(view)
    assert (counts["prospect"], counts["contacted"], counts["proposal"]) == (1, 1, 0)
    assert counts["placement"] is None and counts["course_promotion"] is None  # volumes: not tracked
    assert view["lost_count"] == 1
    assert {i["id"] for i in view["items"]} == {a["id"], b["id"]} and view["total"] == 2  # all open, archived and lost excluded
    contacted = (await client.get(PIPELINE, params={"assigned": "me", "stage": "contacted"})).json()
    assert [(i["id"], i["stage_label"], i["lost"]) for i in contacted["items"]] == [(b["id"], "Contacted", False)]
    lost = (await client.get(PIPELINE, params={"assigned": "me", "stage": "lost"})).json()
    assert [(i["id"], i["lost"]) for i in lost["items"]] == [(c["id"], True)]
    assert (await client.get(PIPELINE, params={"assigned": "me", "stage": "placement"})).json()["items"] == []
    paged = (await client.get(PIPELINE, params={"assigned": "me", "limit": 1, "offset": 1})).json()
    assert paged["total"] == 2 and len(paged["items"]) == 1


@pytest.mark.asyncio
async def test_whole_module_toggle_counts_peers(client, db_session):
    manager = await make_manager(db_session)
    me, peer = await make_bdm(db_session, manager, "agent"), await make_bdm(db_session, manager, "agent")
    await login(client, me)
    before = _counts((await client.get(PIPELINE)).json())
    await login(client, peer)
    await create_org(client)
    await login(client, me)
    after = _counts((await client.get(PIPELINE)).json())
    assert after["prospect"] - before["prospect"] >= 1
    assert _counts((await client.get(PIPELINE, params={"assigned": "me"})).json())["prospect"] == 0


@pytest.mark.asyncio
async def test_type_rules(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "school")
    await login(client, bdm)
    assert (await client.get(PIPELINE, params={"bdm_type": "school"})).status_code == 200
    other = await client.get(PIPELINE, params={"bdm_type": "college"})
    assert other.status_code == 422 and other.json()["detail"] == "You can only view your own module's pipeline"
    assert (await client.get(PIPELINE, params={"stage": "college_activated"})).status_code == 422  # another type's key
    assert (await client.get(PIPELINE, params={"stage": "<script>"})).status_code == 422
    await login(client, manager)
    missing = await client.get(PIPELINE)
    assert missing.status_code == 422 and missing.json()["detail"] == "Choose a BDM type"
    assert (await client.get(PIPELINE, params={"bdm_type": "school", "assigned": "me"})).status_code == 422  # `me` is BDM-only


@pytest.mark.asyncio
async def test_manager_sees_their_team_and_one_bdm(client, db_session):
    manager = await make_manager(db_session)
    first, second = await make_bdm(db_session, manager, "college"), await make_bdm(db_session, manager, "college")
    await _seed(client, first)
    await login(client, second)
    await create_org(client)
    outsider = await make_bdm(db_session, await make_manager(db_session), "college")
    await login(client, outsider)
    await create_org(client)
    await login(client, manager)
    team = (await client.get(PIPELINE, params={"bdm_type": "college"})).json()
    assert (_counts(team)["prospect"], _counts(team)["contacted"], team["lost_count"]) == (2, 1, 1)
    one = (await client.get(PIPELINE, params={"bdm_type": "college", "assigned": str(second.id)})).json()
    assert (_counts(one)["prospect"], one["total"]) == (1, 1)
    assert (await client.get(PIPELINE, params={"bdm_type": "college", "assigned": str(outsider.id)})).json()["total"] == 0


@pytest.mark.asyncio
async def test_super_admin_sees_every_bdm_and_other_roles_are_refused(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "school")
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    before = _counts((await client.get(PIPELINE, params={"bdm_type": "school"})).json())["prospect"]
    await login(client, bdm)
    await create_org(client)
    await login(client, admin)
    assert _counts((await client.get(PIPELINE, params={"bdm_type": "school"})).json())["prospect"] - before >= 1
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(PIPELINE, params={"bdm_type": "school"})).status_code == 403
