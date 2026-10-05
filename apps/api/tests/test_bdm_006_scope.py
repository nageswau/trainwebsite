"""bdm-006 -- who sees and changes what (AC6, AC7; spec §5.5, §5.7, §12.3)."""

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, bdm_with_org, create_appt, future

ACTIONS = (("confirm", None), ("cancel", {"reason": "x"}), ("reschedule", {"starts_at": future(200)}))


@pytest.mark.asyncio
async def test_scope_matrix(client, db_session):
    manager, owner, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    peer = await make_bdm(db_session, manager, "college")
    other_type = await make_bdm(db_session, manager, "school")
    other_manager = await make_manager(db_session)
    super_admin = await make_user(db_session, "super_admin", "global")
    it_admin = await make_user(db_session, "it_admin", "it")
    no_profile = await make_user(db_session, "bdm", "it")

    await login(client, peer)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert a["id"] not in [i["id"] for i in (await client.get(APPTS)).json()["items"]]
    refused = await client.post(APPTS, json=appt_payload(org))
    assert (refused.status_code, refused.json()["detail"]) == (403, "Only the assigned BDM can book appointments for this organization")
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "x"})).status_code == 404

    await login(client, other_type)
    hidden = await client.post(APPTS, json=appt_payload(org))
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "Organization not found")

    for reader in (manager, super_admin):
        await login(client, reader)
        detail = await client.get(f"{APPTS}/{a['id']}")
        assert detail.status_code == 200 and not any(detail.json()["appointment"]["permissions"].values())
        for action, body in ACTIONS:
            response = await client.post(f"{APPTS}/{a['id']}/{action}", json=body)
            assert (response.status_code, response.json()["detail"]) == (403, "Only the appointment's BDM can change it"), (reader.role, action)
        assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "x"})).status_code == 403
        assert (await client.post(APPTS, json=appt_payload(org))).status_code == 403
    await login(client, manager)
    assert [i["id"] for i in (await client.get(APPTS, params={"bdm_user_id": str(owner.id)})).json()["items"]] == [a["id"]]
    assert (await client.get(APPTS, params={"bdm_user_id": str(peer.id)})).json()["total"] == 0

    await login(client, other_manager)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert (await client.get(APPTS, params={"bdm_user_id": str(owner.id)})).json()["total"] == 0  # a filter never widens scope

    for user in (it_admin, no_profile):
        await login(client, user)
        assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 403
        assert (await client.get(APPTS)).status_code == 403


@pytest.mark.asyncio
async def test_archived_organization_blocks_create_but_not_existing_appointments(client, db_session):
    """AC6 / A4."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    refused = await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))
    assert (refused.status_code, refused.json()["detail"]) == (422, "This organization is archived — restore it before booking")
    detail = (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]
    assert detail["organization"]["archived"] is True
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "moved"})).status_code == 200
    assert (await client.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "College archived"})).status_code == 200


@pytest.mark.asyncio
async def test_reassigned_organization_keeps_appointments_with_their_bdm(client, db_session):
    """Review Focus 5: ownership is fixed (bdm-025 moves portfolios)."""
    manager, owner, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    new_assignee = await make_bdm(db_session, manager, "college")
    await login(client, manager)
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(new_assignee.id)})).status_code == 200
    await login(client, owner)
    assert (await client.post(f"{APPTS}/{a['id']}/confirm")).status_code == 200
    assert (await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))).status_code == 403  # no longer assigned
    await login(client, new_assignee)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert (await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))).status_code == 201
