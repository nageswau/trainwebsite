"""bdm-009 -- authorization (spec §5.4; AC5, AC6)."""

import logging

import pytest

from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm009_helpers import ACTIVITIES, TEAM_ACTIVITIES, activity_body, bdm_with_org, org_activities


async def as_user(client, user) -> None:
    client.cookies.clear()
    await login(client, user)


@pytest.mark.asyncio
async def test_out_of_type_org_is_404_and_unassigned_same_type_is_403(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session, "college")
    await as_user(client, await make_bdm(db_session, manager, "school"))
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 404
    await as_user(client, await make_bdm(db_session, manager, "college"))
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (403, "Only the organization's assigned BDM can log activity")


@pytest.mark.asyncio
async def test_archived_org_refuses_a_new_log_but_today_entries_stay_editable(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    assert (await client.post(f"/api/v1/bdm/organizations/{org['id']}/archive")).status_code == 200
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (422, "This organization is archived")
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "fixed"})).status_code == 200


@pytest.mark.asyncio
async def test_only_the_logger_changes_an_activity(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    for user in (await make_bdm(db_session, manager, "college"), manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, user)
        assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "x"})).status_code == 403
        assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 403
    await as_user(client, await make_bdm(db_session, manager, "agent"))
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_timeline_is_visible_to_every_reader_of_the_organization(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(org["id"]))
    for user in (await make_bdm(db_session, manager, "college"), manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, user)
        data = (await client.get(org_activities(org["id"]))).json()
        assert data["total"] == 1 and data["items"][0]["bdm"]["id"] == str(bdm.id)
        assert data["items"][0]["permissions"]["can_change"] is False
    await as_user(client, await make_bdm(db_session, manager, "school"))
    assert (await client.get(org_activities(org["id"]))).status_code == 404
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(org_activities(org["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_manager_reads_the_team_only_and_bdm_filter_only_narrows(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(org["id"]))
    other_manager, outsider, outsider_org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(outsider_org["id"]))
    await as_user(client, manager)
    team = (await client.get(TEAM_ACTIVITIES)).json()
    assert {i["bdm"]["id"] for i in team["items"]} == {str(bdm.id)}
    assert team["counts"]["by_channel"]["call"] == 1
    narrowed = (await client.get(TEAM_ACTIVITIES, params={"bdm_user_id": str(outsider.id)})).json()
    assert narrowed["total"] == 0 and narrowed["counts"]["by_channel"]["call"] == 0
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 403
    await as_user(client, bdm)
    assert (await client.get(TEAM_ACTIVITIES)).status_code == 403


@pytest.mark.asyncio
async def test_refused_writes_are_logged_with_ids_only(client, db_session, caplog):
    """§12.3 S10: a 403 on a write leaves a warning with ids, route and status -- never the note."""
    logging.getLogger("app.bdm").disabled = False  # a migration test earlier in the run (alembic fileConfig) disables existing loggers
    manager, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="private words"))).json()
    await as_user(client, await make_bdm(db_session, manager, "college"))
    with caplog.at_level("WARNING", logger="app.bdm"):
        assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 403
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"], note="more words"))).status_code == 403
    refusals = [r for r in caplog.records if r.getMessage() == "bdm_activity_write_refused"]
    assert [r.extra_fields["route"] for r in refusals] == ["activity_delete", "activity_create"]
    assert all(r.extra_fields["status"] == 403 for r in refusals)
    assert "words" not in str([r.extra_fields for r in refusals])


@pytest.mark.asyncio
async def test_other_roles_are_refused(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    for role, division in (("it_admin", "it"), ("overseas_admin", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(ACTIVITIES)).status_code == 403
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 403
        assert (await client.get(TEAM_ACTIVITIES)).status_code == 403
