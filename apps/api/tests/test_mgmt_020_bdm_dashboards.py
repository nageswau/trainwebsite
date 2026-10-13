"""mgmt-020 -- GET /management/bdm: the §16 figure sets per BDM type, company-wide (spec BD1-BD12).

AC: every figure bdm-024 also shows equals the super admin's bdm-024 total for the same period (BD4/BD5). The test database is shared
and never truncated, so those are compared with bdm-024 read in the same test, and the other figures (BD6-BD11) as before/after deltas
over a fixed past period."""

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import update

from app.models import BdmActivity, BdmMou, BdmMouEvent, BdmOnboardingRequest, BdmOrganization
from app.services.bdm_appointments import IST
from tests.agn001_helpers import mk_active_org
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm024_helpers import appt, signed
from tests.enh016_helpers import make_school
from tests.test_bdm_023_dashboard import org_of

pytestmark = pytest.mark.asyncio

BDM = "/api/v1/management/bdm"
PERIOD = {"from": "2024-06-01", "to": "2024-06-30"}
IN = datetime(2024, 6, 12, 11, 0, tzinfo=IST)
OUT = datetime(2024, 7, 1, 0, 30, tzinfo=IST)  # 30 minutes after the period's last IST day
KEYS = {
    "agent": ["agent_prospects", "meetings", "visits", "agreements", "new_agents", "active_agents", "agent_students", "applications", "enrollments"],
    "school": ["school_leads", "meetings", "visits", "proposals", "mous", "active_schools", "students"],
    "college": ["college_prospects", "meetings", "mous", "course_promotions", "internships", "student_registrations"],
}  # fmt: skip
# BD4: management key -> bdm-024 performance row; BD5: management key -> master view chain step (agent).
PERFORMANCE_ROW = {"agent_prospects": "P-04", "school_leads": "P-04", "college_prospects": "P-04", "meetings": "P-02", "agreements": "P-05",
                   "mous": "P-05", "agent_students": "P-07", "students": "P-07", "student_registrations": "P-07"}  # fmt: skip
MASTER_STEP = {"applications": "applications", "enrollments": "enrollment"}


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def figures(client, bdm_type: str, **params) -> dict:
    response = await client.get(BDM, params={"type": bdm_type, **PERIOD, **params})
    assert response.status_code == 200, response.text
    return {f["key"]: f for f in response.json()["figures"]}


def values(body: dict) -> dict:
    return {key: figure["value"] for key, figure in body.items()}


# --- access (BD12) ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_every_type(client, db_session, role):
    await as_role(client, db_session, role)
    for bdm_type, keys in KEYS.items():
        response = await client.get(BDM, params={"type": bdm_type})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["type"] == bdm_type and body["label"] == f"{bdm_type.capitalize()} BDM"
        assert [f["key"] for f in body["figures"]] == keys
        assert isinstance(body["bdm_count"], int) and body["as_of"]


@pytest.mark.parametrize(("role", "detail"), [("accountant", "Operational access required"), ("bdm_manager", "Management access required"),
                                              ("bdm", "Management access required")])  # fmt: skip
async def test_everyone_else_is_refused(client, db_session, role, detail):
    await as_role(client, db_session, role)
    response = await client.get(BDM)
    assert (response.status_code, response.json()["detail"]) == (403, detail)


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(BDM)).status_code == 401


# --- period and type (BD2, BD3) -------------------------------------------------------------------------------------------------------


async def test_the_defaults_are_agent_and_this_ist_month(client, db_session):
    await as_role(client, db_session, "partner")
    body = (await client.get(BDM)).json()
    today = datetime.now(IST).date()
    assert body["type"] == "agent"
    assert body["from"] == today.replace(day=1).isoformat() and body["to"][:7] == today.isoformat()[:7]


@pytest.mark.parametrize(("params", "detail"), [
    ({"from": "2025-03-31", "to": "2025-03-01"}, "The period must start on or before its end"),
    ({"from": "2024-01-01", "to": "2025-01-02"}, "The period can be at most 366 days"),
])  # fmt: skip
async def test_an_invalid_period_is_refused(client, db_session, params, detail):
    await as_role(client, db_session, "partner")
    response = await client.get(BDM, params=params)
    assert (response.status_code, response.json()["detail"]) == (422, detail)


async def test_an_unknown_type_is_refused(client, db_session):
    await as_role(client, db_session, "partner")
    assert (await client.get(BDM, params={"type": "corporate"})).status_code == 422


# --- AC: the figures equal the bdm-024 totals (BD4, BD5) -----------------------------------------------------------------------------


async def test_figures_equal_the_bdm_024_totals(client, db_session):
    manager = await make_manager(db_session)
    bdms = {t: await make_bdm(db_session, manager, t) for t in KEYS}
    for bdm_type, bdm in bdms.items():  # one meeting, one new organization and one signed MoU per type, inside the period
        org = await org_of(client, bdm, org_type=bdm_type)
        await db_session.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(created_at=IN))
        await appt(db_session, bdm.id, org, IN)
        await signed(db_session, org, bdm.id, IN)

    await as_role(client, db_session, "super_admin")
    performance = (await client.get("/api/v1/bdm/manager/performance", params=PERIOD)).json()
    master = (await client.get("/api/v1/bdm/manager/hierarchy")).json()
    management = {t: await figures(client, t) for t in KEYS}

    cells = {row["key"]: {c["type"]: c["value"] for c in row["cells"]} for row in performance["rows"]}
    for bdm_type, body in management.items():
        for key in KEYS[bdm_type]:
            if key in PERFORMANCE_ROW:
                assert body[key]["value"] == cells[PERFORMANCE_ROW[key]][bdm_type], (bdm_type, key)
                assert body[key]["basis"] == "period"
        assert management[bdm_type]["meetings"]["value"] >= 1
        assert (await client.get(BDM, params={"type": bdm_type, **PERIOD})).json()["bdm_count"] == cells["P-01"][bdm_type]
    agent = next(t for t in master["types"] if t["type"] == "agent")
    steps = {step["key"]: total for step, total in zip(agent["chain"], agent["totals"], strict=True)}
    for key, step in MASTER_STEP.items():
        assert management["agent"][key]["value"] == steps[step] and management["agent"][key]["basis"] == "now"


