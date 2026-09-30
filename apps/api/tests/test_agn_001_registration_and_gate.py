import asyncio
import re

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AgentOrgMember, UserRoleAssignment
from tests.agn001_helpers import login, membership, mk_active_org, mk_user, org_of, register_agent, uniq


@pytest.mark.asyncio
async def test_registering_creates_one_pending_org_and_m001(client, db_session):  # AC01
    body = await register_agent(client, agency_name="Qwerty Overseas")
    member = await membership(db_session, body["user"]["id"])
    org = await org_of(db_session, body["user"]["id"])
    assert org.status == "pending" and org.name == "Qwerty Overseas" and org.master_seq == 1
    assert re.fullmatch(r"QWE\d*", org.prefix)
    assert member.seq == 1 and member.code == f"{org.prefix}-M001" and member.status == "active" and member.role == "master"
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.org_id == org.id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("agency_name", [None, "", "   "])
async def test_a_missing_agency_name_falls_back_to_the_full_name(client, db_session, agency_name):  # E2
    overrides = {"full_name": "Zulu Yankee"} | ({} if agency_name is None else {"agency_name": agency_name})
    body = await register_agent(client, **overrides)
    org = await org_of(db_session, body["user"]["id"])
    assert org.name == "Zulu Yankee" and re.fullmatch(r"ZUL\d*", org.prefix)


@pytest.mark.asyncio
async def test_registration_response_shape_is_unchanged(client):  # E8
    body = await register_agent(client, agency_name="Shape Check")
    assert set(body) == {"user", "expires_in_minutes"}
    assert "agent_membership" not in body["user"]


@pytest.mark.asyncio
async def test_an_agency_name_over_160_characters_is_422(client):
    response = await client.post("/api/v1/auth/register", json={"email": f"{uniq('long')}@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "Long Name", "division": "overseas", "account_type": "agent", "agency_name": "A" * 161})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_student_registration_creates_no_org(client, db_session):
    response = await client.post("/api/v1/auth/register", json={"email": f"{uniq('agn-student')}@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "A Student", "division": "overseas"})
    assert response.status_code == 201
    assert await membership(db_session, response.json()["user"]["id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("approval", "expected"), [("approved", "active"), ("pending", "pending"), ("rejected", "pending")])
async def test_a_legacy_agent_without_an_org_gets_one_on_login(client, db_session, approval, expected):  # E7, D10 mapping
    agent = await mk_user(db_session, role="agent", full_name="Legacy Person")
    db_session.add(UserRoleAssignment(user_id=agent.id, division="overseas", role="agent", approval_status=approval))
    await db_session.commit()
    await login(client, agent.email)
    org = await org_of(db_session, agent.id)
    assert org.status == expected and re.fullmatch(r"LEG\d*", org.prefix)
    await login(client, agent.email)  # idempotent: a second login adds nothing
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.user_id == agent.id)) == 1


@pytest.mark.asyncio
async def test_an_admin_created_agent_gets_a_pending_org(client, db_session):  # AC09
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.post("/api/v1/admin/users", json={"role": "agent", "division": "overseas", "email": f"{uniq('agn-admin-made')}@example.local", "full_name": "Made By Admin", "profile": {"agency_name": "Admin Made Agency"}})
    assert response.status_code == 201
    member = await membership(db_session, response.json()["id"])
    org = await org_of(db_session, response.json()["id"])
    assert org.status == "pending" and org.name == "Admin Made Agency" and member.code == f"{org.prefix}-M001"


@pytest.mark.asyncio
async def test_same_prefix_registrations_racing_get_distinct_prefixes(db_session):  # race: prefix
    async def one():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await register_agent(c, agency_name="Racecar Agency")

    first, second = await asyncio.gather(one(), one())
    prefixes = {(await org_of(db_session, b["user"]["id"])).prefix for b in (first, second)}
    assert len(prefixes) == 2


AGENT_ROUTES = [
    ("get", "/api/v1/workflows/overseas/agent/students"),
    ("get", "/api/v1/workflows/overseas/agent/commissions"),
    ("get", "/api/v1/workflows/overseas/applications"),
    ("get", "/api/v1/portal/overseas/agent/dashboard"),
    ("get", "/api/v1/portal/overseas/agent/students"),
    ("get", "/api/v1/portal/overseas/agent/commissions"),
]


async def _set_org_status(db, user_id, status):
    org = await org_of(db, user_id)
    org.status = status
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "rejected"])
async def test_a_pending_or_rejected_org_is_denied_every_agent_route(client, db_session, status):  # AC02
    ctx = await mk_active_org(db_session, name="Gate Agency")
    await _set_org_status(db_session, ctx["master"].id, status)
    await login(client, ctx["master"].email)
    for method, url in AGENT_ROUTES:
        response = await getattr(client, method)(url)
        assert response.status_code == 403 and response.json()["detail"] == "Agent registration is pending approval", url


@pytest.mark.asyncio
async def test_suspension_applies_on_the_next_request_and_reinstatement_restores(client, db_session):  # AC04
    ctx = await mk_active_org(db_session, name="Suspend Agency")
    await login(client, ctx["master"].email)
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).status_code == 200
    await _set_org_status(db_session, ctx["master"].id, "suspended")
    for method, url in AGENT_ROUTES:
        response = await getattr(client, method)(url)
        assert response.status_code == 403 and response.json()["detail"] == "Your agency's account is suspended", url
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await client.get("/api/v1/workflows/notifications")).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    await login(client, ctx["master"].email)
    await _set_org_status(db_session, ctx["master"].id, "active")
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).status_code == 200


@pytest.mark.asyncio
async def test_a_deactivated_member_whose_login_was_re_enabled_is_still_denied(client, db_session):  # E9, E10
    ctx = await mk_active_org(db_session, name="Deact Agency")
    member = await membership(db_session, ctx["master"].id)
    member.status = "deactivated"
    await db_session.commit()
    await login(client, ctx["master"].email)
    response = await client.get("/api/v1/workflows/overseas/agent/students")
    assert response.status_code == 403 and response.json()["detail"] == "Your Master account is deactivated"
