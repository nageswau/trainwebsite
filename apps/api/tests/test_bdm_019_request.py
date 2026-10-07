"""bdm-019 -- the BDM's agent onboarding request (spec §4.1; AC1, A2, A8)."""

import pytest

from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm004_helpers import move
from tests.bdm018_helpers import audits, notices, request, requested, requests_of
from tests.bdm019_helpers import agent_world

AGREEMENT = "The agreement must be signed to request onboarding"


@pytest.mark.asyncio
async def test_the_owner_requests_agent_onboarding_at_agreement_signed(client, db_session):
    w = await agent_world(client, db_session)
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["pipeline"]["stage"] == "agreement_signed"
    assert detail["onboarding"] == {"request": None, "school": None, "agent": None, "can_request": True}
    org = await requested(client, w["org"], note="Ready")
    assert org["onboarding"]["request"]["status"] == "pending" and org["onboarding"]["can_request"] is False
    [row] = await requests_of(db_session, w["org"]["id"])
    assert (row.kind, row.status, row.note, row.agent_org_id) == ("agent", "pending", "Ready", None)
    request_id = str(row.id)  # audits() expires the session
    [audit] = await audits(db_session, w["org"]["id"], "bdm_organization.onboarding_requested")
    assert audit.metadata_json == {"request_id": request_id}
    [notice] = await notices(db_session, w["ids"]["admin"])
    assert notice.title == "Agent onboarding requested"
    assert w["org"]["code"] in notice.body
    assert notice.action_url == "/overseas/admin/agents"


@pytest.mark.asyncio
async def test_a_request_before_the_agreement_is_signed_is_422(client, db_session):  # AC1, backlog negative scenario
    w = await agent_world(client, db_session, mou=None)
    assert (await move(client, w["org"], "proposal_agreement")).status_code == 200
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["onboarding"]["can_request"] is False
    response = await request(client, w["org"])
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == AGREEMENT
    assert await requests_of(db_session, w["org"]["id"]) == []


@pytest.mark.asyncio
async def test_a_manual_move_to_agreement_signed_qualifies(client, db_session):  # A2: the stored stage is the evidence
    w = await agent_world(client, db_session, mou=None)
    assert (await move(client, w["org"], "agreement_signed")).status_code == 200
    assert (await request(client, w["org"])).status_code == 201


@pytest.mark.asyncio
async def test_a_second_request_while_one_is_pending_is_409(client, db_session):
    w = await agent_world(client, db_session)
    await requested(client, w["org"])
    response = await request(client, w["org"])
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "request_pending")


@pytest.mark.asyncio
@pytest.mark.parametrize(("actor", "status"), [("peer", 403), ("manager", 403), ("other_type", 404), ("it_admin", 403), ("admin", 403)])
async def test_only_the_owner_or_super_admin_may_request(client, db_session, actor, status):
    w = await agent_world(client, db_session)
    await login(client, w[actor])
    assert (await request(client, w["org"])).status_code == status
    await login(client, w["super_admin"])
    assert (await request(client, w["org"])).status_code == 201


@pytest.mark.asyncio
async def test_a_college_organization_has_no_onboarding(client, db_session):
    from tests.test_bdm_018_request import school_world_of

    college = await school_world_of(client, db_session, "college")
    assert (await client.get(f"{ORGS}/{college['id']}")).json()["organization"]["onboarding"] is None
    response = await request(client, college)
    assert (response.status_code, response.json()["detail"]) == (422, "Onboarding requests are for School or Agent organizations")


@pytest.mark.asyncio
async def test_managers_read_the_agent_onboarding_but_cannot_request(client, db_session):
    w = await agent_world(client, db_session)
    await login(client, w["manager"])
    detail = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]
    assert detail["onboarding"]["can_request"] is False