# --- the other figures (BD6-BD11), as deltas -----------------------------------------------------------------------------------------


async def test_visits_count_the_types_own_visit_activities_in_the_period(client, db_session):
    manager = await make_manager(db_session)
    agent_bdm, college_bdm = await make_bdm(db_session, manager, "agent"), await make_bdm(db_session, manager, "college")
    org = await org_of(client, agent_bdm, org_type="agent")
    await as_role(client, db_session, "partner")
    before = {t: values(await figures(client, t)) for t in ("agent", "school")}
    for bdm, channel, at in ((agent_bdm, "visit", IN), (agent_bdm, "visit", IN), (agent_bdm, "visit", OUT), (agent_bdm, "meeting", IN),
                             (college_bdm, "visit", IN)):  # fmt: skip
        db_session.add(BdmActivity(bdm_user_id=bdm.id, organization_id=org["id"], channel=channel, occurred_at=at))
    await db_session.commit()
    after = {t: values(await figures(client, t)) for t in ("agent", "school")}
    assert after["agent"]["visits"] - before["agent"]["visits"] == 2
    assert after["school"]["visits"] == before["school"]["visits"]


async def test_proposals_count_school_moves_to_proposal_sent(client, db_session):
    manager = await make_manager(db_session)
    school_bdm = await make_bdm(db_session, manager, "school")
    org = await org_of(client, school_bdm, org_type="school")
    await as_role(client, db_session, "partner")
    before = values(await figures(client, "school"))["proposals"]
    mou = BdmMou(organization_id=org["id"], created_by_user_id=school_bdm.id, status="proposal_sent")
    db_session.add(mou)
    await db_session.flush()
    for from_status, to_status, at in (("discussion_started", "proposal_sent", IN), ("proposal_sent", "proposal_sent", IN),
                                       ("discussion_started", "proposal_sent", OUT)):  # fmt: skip
        db_session.add(BdmMouEvent(mou_id=mou.id, actor_user_id=school_bdm.id, kind="status", from_status=from_status, to_status=to_status,
                                   changed=[], created_at=at))  # fmt: skip
    await db_session.commit()
    assert values(await figures(client, "school"))["proposals"] - before == 1


async def test_course_promotions_are_tracked_and_internships_are_not(client, db_session):
    manager = await make_manager(db_session)
    college_bdm = await make_bdm(db_session, manager, "college")
    org = await org_of(client, college_bdm, org_type="college")
    await as_role(client, db_session, "partner")
    before = await figures(client, "college")
    assert before["internships"]["tracked"] is False and before["internships"]["value"] is None
    assert before["internships"]["definition"].startswith("Not tracked")
    for at, status in ((IN, "completed"), (IN, "scheduled"), (OUT, "completed")):
        row = await appt(db_session, college_bdm.id, org, at, status=status)
        row.appointment_type = "course_promotion"
    await appt(db_session, college_bdm.id, org, IN)  # a college meeting is not a course promotion
    await db_session.commit()
    after = await figures(client, "college")
    assert after["course_promotions"]["tracked"] is True
    assert after["course_promotions"]["value"] - before["course_promotions"]["value"] == 1


async def test_new_and_active_agents(client, db_session):
    manager = await make_manager(db_session)
    agent_bdm = await make_bdm(db_session, manager, "agent")
    linked, suspended = await org_of(client, agent_bdm, org_type="agent"), await org_of(client, agent_bdm, org_type="agent")
    await as_role(client, db_session, "partner")
    before = values(await figures(client, "agent"))
    active_agency = (await mk_active_org(db_session, name=f"MG20 {uuid.uuid4().hex[:6]}"))["org"]
    other_agency = (await mk_active_org(db_session, name=f"MG20 {uuid.uuid4().hex[:6]}"))["org"]
    other_agency.status = "suspended"
    for org, agency, resolved_at in ((linked, active_agency, IN), (suspended, other_agency, OUT)):
        await db_session.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(agent_org_id=agency.id))
        db_session.add(BdmOnboardingRequest(organization_id=org["id"], kind="agent", status="completed", resolution="linked",
                                            requested_by_user_id=agent_bdm.id, resolved_at=resolved_at, agent_org_id=agency.id))  # fmt: skip
    await db_session.commit()
    after = values(await figures(client, "agent"))
    assert after["new_agents"] - before["new_agents"] == 1  # the one linked in the period
    assert after["active_agents"] - before["active_agents"] == 1  # the suspended agency is not active


async def test_active_schools_are_linked_schools_with_a_valid_tier(client, db_session):
    manager = await make_manager(db_session)
    school_bdm = await make_bdm(db_session, manager, "school")
    valid, expired = await org_of(client, school_bdm, org_type="school"), await org_of(client, school_bdm, org_type="school")
    await as_role(client, db_session, "partner")
    before = values(await figures(client, "school"))["active_schools"]
    good = (await make_school(db_session, tier="platinum"))["school"]
    old = (await make_school(db_session, tier="platinum", tier_valid_until=date(2024, 5, 31)))["school"]
    for org, school in ((valid, good), (expired, old)):
        await db_session.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(school_id=school.id))
    await db_session.commit()
    assert values(await figures(client, "school"))["active_schools"] - before == 1
