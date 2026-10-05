"""AGN-002 -- AC09 / S2: staff never count as Masters; AC07: staff cannot manage the team."""

import pytest

from app.services.agent_orgs import count_active_masters, notification_recipients
from tests.agn001_helpers import client_for, login, mk_active_org, uniq
from tests.agn002_helpers import mk_staff

TEAM = "/api/v1/workflows/overseas/agent/team"


@pytest.mark.asyncio
async def test_staff_do_not_count_toward_the_master_limit(client, db_session):
    ctx = await mk_active_org(db_session, name="Limit Staff")
    for _ in range(3):
        await mk_staff(db_session, ctx["org"])
    assert await count_active_masters(db_session, ctx["org"].id) == 1
    await login(client, ctx["master"].email)
    for _ in range(2):
        response = await client.post(TEAM + "/masters", json={"full_name": "M", "email": f"{uniq('m')}@example.local"})
        assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_an_active_staff_member_does_not_let_the_last_master_go(client, db_session):
    ctx = await mk_active_org(db_session, name="Last Master")
    await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    response = await client.post(f"{TEAM}/masters/{ctx['member'].id}/deactivate")
    assert response.status_code == 422 and response.json()["detail"] == "An agency must keep at least one active Master"


@pytest.mark.asyncio
async def test_the_master_deactivate_route_does_not_touch_staff(client, db_session):
    ctx = await mk_active_org(db_session, name="Not A Master")
    staff = await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    response = await client.post(f"{TEAM}/masters/{staff['member'].id}/deactivate")
    assert response.status_code == 404 and response.json()["detail"] == "Master not found"


@pytest.mark.asyncio
async def test_commission_notifications_reach_masters_only(db_session):
    ctx = await mk_active_org(db_session, name="Notify Masters")
    staff = await mk_staff(db_session, ctx["org"])
    recipients = await notification_recipients(db_session, staff["user"])
    assert [u.id for u in recipients] == [ctx["master"].id]


@pytest.mark.asyncio
async def test_team_lists_masters_only(client, db_session):
    ctx = await mk_active_org(db_session, name="Masters Only")
    await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    body = (await client.get(TEAM)).json()
    assert [m["code"] for m in body["masters"]] == [f"{ctx['org'].prefix}-M001"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), [("get", ""), ("post", "/masters"), ("get", "/staff"), ("post", "/staff")])
async def test_staff_cannot_use_team_routes(db_session, method, path):
    ctx = await mk_active_org(db_session, name="Staff Blocked")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        kwargs = {"json": {"full_name": "X", "email": f"{uniq('x')}@example.local"}} if method == "post" else {}
        response = await getattr(c, method)(TEAM + path, **kwargs)
    assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can manage the team"
