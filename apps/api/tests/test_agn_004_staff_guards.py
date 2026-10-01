"""AGN-004 G2/G3 -- staff keep AGN-002's reach: Team and Commissions stay Master-only (identical to AGN-002 S1; spec §5.1, AC10)."""

import pytest
import pytest_asyncio

from app.models import AgentOrg
from app.services.agent_orgs import count_active_masters, notification_recipients
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Guard Agency")
    # AGN-003 (DEC-SCOPE-043 P1, reconciled on merging `main`): Reports is off for staff by default; these page tests keep it on.
    return ctx | {"staff": await mk_staff(db_session, ctx["org"], can_view_reports=True)}


MASTER_ONLY = [
    ("get", "/api/v1/workflows/overseas/agent/team"),
    ("post", "/api/v1/workflows/overseas/agent/team/masters"),
    ("get", "/api/v1/workflows/overseas/agent/commissions"),
    ("get", "/api/v1/portal/overseas/agent/team"),
    ("get", "/api/v1/portal/overseas/agent/commissions"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), MASTER_ONLY)
async def test_staff_are_refused_master_only_pages(agency, method, url):
    async with client_for(agency["staff"]["user"].email) as c:
        if method == "post":
            response = await c.post(url, json={"full_name": "X", "email": "x-guard@example.local"})
        else:
            response = await c.get(url)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "students", "applications", "documents", "reports"])
async def test_staff_open_the_other_agent_pages(agency, section):
    async with client_for(agency["staff"]["user"].email) as c:
        response = await c.get(f"/api/v1/portal/overseas/agent/{section}")
    assert response.status_code == 200
    # The dashboard's description sentence mentions commissions; the KPI and report rows are what AGN-002 hides.
    assert "Claimable commission" not in response.text and "Paid commission" not in response.text


@pytest.mark.asyncio
async def test_staff_never_count_as_masters_or_get_commission_notifications(db_session, agency):
    assert await count_active_masters(db_session, agency["org"].id) == 1
    recipients = await notification_recipients(db_session, agency["staff"]["user"])
    assert [u.id for u in recipients] == [agency["master"].id]


@pytest.mark.asyncio
async def test_team_lists_masters_only(agency):
    async with client_for(agency["master"].email) as c:
        body = (await c.get("/api/v1/workflows/overseas/agent/team")).json()
    assert [m["code"] for m in body["masters"]] == [agency["member"].code]


@pytest.mark.asyncio
async def test_me_reports_the_member_role(agency):
    async with client_for(agency["staff"]["user"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "staff"
    async with client_for(agency["master"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "master"


@pytest.mark.asyncio
async def test_overseas_admin_cannot_approve_a_staff_user(db_session, agency):
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        response = await c.post(f"/api/v1/overseas-admin/agents/{agency['staff']['user'].id}/approve")
        listed = await c.get("/api/v1/overseas-admin/agents")
    assert response.status_code == 422 and response.json()["detail"] == "Staff accounts are managed by their agency"
    assert listed.status_code == 200 and agency["staff"]["user"].email not in listed.text


@pytest.mark.asyncio
async def test_suspended_agency_denies_its_staff(db_session, agency):
    org = await db_session.get(AgentOrg, agency["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(agency["staff"]["user"].email) as c:
        response = await c.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 403 and response.json()["detail"] == "Your agency's account is suspended"
