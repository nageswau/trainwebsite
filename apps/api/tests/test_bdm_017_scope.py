"""bdm-017 -- who may add and read an organization's leads (spec §4; L6 mirrors bdm-009 V1/V5)."""

import logging

import pytest

from tests.bdm001_helpers import make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import add_lead, as_user, lead_body, org_leads


@pytest.mark.asyncio
async def test_out_of_type_org_is_404_for_read_and_add(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session, "college")
    await as_user(client, await make_bdm(db_session, manager, "school"))
    assert (await client.get(org_leads(org["id"]))).status_code == 404
    assert (await client.post(org_leads(org["id"]), json=lead_body())).status_code == 404


@pytest.mark.asyncio
async def test_unknown_org_is_404(client, db_session):
    await bdm_with_org(client, db_session)
    assert (await client.post(org_leads("00000000-0000-0000-0000-000000000000"), json=lead_body())).status_code == 404


@pytest.mark.asyncio
async def test_same_type_bdm_who_is_not_assigned_gets_403_and_the_refusal_is_logged_without_pii(client, db_session, caplog):
    manager, _, org = await bdm_with_org(client, db_session)
    await as_user(client, await make_bdm(db_session, manager, "college"))
    body = lead_body(name="Secret Student")
    with caplog.at_level(logging.WARNING, logger="app.bdm"):
        response = await client.post(org_leads(org["id"]), json=body)
    assert (response.status_code, response.json()["detail"]) == (403, "Only the organization's assigned BDM can add leads")
    refused = [r for r in caplog.records if r.getMessage() == "bdm_lead_write_refused"]
    assert len(refused) == 1
    assert body["email"] not in str(refused[0].__dict__) and "Secret Student" not in str(refused[0].__dict__)


@pytest.mark.asyncio
async def test_managers_and_super_admin_read_but_never_add(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    await add_lead(client, org["id"])
    for user in (manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, user)
        data = (await client.get(org_leads(org["id"]))).json()
        assert data["total"] == 1 and data["items"][0]["bdm"]["id"] == str(bdm.id)
        assert (await client.post(org_leads(org["id"]), json=lead_body())).status_code == 403


@pytest.mark.asyncio
async def test_other_roles_are_refused(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    for role, division in (("it_admin", "it"), ("it_student", "it"), ("counselor", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(org_leads(org["id"]))).status_code == 403
        assert (await client.post(org_leads(org["id"]), json=lead_body())).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    client.cookies.clear()
    assert (await client.get(org_leads(org["id"]))).status_code == 401
    assert (await client.post(org_leads(org["id"]), json=lead_body())).status_code == 401


@pytest.mark.asyncio
async def test_archived_org_keeps_its_leads_readable_but_refuses_new_ones(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    await add_lead(client, org["id"])
    assert (await client.post(f"/api/v1/bdm/organizations/{org['id']}/archive")).status_code == 200
    response = await client.post(org_leads(org["id"]), json=lead_body())
    assert (response.status_code, response.json()["detail"]) == (422, "This organization is archived")
    assert (await client.get(org_leads(org["id"]))).json()["total"] == 1
