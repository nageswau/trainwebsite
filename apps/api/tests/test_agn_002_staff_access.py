"""AGN-002 -- AC07/AC09 outside the team routes: staff reach organisation students/applications, never commissions."""

import pytest
from sqlalchemy import select

from app.models import AgentStudent
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user
from tests.agn002_helpers import mk_staff


async def _org_with_student(db_session, name: str):
    ctx = await mk_active_org(db_session, name=name)
    student = await mk_user(db_session, role="overseas_student", full_name=f"{name} Student")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active"))
    await db_session.commit()
    return ctx, student


@pytest.mark.asyncio
async def test_staff_see_the_organisations_students(db_session):
    # AGN-004 G4 (DEC-SCOPE-042, owner-approved 2026-09-30) narrows S1: Staff see only the students assigned to them.
    ctx, student = await _org_with_student(db_session, "Staff Sees")
    other = await mk_user(db_session, role="overseas_student", full_name="Staff Sees Unassigned")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=other.id, status="active"))
    staff = await mk_staff(db_session, ctx["org"])
    link = await db_session.scalar(select(AgentStudent).where(AgentStudent.student_id == student.id))
    link.assigned_member_id = staff["member"].id
    await db_session.commit()
    async with client_for(staff["user"].email) as c:
        response = await c.get("/api/v1/workflows/overseas/agent/students")
        assert response.status_code == 200 and str(student.id) in response.text and str(other.id) not in response.text
        assert (await c.get("/api/v1/portal/overseas/agent/students")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "detail"), [
    ("get", "/api/v1/workflows/overseas/agent/commissions", "Only an agency Master can view commissions"),
    ("post", "/api/v1/workflows/overseas/agent/commissions/00000000-0000-0000-0000-000000000000/claim", "Only an agency Master can view commissions"),
    ("get", "/api/v1/portal/overseas/agent/commissions", "Only an agency Master can open this page"),
    ("get", "/api/v1/portal/overseas/agent/team", "Only an agency Master can open this page"),
])
async def test_staff_are_refused_master_only_pages(db_session, method, path, detail):
    ctx = await mk_active_org(db_session, name="Staff Refused")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        response = await getattr(c, method)(path)
    assert response.status_code == 403 and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_staff_dashboard_and_reports_leave_out_commission_figures(db_session):
    ctx = await mk_active_org(db_session, name="Staff Figures")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        dashboard = (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()
        reports = (await c.get("/api/v1/portal/overseas/agent/reports")).json()
    assert "Claimable commission" not in str(dashboard) and "'Claims'" not in str(dashboard)
    assert "commission" not in str(reports["rows"]).lower()
    async with client_for(ctx["master"].email) as m:
        assert "Claimable commission" in str((await m.get("/api/v1/portal/overseas/agent/dashboard")).json())


@pytest.mark.asyncio
async def test_auth_me_reports_the_member_role(db_session):
    ctx = await mk_active_org(db_session, name="Me Role")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "staff"
    async with client_for(ctx["master"].email) as m:
        assert (await m.get("/api/v1/auth/me")).json()["agent_member_role"] == "master"
    student = await mk_user(db_session, role="overseas_student")
    async with client_for(student.email) as s:
        assert (await s.get("/api/v1/auth/me")).json()["agent_member_role"] is None


@pytest.mark.asyncio
async def test_admin_lists_show_masters_only_and_staff_cannot_be_approved_as_agents(client, db_session):
    ctx = await mk_active_org(db_session, name="Admin View Staff")
    staff = await mk_staff(db_session, ctx["org"])
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    orgs = (await client.get("/api/v1/overseas-admin/agent-orgs", params={"q": ctx["org"].prefix})).json()["items"]
    mine = next(o for o in orgs if o["id"] == str(ctx["org"].id))
    assert [m["code"] for m in mine["masters"]] == [f"{ctx['org'].prefix}-M001"]
    assert (await client.get("/api/v1/overseas-admin/agent-orgs", params={"q": staff["member"].code})).json()["total"] == 0
    assert str(staff["user"].id) not in (await client.get("/api/v1/overseas-admin/agents")).text
    response = await client.post(f"/api/v1/overseas-admin/agents/{staff['user'].id}/approve")
    assert response.status_code == 422 and response.json()["detail"] == "Staff accounts are managed by their agency"
    # Final review #1: the admin portal's "Agent Masters" page lists Masters only.
    masters_page = (await client.get("/api/v1/portal/overseas/admin/agents")).json()
    assert f"{ctx['org'].prefix}-M001" in str(masters_page) and staff["member"].code not in str(masters_page)
