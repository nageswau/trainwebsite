"""bdm-019 -- live Agent stages, volume counts and the derived agent status (spec §1 A3-A5, §4.6-4.7; AC3)."""

import pytest

from app.models import AgentOrg
from tests.agn001_helpers import uniq
from tests.agn022_helpers import NETWORK, network_world
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm004_helpers import move
from tests.bdm018_helpers import requested
from tests.bdm019_helpers import agent_world, link_agent, pending_agent

LIVE = ("agent_onboarding", "master_login_created", "staff_logins_created", "active_agent")
VOLUME = ("students", "applications", "enrollments")


def _steps(org: dict) -> dict:
    return {s["key"]: (s["state"], s.get("count")) for s in org["pipeline"]["steps"]}


async def _detail(client, org_id: str) -> dict:
    return (await client.get(f"{ORGS}/{org_id}")).json()["organization"]


async def _linked_to(client, db, agency: AgentOrg) -> dict:
    w = await pending_agent(client, db)
    assert (await link_agent(client, w["item"]["id"], agency.prefix)).status_code == 200
    await login(client, w["owner"])
    return w


@pytest.mark.asyncio
async def test_without_a_request_the_live_steps_await_handover(client, db_session):
    w = await agent_world(client, db_session)
    steps = _steps(await _detail(client, w["org"]["id"]))
    assert {k: steps[k] for k in LIVE} == dict.fromkeys(LIVE, ("awaiting_handover", None))
    assert {k: steps[k] for k in VOLUME} == dict.fromkeys(VOLUME, ("not_tracked", None))
    assert steps["agreement_signed"] == ("current", None)
    assert (await _detail(client, w["org"]["id"]))["pipeline"]["agent_status"] == "Agreement"


@pytest.mark.asyncio
async def test_a_pending_request_makes_agent_onboarding_current(client, db_session):
    w = await agent_world(client, db_session)
    org = await requested(client, w["org"])
    steps = _steps(org)
    assert steps["agreement_signed"] == ("done", None)
    assert [steps[k][0] for k in LIVE] == ["current", "upcoming", "upcoming", "upcoming"]
    assert {k: steps[k] for k in VOLUME} == dict.fromkeys(VOLUME, ("not_tracked", None))
    assert org["pipeline"]["agent_status"] == "Onboarding"
    assert org["pipeline"]["stage"] == "agreement_signed"  # live stages are never stored


@pytest.mark.asyncio
async def test_a_linked_agency_without_members_is_onboarding_with_master_login_current(client, db_session):
    agency = AgentOrg(name=f"Bare {uniq()}", prefix=uniq("B")[:8].upper(), status="pending", master_seq=0)
    db_session.add(agency)
    await db_session.commit()
    w = await _linked_to(client, db_session, agency)
    org = await _detail(client, w["org"]["id"])
    steps = _steps(org)
    assert [steps[k][0] for k in LIVE] == ["done", "current", "upcoming", "upcoming"]
    assert {k: steps[k] for k in VOLUME} == dict.fromkeys(VOLUME, ("upcoming", 0))
    assert org["pipeline"]["agent_status"] == "Onboarding"
    assert org["onboarding"]["agent"] == {
        "name": agency.name,
        "prefix": agency.prefix,
        "status": "pending",
        "master_login": False,
        "staff_count": 0,
        "counts": {"students": 0, "applications": 0, "enrollments": 0},
    }


@pytest.mark.asyncio
async def test_a_working_agency_shows_every_live_step_and_its_counts(client, db_session):  # positive scenario: Master Login, then Active
    n = await network_world(db_session)
    w = await _linked_to(client, db_session, n["org"])
    org = await _detail(client, w["org"]["id"])
    steps = _steps(org)
    assert [steps[k][0] for k in LIVE] == ["done"] * 4
    assert {k: steps[k] for k in VOLUME} == {k: ("done", NETWORK[k]) for k in VOLUME}
    assert org["pipeline"]["agent_status"] == "Active"
    agent = org["onboarding"]["agent"]
    assert (agent["master_login"], agent["staff_count"], agent["status"]) == (True, NETWORK["staff_count"], "active")
    assert agent["counts"] == {k: NETWORK[k] for k in VOLUME}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["suspend"])
async def test_a_suspended_agency_reads_inactive(client, db_session, action):  # edge case
    n = await network_world(db_session)
    w = await _linked_to(client, db_session, n["org"])
    await login(client, w["admin"])
    assert (await client.post(f"/api/v1/overseas-admin/agent-orgs/{n['org'].id}/{action}")).status_code == 200
    await login(client, w["owner"])
    org = await _detail(client, w["org"]["id"])
    assert org["pipeline"]["agent_status"] == "Inactive"
    assert _steps(org)["active_agent"][0] == "current"


@pytest.mark.asyncio
async def test_live_and_volume_steps_still_cannot_be_moved_to(client, db_session):  # AC3: not editable
    n = await network_world(db_session)
    w = await _linked_to(client, db_session, n["org"])
    for key in ("master_login_created", "active_agent", "students"):
        response = await move(client, w["org"], key, from_stage="agreement_signed")
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_the_manager_reads_the_same_live_view(client, db_session):
    n = await network_world(db_session)
    w = await _linked_to(client, db_session, n["org"])
    await login(client, w["manager"])
    org = await _detail(client, w["org"]["id"])
    assert org["pipeline"]["agent_status"] == "Active" and org["onboarding"]["agent"]["staff_count"] == NETWORK["staff_count"]
