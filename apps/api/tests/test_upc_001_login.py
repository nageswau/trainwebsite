"""upc-001 AC3 / PU1 -- a manager signs in at /overseas/login, a head at /admin/login; any other portal gets the existing 'use the correct
portal' 403. The reset response's login_portal sends a head back to /admin. Unchanged auth code; this pins it for the new roles."""

import pytest

from app.services.provisioning import ADMIN_PORTAL_ROLES
from tests.upc001_helpers import PASSWORD, make_head, make_user

LOGIN = "/api/v1/auth/login"


async def _try(client, user, division):
    return await client.post(LOGIN, json={"email": user.email, "password": PASSWORD, "division": division})


@pytest.mark.asyncio
async def test_manager_signs_in_only_at_overseas(client, db_session):
    manager = await make_user(db_session, "partnership_manager", "overseas")
    assert (await _try(client, manager, "overseas")).status_code == 200
    response = await _try(client, manager, "global")
    assert response.status_code == 403 and "/overseas/login" in response.json()["detail"]


@pytest.mark.asyncio
async def test_head_signs_in_only_at_admin(client, db_session):
    head = await make_head(db_session)
    assert (await _try(client, head, "global")).status_code == 200
    response = await _try(client, head, "overseas")
    assert response.status_code == 403 and "/admin/login" in response.json()["detail"]


def test_head_is_an_admin_portal_role_and_manager_is_not():
    assert "partnership_head" in ADMIN_PORTAL_ROLES and "partnership_manager" not in ADMIN_PORTAL_ROLES
