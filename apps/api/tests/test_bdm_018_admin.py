"""bdm-018 -- the Overseas Admin queue, reject and link (spec §5.2-§5.4; AC2, AC3, H3, H7, H8)."""

from uuid import UUID

import pytest

from app.models import BdmOrganization
from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import ORGS
from tests.bdm018_helpers import QUEUE, SCHOOLS, audits, notices, pending_request, queue_item, requested, requests_of, school_payload, school_world, user


async def _school(client, **overrides) -> dict:
    response = await client.post(SCHOOLS, json=school_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def _org(db, org_id: str) -> BdmOrganization:
    db.expire_all()
    return await db.get_one(BdmOrganization, UUID(org_id))


@pytest.mark.asyncio
async def test_the_queue_lists_a_pending_request_with_the_organization_prefill(client, db_session):
    w = await pending_request(client, db_session)
    item = w["item"]
    assert item["status"] == "pending"
    assert item["organization"]["code"] == w["org"]["code"]
    assert item["organization"]["name"] == w["org"]["name"]
    assert item["organization"]["city"] == "Kochi"
    assert item["primary_contact"]["name"] == "Dr Rao"
    assert item["mou"] == {"reference": None, "signed_on": "2026-01-10"}
    assert item["requested_by"]["id"] == str(w["ids"]["owner"])
    assert item["assigned_bdm"]["id"] == str(w["ids"]["owner"])
    assert item["school"] is None and item["resolution"] is None


@pytest.mark.asyncio
async def test_pending_is_oldest_first_and_status_filters(client, db_session):
    first = await pending_request(client, db_session)
    second = await pending_request(client, db_session)
    page = (await client.get(QUEUE, params={"limit": 100})).json()
    ids = [i["id"] for i in page["items"]]
    if first["item"]["id"] in ids and second["item"]["id"] in ids:
        assert ids.index(first["item"]["id"]) < ids.index(second["item"]["id"])
    assert all(i["status"] == "pending" for i in page["items"])
    rejected = (await client.get(QUEUE, params={"status": "rejected"})).json()
    assert all(i["status"] == "rejected" for i in rejected["items"])
    assert (await client.get(QUEUE, params={"status": "bogus"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [("bdm", "overseas"), ("bdm_manager", "global"), ("it_admin", "it"), ("school_coordinator", "overseas")])
async def test_only_overseas_admin_or_super_admin_reads_the_queue(client, db_session, role):
    w = await pending_request(client, db_session)
    await login(client, await make_user(db_session, *role))
    assert (await client.get(QUEUE)).status_code == 403
    assert (await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "No"})).status_code == 403
    assert (await client.post(f"{QUEUE}/{w['item']['id']}/link", json={"school_code": "ABCDEFGH"})).status_code == 403
    await login(client, w["super_admin"])
    assert (await client.get(QUEUE)).status_code == 200


@pytest.mark.asyncio
async def test_the_queue_requires_authentication(client):
    assert (await client.get(QUEUE)).status_code == 401


@pytest.mark.asyncio
async def test_reject_stores_the_reason_notifies_the_bdm_and_allows_a_new_request(client, db_session):
    w = await pending_request(client, db_session)
    response = await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "Board details missing"})
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["reject_reason"]) == ("rejected", "Board details missing")
    [notice] = await notices(db_session, w["ids"]["owner"])
    assert notice.title == "School onboarding not approved"
    assert "Board details missing" in notice.body
    assert notice.action_url == f"/bdm/organizations/{w['org']['id']}"
    assert len(await audits(db_session, w["item"]["id"], "bdm_onboarding_request.rejected")) == 1
    again = await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "Again"})
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "request_resolved")
    await login(client, await user(db_session, w["ids"]["owner"]))
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]["onboarding"]
    assert detail["request"]["status"] == "rejected" and detail["request"]["reject_reason"] == "Board details missing"
    assert detail["can_request"] is True
    await requested(client, w["org"])
    assert [r.status for r in await requests_of(db_session, w["org"]["id"])] == ["rejected", "pending"]


@pytest.mark.asyncio
async def test_reject_needs_a_reason(client, db_session):
    w = await pending_request(client, db_session)
    assert (await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "  "})).status_code == 422
    assert (await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={})).status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_request_is_404(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"{QUEUE}/{missing}/reject", json={"reason": "No"})).status_code == 404
    assert (await client.post(f"{QUEUE}/{missing}/link", json={"school_code": "ABCDEFGH"})).status_code == 404


@pytest.mark.asyncio
async def test_link_an_existing_school_links_both_ways(client, db_session):
    w = await pending_request(client, db_session)
    school = await _school(client)
    response = await client.post(f"{QUEUE}/{w['item']['id']}/link", json={"school_code": school["school_code"].lower()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["resolution"], body["school"]["id"]) == ("completed", "linked", school["id"])
    assert str((await _org(db_session, w["org"]["id"])).school_id) == school["id"]
    assert len(await audits(db_session, w["item"]["id"], "bdm_onboarding_request.linked")) == 1
    [notice] = await notices(db_session, w["ids"]["owner"])
    assert notice.title == "School onboarded" and school["school_code"] in notice.body
    await login(client, await user(db_session, w["ids"]["owner"]))
    onboarding = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]["onboarding"]
    assert onboarding["school"] == {"name": school["name"], "school_code": school["school_code"]}
    assert onboarding["can_request"] is False


@pytest.mark.asyncio
async def test_link_refuses_an_unknown_code_a_school_linked_elsewhere_and_a_resolved_request(client, db_session):
    first = await pending_request(client, db_session)
    school = await _school(client)
    unknown = await client.post(f"{QUEUE}/{first['item']['id']}/link", json={"school_code": "ZZZZZZZZ"})
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No School has that School ID")
    assert (await client.post(f"{QUEUE}/{first['item']['id']}/link", json={"school_code": school["school_code"]})).status_code == 200
    resolved = await client.post(f"{QUEUE}/{first['item']['id']}/link", json={"school_code": school["school_code"]})
    assert (resolved.status_code, resolved.json()["detail"]["code"]) == (409, "request_resolved")
    second = await pending_request(client, db_session)
    taken = await client.post(f"{QUEUE}/{second['item']['id']}/link", json={"school_code": school["school_code"]})
    assert (taken.status_code, taken.json()["detail"]["code"]) == (409, "school_linked")
    assert (await queue_item(client, second["org"]["id"]))["status"] == "pending"


@pytest.mark.asyncio
async def test_a_linked_organization_cannot_request_again(client, db_session):
    w = await pending_request(client, db_session)
    school = await _school(client)
    await client.post(f"{QUEUE}/{w['item']['id']}/link", json={"school_code": school["school_code"]})
    await login(client, await user(db_session, w["ids"]["owner"]))
    response = await client.post(f"{ORGS}/{w['org']['id']}/onboarding-request", json={})
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "already_linked")


@pytest.mark.asyncio
async def test_a_bdm_never_reaches_school_portal_routes(client, db_session):
    await school_world(client, db_session)  # the School BDM is signed in
    for path in ("/api/v1/school/students", "/api/v1/school/analytics/scorecards"):
        assert (await client.get(path)).status_code == 403, path
