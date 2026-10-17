"""AGN-024 K7 -- the Agent Approvals portal section is open to Super Admin as well as Overseas Admin."""

import pytest

from tests.agn001_helpers import client_for, mk_user

URL = "/api/v1/portal/overseas/admin/agents"


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("super_admin", "global"), ("overseas_admin", "overseas")])
async def test_agents_section_is_readable_by_admins(client, db_session, role, division):
    admin = await mk_user(db_session, role=role, division=division)
    async with client_for(admin.email, division) as c:
        response = await c.get(URL)
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Agent Masters"


@pytest.mark.asyncio
async def test_agents_section_refused_for_it_admin(client, db_session):
    admin = await mk_user(db_session, role="it_admin", division="it")
    async with client_for(admin.email, "it") as c:
        response = await c.get(URL)
    assert response.status_code == 403
