"""bdm-018 -- the BDM's onboarding request (spec §5.1; AC1, H5, H6, H7, H8)."""

import pytest

from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm004_helpers import move
from tests.bdm005_helpers import change
from tests.bdm018_helpers import audits, notices, request, requested, requests_of, school_world


@pytest.mark.asyncio
async def test_the_owner_requests_onboarding_once_the_mou_is_signed(client, db_session):
    w = await school_world(client, db_session)
    org = await requested(client, w["org"], note="Ready from June")
    assert org["onboarding"]["school"] is None
    assert org["onboarding"]["can_request"] is False
    assert org["onboarding"]["request"]["status"] == "pending"
    [row] = await requests_of(db_session, w["org"]["id"])
    assert (row.status, row.kind, row.note, row.requested_by_user_id) == ("pending", "school", "Ready from June", w["ids"]["owner"])
    request_id = str(row.id)
    [audit] = await audits(db_session, w["org"]["id"], "bdm_organization.onboarding_requested")
    assert audit.metadata_json == {"request_id": request_id}
    [notice] = await notices(db_session, w["ids"]["admin"])
    assert notice.title == "School onboarding requested"
    assert w["org"]["code"] in notice.body
    assert notice.action_url == "/overseas/admin/schools"


@pytest.mark.asyncio
async def test_super_admin_may_request(client, db_session):
    w = await school_world(client, db_session)
    await login(client, w["super_admin"])
    assert (await request(client, w["org"])).status_code == 201


@pytest.mark.asyncio
async def test_an_active_mou_qualifies(client, db_session):
    w = await school_world(client, db_session)
    await change(client, w["org"], status="active", from_status="signed", valid_from="2026-01-10", valid_until="2099-01-09")
    assert (await request(client, w["org"])).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("mou", [None, {"status": "proposal_sent"}, {"status": "signed", "signed_on": "2020-01-10", "valid_until": "2021-01-09"}])
async def test_without_a_signed_or_active_mou_the_request_is_refused(client, db_session, mou):
    w = await school_world(client, db_session, mou=mou)
    response = await request(client, w["org"])
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "The MoU must be Signed or Active to request onboarding"
    assert await requests_of(db_session, w["org"]["id"]) == []


@pytest.mark.asyncio
async def test_a_second_request_while_one_is_pending_is_409(client, db_session):
    w = await school_world(client, db_session)
    await requested(client, w["org"])
    response = await request(client, w["org"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "request_pending"


@pytest.mark.asyncio
async def test_a_lost_or_archived_organization_is_refused(client, db_session):
    w = await school_world(client, db_session)
    assert (await client.post(f"{ORGS}/{w['org']['id']}/lost", json={"reason": "Went elsewhere"})).status_code == 200
    response = await request(client, w["org"])
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "organization_lost")
    await client.post(f"{ORGS}/{w['org']['id']}/revive", json={"reason": "Back"})
    assert (await client.post(f"{ORGS}/{w['org']['id']}/archive")).status_code == 200
    assert (await request(client, w["org"])).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(("actor", "status"), [("peer", 403), ("manager", 403), ("other_type", 404), ("it_admin", 403), ("admin", 403)])
async def test_only_the_owner_or_super_admin_may_request(client, db_session, actor, status):
    w = await school_world(client, db_session)
    await login(client, w[actor])
    assert (await request(client, w["org"])).status_code == status


@pytest.mark.asyncio
async def test_only_school_organizations_have_onboarding(client, db_session):
    w = await school_world(client, db_session)
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["onboarding"] == {"request": None, "school": None, "agent": None, "can_request": True}  # bdm-019 added `agent`
    # bdm-019 (DEC-SCOPE-107) gave Agent organizations their own handover (test_bdm_019_request); College ones still have none.
    other = await school_world_of(client, db_session, "college")
    detail = (await client.get(f"{ORGS}/{other['id']}")).json()["organization"]
    assert detail["onboarding"] is None
    response = await request(client, other)
    assert response.status_code == 422
    assert response.json()["detail"] == "Onboarding requests are for School or Agent organizations"


async def school_world_of(client, db, bdm_type):
    from tests.bdm005_helpers import started, world

    w = await world(client, db, bdm_type)
    await started(client, w["org"], status="signed", signed_on="2026-01-10")
    return w["org"]


@pytest.mark.asyncio
async def test_can_request_is_false_before_the_mou_is_signed(client, db_session):
    w = await school_world(client, db_session, mou=None)
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["onboarding"]["can_request"] is False
    w2 = await school_world(client, db_session)
    await login(client, w2["manager"])
    detail = (await client.get(f"{ORGS}/{w2['org']['id']}")).json()["organization"]
    assert detail["onboarding"]["can_request"] is False  # managers read only (H5)


@pytest.mark.asyncio
async def test_a_signed_mou_is_needed_even_after_a_manual_move_to_signed(client, db_session):
    w = await school_world(client, db_session, mou=None)
    assert (await move(client, w["org"], "signed")).status_code == 200
    assert (await request(client, w["org"])).status_code == 422
