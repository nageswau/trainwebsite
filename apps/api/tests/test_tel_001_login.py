"""tel-001 AC3 -- a telecaller signs in at its team's portal; any other portal gets the existing 'use the correct portal' 403, which
names the right one. Unchanged auth code; this pins the behavior for the new roles."""

import pytest

from tests.tel001_helpers import PASSWORD, make_tl_manager, make_user

LOGIN = "/api/v1/auth/login"


async def _try(client, user, division):
    return await client.post(LOGIN, json={"email": user.email, "password": PASSWORD, "division": division})


@pytest.mark.asyncio
@pytest.mark.parametrize(("team", "other"), [("it", "overseas"), ("overseas", "it")])
async def test_telecaller_signs_in_only_at_its_team_portal(client, db_session, team, other):
    user = await make_user(db_session, "telecaller", team)
    assert (await _try(client, user, team)).status_code == 200
    response = await _try(client, user, other)
    assert response.status_code == 403 and f"/{team}/login" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manager_signs_in_only_at_admin(client, db_session):
    manager = await make_tl_manager(db_session)
    assert (await _try(client, manager, "global")).status_code == 200
    response = await _try(client, manager, "it")
    assert response.status_code == 403 and "/admin/login" in response.json()["detail"]
