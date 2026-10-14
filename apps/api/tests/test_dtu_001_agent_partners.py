"""dtu-001 §6: agents browse the published catalogue; only a Master gets the agent commission."""

import pytest

from app.models import AgentOrg
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_staff
from tests.test_dtu_001_catalogue import _published

URL = "/api/v1/workflows/overseas/agent/crm/partner-universities"


@pytest.mark.asyncio
async def test_master_sees_the_rate_staff_do_not(client, db_session):
    uni = await _published(client, db_session)
    org = await mk_active_org(db_session)
    staff = await mk_staff(db_session, org["org"])
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        items = (await master.get(URL, params={"q": uni["name"]})).json()["items"]
        assert items[0]["agent_commission"]["percent"] == "13.00" and items[0]["course_count"] == 1
        detail = (await master.get(f"{URL}/{uni['id']}")).json()["university"]
        assert detail["agent_commission"]["percent"] == "13.00" and detail["courses"][0]["campus"] == "Newport Campus"
    async with client_for(staff["user"].email) as s:
        r = await s.get(URL, params={"q": uni["name"]})
        assert r.status_code == 200 and r.json()["items"] and "agent_commission" not in r.text
        assert "agent_commission" not in (await s.get(f"{URL}/{uni['id']}")).text


@pytest.mark.asyncio
async def test_hidden_or_inactive_university_is_404(client, db_session):
    uni = await _published(client, db_session)
    assert (await client.post(f"/api/v1/partnership/universities/{uni['id']}/unpublish")).status_code == 200
    org = await mk_active_org(db_session)
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        assert (await master.get(f"{URL}/{uni['id']}")).status_code == 404
        assert all(i["id"] != uni["id"] for i in (await master.get(URL, params={"q": uni["name"]})).json()["items"])


@pytest.mark.asyncio
async def test_non_agents_are_refused(client, db_session):
    from tests.upc001_helpers import as_role

    for role, division in (("counselor", "overseas"), ("overseas_admin", "overseas"), ("student", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(URL)).status_code == 403
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["suspended", "pending"])
async def test_suspended_or_pending_agency_master_is_refused(client, db_session, status):
    uni = await _published(client, db_session)
    org = await mk_active_org(db_session)
    row = await db_session.get(AgentOrg, org["org"].id, populate_existing=True)
    row.status = status
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        assert (await master.get(URL)).status_code == 403
        assert (await master.get(f"{URL}/{uni['id']}")).status_code == 403


@pytest.mark.asyncio
async def test_partner_universities_portal_section_is_a_header_for_master_and_staff(db_session):
    org = await mk_active_org(db_session)
    staff = await mk_staff(db_session, org["org"])
    await db_session.commit()
    for email in (org["master"].email, staff["user"].email):
        async with client_for(email) as c:
            r = await c.get("/api/v1/portal/overseas/agent/partner-universities")
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Partner Universities"
