"""bdm-022 (DEC-SCOPE-109) -- a linked Agent organization's performance: the agency's own figures (AC1), offers by the confirmed rule
(AC2), revenue not tracked (AC3), aggregates only (AC4), the unlinked and suspended cases and the read scope (spec §1-§2)."""

import pytest

from tests.agn001_helpers import client_for
from tests.agn018_helpers import DASHBOARD_API, MASTER
from tests.agn022_helpers import network_world
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm005_helpers import world
from tests.bdm019_helpers import agent_world, link_agent, pending_agent

STEPS = ("students", "applications", "offers", "visa", "enrolled")
# network_world (agn018 hand counts): enquiry a1 a7, university_selection a6, offer a2, visa_documentation a3, enrolled a4; withdrawn
# a5 a10; the legacy `offer_received` a8 is an earlier stage name. The non-withdrawn rows sum to MASTER["applications"] (7).
BY_STAGE = [
    ("enquiry", 2), ("eligibility_evaluation", 0), ("university_selection", 1), ("offer", 1), ("visa_documentation", 1),
    ("status_tracking", 0), ("enrolled", 1), ("withdrawn", 2), ("earlier_stage_names", 1),
]


def _url(org_id: str) -> str:
    return f"{ORGS}/{org_id}/agent-performance"


async def _linked(client, db) -> dict:
    """bdm-019's handover, linking the AGN-018/022 dashboard agency; the organization's BDM is signed in on return."""
    n = await network_world(db)
    w = await pending_agent(client, db)
    assert (await link_agent(client, w["item"]["id"], n["org"].prefix)).status_code == 200
    await login(client, w["owner"])
    return w | {"n": n}


def _counts(body: dict) -> dict:
    return {s["key"]: s["count"] for s in body["steps"]}


@pytest.mark.asyncio
async def test_the_counts_equal_the_agencys_own_dashboard(client, db_session):  # AC1, positive scenario
    w = await _linked(client, db_session)
    response = await client.get(_url(w["org"]["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    agency = w["n"]["org"]
    assert body["linked"] is True and body["agency"] == {"name": agency.name, "prefix": agency.prefix, "status": "active"}
    async with client_for(w["n"]["master"].email) as c:
        own = (await c.get(DASHBOARD_API)).json()
    expected = {"students": own["students"], "applications": own["applications"], "offers": own["offers"], "visa": own["visa_approvals"],
                "enrolled": own["enrollments"], "revenue": None}
    assert _counts(body) == expected
    assert {k: expected[k] for k in STEPS} == {"students": 4, "applications": 7, "offers": 6, "visa": 1, "enrolled": 1}  # agn018 MASTER
    assert body["visa_applications"] == own["visa_applications"] == MASTER["visa_applications"]


@pytest.mark.asyncio
async def test_the_chain_is_in_source_order_with_definitions_and_revenue_not_tracked(client, db_session):  # AC2, AC3
    w = await _linked(client, db_session)
    body = (await client.get(_url(w["org"]["id"]))).json()
    assert [s["key"] for s in body["steps"]] == [*STEPS, "revenue"]
    assert all(s["definition"] for s in body["steps"])
    offers = next(s for s in body["steps"] if s["key"] == "offers")
    assert "offer" in offers["definition"].lower()
    revenue = body["steps"][-1]
    assert (revenue["tracked"], revenue["count"]) == (False, None)
    assert all(s["tracked"] for s in body["steps"][:-1])


@pytest.mark.asyncio
async def test_applications_by_stage_sum_to_the_applications_count(client, db_session):  # drill-down level
    w = await _linked(client, db_session)
    body = (await client.get(_url(w["org"]["id"]))).json()
    assert [(r["key"], r["count"]) for r in body["applications_by_stage"]] == BY_STAGE
    assert body["applications_by_stage"][1]["label"] == "Eligibility evaluation"
    open_rows = [r["count"] for r in body["applications_by_stage"] if r["key"] != "withdrawn"]
    assert sum(open_rows) == _counts(body)["applications"]


@pytest.mark.asyncio
async def test_an_empty_agency_has_zeros_and_no_earlier_stage_row(client, db_session):
    n = await network_world(db_session)
    w = await pending_agent(client, db_session)
    assert (await link_agent(client, w["item"]["id"], n["empty"]["org"].prefix)).status_code == 200
    await login(client, w["owner"])
    body = (await client.get(_url(w["org"]["id"]))).json()
    assert {k: v for k, v in _counts(body).items() if k != "revenue"} == dict.fromkeys(STEPS, 0)
    assert [r["key"] for r in body["applications_by_stage"]][-1] == "withdrawn"
    assert body["visa_applications"] == 0


@pytest.mark.asyncio
async def test_an_unlinked_organization_is_not_onboarded_yet(client, db_session):  # negative scenario
    w = await agent_world(client, db_session)
    response = await client.get(_url(w["org"]["id"]))
    assert response.status_code == 200
    assert response.json() | {"as_of": None} == {
        "organization_id": w["org"]["id"], "linked": False, "agency": None, "steps": [], "applications_by_stage": [], "visa_applications": None,
        "as_of": None,
    }


@pytest.mark.asyncio
async def test_a_suspended_agency_still_shows_its_figures_and_status(client, db_session):  # edge case: frozen, flagged
    w = await _linked(client, db_session)
    await login(client, w["admin"])
    assert (await client.post(f"/api/v1/overseas-admin/agent-orgs/{w['n']['org'].id}/suspend")).status_code == 200
    await login(client, w["owner"])
    body = (await client.get(_url(w["org"]["id"]))).json()
    assert body["agency"]["status"] == "suspended" and _counts(body)["students"] == 4


@pytest.mark.asyncio
async def test_no_student_member_or_money_data_leaves(client, db_session):  # AC4
    w = await _linked(client, db_session)
    text = (await client.get(_url(w["org"]["id"]))).text
    n = w["n"]
    for secret in (n["master"].email, n["master"].full_name, "Staff One", "Staff Four", "R1 ", "R2 ", "12000", "50000", '"amount"', '"currency"'):
        assert secret not in text, secret


@pytest.mark.asyncio
async def test_a_college_organization_has_no_agent_performance(client, db_session):
    w = await world(client, db_session, "college")
    response = await client.get(_url(w["org"]["id"]))
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent performance is only for Agent organizations"


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "status"), [("peer", 200), ("manager", 200), ("super_admin", 200), ("other_type", 404), ("other_manager", 404), ("it_admin", 403)])
async def test_read_scope(client, db_session, who, status):  # B1: load_scoped
    w = await _linked(client, db_session)
    await login(client, w[who])
    response = await client.get(_url(w["org"]["id"]))
    assert response.status_code == status, (who, response.text)
    if status == 200:
        assert _counts(response.json())["students"] == 4


@pytest.mark.asyncio
async def test_unknown_and_malformed_ids(client, db_session):
    await agent_world(client, db_session)
    assert (await client.get(_url("00000000-0000-0000-0000-000000000000"))).status_code == 404
    assert (await client.get(_url("not-a-uuid"))).status_code == 422
