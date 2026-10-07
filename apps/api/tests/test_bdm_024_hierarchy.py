"""bdm-024 (DEC-SCOPE-113 P10/P11) -- GET /bdm/manager/hierarchy: the §6 master view, type -> BDMs -> linked organizations -> value chain
(Appendix B.6 V-A / V-S / V-C). Each organization's chain must equal its own panels (bdm-020/021/022); BDM and type totals are sums."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.models import BdmOrganization, OverseasApplication
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import ORGS
from tests.bdm024_helpers import career_done, perf_world
from tests.test_bdm_023_dashboard import org_of

HIERARCHY = "/api/v1/bdm/manager/hierarchy"
CHAINS = {
    "agent": ["students", "applications", "enrollment", "revenue"],
    "school": ["students", "profile_building", "career_university", "future_student"],
    "college": ["students", "training", "internship", "placement", "revenue"],
}


async def read(client, **params) -> dict:
    response = await client.get(HIERARCHY, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def panel(client, org_id: str, name: str) -> dict:
    response = await client.get(f"{ORGS}/{org_id}/{name}")
    assert response.status_code == 200, response.text
    return response.json()


def node(body: dict, bdm_type: str) -> dict:
    return next(t for t in body["types"] if t["type"] == bdm_type)


def bdm(body: dict, bdm_type: str, user) -> dict:
    return next(b for b in node(body, bdm_type)["bdms"] if b["id"] == str(user.id))


def add(values) -> list:
    """Column sums of chain counts (None stays None, revenue strings stay strings)."""
    out = []
    for column in zip(*values, strict=True):
        if column[0] is None:
            out.append(None)
        elif isinstance(column[0], str):
            out.append(str(sum((Decimal(v) for v in column), Decimal("0.00"))))
        else:
            out.append(sum(column))
    return out


async def world(client, db) -> dict:
    w = await perf_world(client, db)
    await career_done(db, w["school_student"])
    db.add(OverseasApplication(school_student_id=w["school_student"].id, university_id=(await mk_university(db)).id, intake="Fall 2027",
                               status="enquiry"))
    await db.commit()
    w["unlinked"] = await org_of(client, w["a1"], org_type="agent")  # not onboarded: counted, not listed
    w["archived"] = await org_of(client, w["c1"], org_type="college")
    await db.execute(update(BdmOrganization).where(BdmOrganization.id == w["archived"]["id"]).values(archived_at=datetime.now(UTC)))
    await db.commit()
    return w


@pytest.mark.asyncio
async def test_the_three_types_and_their_value_chains(client, db_session):
    w = await world(client, db_session)
    await login(client, w["manager"])
    body = await read(client)
    assert [t["type"] for t in body["types"]] == ["agent", "school", "college"]
    assert [t["label"] for t in body["types"]] == ["Agent BDM", "School BDM", "College BDM"]
    for t in body["types"]:
        assert [s["key"] for s in t["chain"]] == CHAINS[t["type"]]
        assert all(s["label"] and s["definition"] for s in t["chain"])
    assert [s["tracked"] for s in node(body, "agent")["chain"]] == [True, True, True, False]
    assert [s["tracked"] for s in node(body, "school")["chain"]] == [True, False, True, True]
    assert [s["tracked"] for s in node(body, "college")["chain"]] == [True, True, False, True, True]
    assert body["manager"] is None and body["as_of"]


@pytest.mark.asyncio
async def test_each_organization_reads_the_same_as_its_own_panels(client, db_session):
    w = await world(client, db_session)
    await login(client, w["manager"])
    body = await read(client)

    agent = bdm(body, "agent", w["a1"])["organizations"]
    assert [o["id"] for o in agent] == [w["org_a"]["id"]]
    steps = {s["key"]: s["count"] for s in (await panel(client, w["org_a"]["id"], "agent-performance"))["steps"]}
    assert agent[0]["counts"] == [steps["students"], steps["applications"], steps["enrolled"], None] == [4, 7, 1, None]

    school = bdm(body, "school", w["s1"])["organizations"]
    activity = await panel(client, w["org_s"]["id"], "school-activity")
    guidance = next(m["completed"] for m in activity["metrics"] if m["key"] == "career_guidance")
    assert school[0]["counts"] == [activity["total_students"], None, guidance, 1] == [3, None, 1, 1]

    college = bdm(body, "college", w["c1"])["organizations"]
    assert {o["id"] for o in college} == {w["org_c"]["id"], w["org_c2"]["id"]}
    assert [o["name"] for o in college] == sorted(o["name"] for o in college)
    business = await panel(client, w["org_c"]["id"], "business")
    funnel = {s["key"]: s["count"] for s in business["funnel"]}
    fees = next(line["amount"] for line in business["revenue"]["lines"] if line["key"] == "training")
    org_c = next(o for o in college if o["id"] == w["org_c"]["id"])
    assert org_c["counts"] == [funnel["registrations"], funnel["training"], None, funnel["placement"], fees] == [2, 0, None, 0, "1950.50"]
    org_c2 = next(o for o in college if o["id"] == w["org_c2"]["id"])
    assert org_c2["counts"] == [0, 0, None, 0, "0.00"]
    assert set(org_c) == {"id", "code", "name", "counts"}  # aggregates only: no student, contact or payment data


@pytest.mark.asyncio
async def test_totals_are_sums_and_unlinked_or_archived_organizations_are_not_listed(client, db_session):
    w = await world(client, db_session)
    await login(client, w["manager"])
    body = await read(client)
    a1 = bdm(body, "agent", w["a1"])
    assert (a1["organization_count"], a1["not_linked"], a1["active"]) == (1, 1, True)
    a2 = bdm(body, "agent", w["a2"])
    assert (a2["organizations"], a2["organization_count"], a2["active"], a2["totals"]) == ([], 0, False, [0, 0, 0, None])
    c1 = bdm(body, "college", w["c1"])
    assert w["archived"]["id"] not in [o["id"] for o in c1["organizations"]] and c1["organization_count"] == 2
    for t in body["types"]:
        for b in t["bdms"]:
            if b["organizations"]:
                assert b["totals"] == add([o["counts"] for o in b["organizations"]])
        assert t["totals"] == add([b["totals"] for b in t["bdms"]])
        assert t["organization_count"] == sum(b["organization_count"] for b in t["bdms"])
        assert t["not_linked"] == sum(b["not_linked"] for b in t["bdms"])
        assert t["bdm_count"] == sum(b["active"] for b in t["bdms"])
    assert node(body, "agent")["not_linked"] == 1


@pytest.mark.asyncio
async def test_another_team_is_excluded_and_super_admin_can_narrow(client, db_session):
    w = await world(client, db_session)
    await login(client, w["manager"])
    mine = await read(client)
    listed = {o["id"] for t in mine["types"] for b in t["bdms"] for o in b["organizations"]}
    assert w["org_x"]["id"] not in listed and str(w["x"].id) not in {b["id"] for t in mine["types"] for b in t["bdms"]}
    client.cookies.clear()
    await login(client, await make_user(db_session, "super_admin", "global"))
    narrowed = await read(client, manager_user_id=str(w["manager"].id))
    assert narrowed["manager"]["id"] == str(w["manager"].id)
    assert narrowed["types"] == mine["types"]
    r = await client.get(HIERARCHY, params={"manager_user_id": "not-a-uuid"})
    assert r.status_code == 422
