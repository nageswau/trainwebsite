"""bdm-019 -- Overseas Admin resolves agent requests (spec §4.2-4.5; AC2, A1, A8, A9)."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmOrganization
from tests.agn001_helpers import client_for, mk_active_org, uniq
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm018_helpers import QUEUE, SCHOOLS, notices, pending_request, queue_item, requested, requests_of, school_payload
from tests.bdm019_helpers import LINK_AGENT, agent_queue_item, agent_world, link_agent, pending_agent


async def _org_row(db, org_id: str) -> BdmOrganization:
    db.expire_all()
    return await db.get_one(BdmOrganization, uuid.UUID(org_id))


@pytest.mark.asyncio
async def test_the_queue_is_school_only_by_default_and_agent_on_request(client, db_session):
    w = await pending_agent(client, db_session)
    item = w["item"]
    assert item["kind"] == "agent" and item["agent_org"] is None and item["school"] is None
    assert item["organization"]["code"] == w["org"]["code"]
    default = (await client.get(QUEUE, params={"limit": 100})).json()
    assert all(i["kind"] == "school" for i in default["items"])
    assert w["org"]["id"] not in {i["organization"]["id"] for i in default["items"]}
    school = await pending_request(client, db_session)
    agent_ids = set()
    offset = 0
    while True:
        page = (await client.get(QUEUE, params={"kind": "agent", "limit": 100, "offset": offset})).json()
        agent_ids |= {i["organization"]["id"] for i in page["items"]}
        offset += 100
        if offset >= page["total"]:
            break
    assert school["org"]["id"] not in agent_ids
    assert (await client.get(QUEUE, params={"kind": "college"})).status_code == 422


@pytest.mark.asyncio
async def test_linking_by_agent_code_completes_the_request_and_tells_the_bdm(client, db_session):  # positive scenario
    w = await pending_agent(client, db_session)
    code, agency_id, agency_name = w["agency"]["org"].prefix, w["agency"]["org"].id, w["agency"]["org"].name  # helpers expire the session
    response = await link_agent(client, w["item"]["id"], code.lower())  # codes match case-insensitively
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["resolution"], body["kind"]) == ("completed", "linked", "agent")
    assert body["agent_org"] == {"id": str(agency_id), "name": agency_name, "prefix": code, "status": "active"}
    assert (await _org_row(db_session, w["org"]["id"])).agent_org_id == agency_id
    [row] = await requests_of(db_session, w["org"]["id"])
    assert (row.agent_org_id, row.school_id, row.resolved_by_user_id) == (agency_id, None, w["ids"]["admin"])
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(row.id), AuditLog.action == "bdm_onboarding_request.linked"))
    assert audit.metadata_json == {"organization_id": w["org"]["id"], "agent_org_id": str(agency_id)}
    [notice] = await notices(db_session, w["ids"]["owner"])
    assert notice.title == "Agent onboarded"
    assert code in notice.body and notice.action_url == f"/bdm/organizations/{w['org']['id']}"


@pytest.mark.asyncio
async def test_link_agent_refusals(client, db_session):
    w = await pending_agent(client, db_session)
    rid = w["item"]["id"]
    unknown = await link_agent(client, rid, "ZZZZZZZZ")
    assert (unknown.status_code, unknown.json()["detail"]) == (422, "No agent organization has that code")
    assert (await link_agent(client, str(uuid.uuid4()), w["agency"]["org"].prefix)).status_code == 404
    assert (await client.post(LINK_AGENT.format(rid=rid), json={"agent_code": ""})).status_code == 422
    assert (await client.post(LINK_AGENT.format(rid=rid), json={"agent_code": "X", "extra": 1})).status_code == 422
    # The agency is already linked to another organization: 1:1 (AC2)
    other = await pending_agent(client, db_session)
    assert (await link_agent(client, other["item"]["id"], w["agency"]["org"].prefix)).status_code == 200
    taken = await link_agent(client, rid, w["agency"]["org"].prefix)
    assert (taken.status_code, taken.json()["detail"]["code"]) == (409, "agent_org_linked")
    # A resolved request
    assert (await link_agent(client, other["item"]["id"], (await mk_active_org(db_session, name=f"N {uniq()}"))["org"].prefix)).status_code == 409


@pytest.mark.asyncio
async def test_a_school_request_cannot_be_linked_to_an_agency_nor_an_agent_request_to_a_school(client, db_session):
    s = await pending_request(client, db_session)
    agency = await mk_active_org(db_session, name=f"Agency {uniq()}")
    wrong = await link_agent(client, s["item"]["id"], agency["org"].prefix)
    assert (wrong.status_code, wrong.json()["detail"]) == (422, "This request is for a School organization")
    a = await pending_agent(client, db_session)
    wrong = await client.post(f"{QUEUE}/{a['item']['id']}/link", json={"school_code": "ABC123"})
    assert (wrong.status_code, wrong.json()["detail"]) == (422, "This request is for an Agent organization")
    wrong = await client.post(SCHOOLS, json=school_payload(bdm_onboarding_request_id=a["item"]["id"]))
    assert (wrong.status_code, wrong.json()["detail"]) == (422, "This request is for an Agent organization")
    assert (await requests_of(db_session, a["org"]["id"]))[0].status == "pending"


@pytest.mark.asyncio
async def test_rejecting_an_agent_request_tells_the_bdm_who_may_request_again(client, db_session):
    w = await pending_agent(client, db_session)
    response = await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "Licence missing"})
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    await login(client, w["owner"])  # before notices() expires the session's users
    [notice] = await notices(db_session, w["ids"]["owner"])
    assert notice.title == "Agent onboarding not approved" and "Licence missing" in notice.body
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["onboarding"]["can_request"] is True
    await requested(client, w["org"])


@pytest.mark.asyncio
async def test_a_self_registered_pending_agency_can_be_linked(client, db_session):  # edge case: registered before the request
    from tests.agn001_helpers import org_of, register_agent

    w = await pending_agent(client, db_session)
    from app.models import User

    email = f"{uniq('bdm019-reg')}@example.local"
    await register_agent(client, email=email)
    await login(client, w["admin"])
    org = await org_of(db_session, await db_session.scalar(select(User.id).where(User.email == email)))
    assert org.status == "pending"
    response = await link_agent(client, w["item"]["id"], org.prefix)
    assert response.status_code == 200 and response.json()["agent_org"]["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "manager", "super_admin_ok"])
async def test_only_admins_link(client, db_session, actor):
    w = await pending_agent(client, db_session)
    if actor == "super_admin_ok":
        await login(client, w["super_admin"])
        assert (await link_agent(client, w["item"]["id"], w["agency"]["org"].prefix)).status_code == 200
        return
    await login(client, w[actor])
    assert (await link_agent(client, w["item"]["id"], w["agency"]["org"].prefix)).status_code == 403
    assert (await client.get(QUEUE, params={"kind": "agent"})).status_code == 403


@pytest.mark.asyncio
async def test_two_links_racing_for_one_agency_link_once(client, db_session):  # AC2 under concurrency
    first = await pending_agent(client, db_session)
    code, first_email = first["agency"]["org"].prefix, first["admin"].email  # the next world's commits expire these objects
    second = await pending_agent(client, db_session)
    async with client_for(first_email) as a, client_for(second["admin"].email) as b:
        results = await asyncio.gather(link_agent(a, first["item"]["id"], code), link_agent(b, second["item"]["id"], code))
    assert sorted(r.status_code for r in results) == [200, 409]
    links = [(await _org_row(db_session, w["org"]["id"])).agent_org_id for w in (first, second)]
    assert len([link for link in links if link]) == 1


@pytest.mark.asyncio
async def test_the_school_queue_item_shape_gains_kind_and_agent_org(client, db_session):
    s = await pending_request(client, db_session)
    item = await queue_item(client, s["org"]["id"])
    assert item["kind"] == "school" and item["agent_org"] is None


@pytest.mark.asyncio
async def test_an_agent_request_resolved_queue_lists_it_newest_first(client, db_session):
    w = await pending_agent(client, db_session)
    await link_agent(client, w["item"]["id"], w["agency"]["org"].prefix)
    item = await agent_queue_item(client, w["org"]["id"], status="completed")
    assert item["agent_org"]["prefix"] == w["agency"]["org"].prefix


@pytest.mark.asyncio
async def test_a_lost_agent_organization_is_refused(client, db_session):
    w = await agent_world(client, db_session)
    await client.post(f"{ORGS}/{w['org']['id']}/lost", json={"reason": "Gone"})
    response = await client.post(f"{ORGS}/{w['org']['id']}/onboarding-request", json={})
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "organization_lost")
