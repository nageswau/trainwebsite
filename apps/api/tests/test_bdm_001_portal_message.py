"""bdm-001 browser QA-07: a sign-in at the wrong portal names the right one (BDMs are split across portals by module).
The password is checked first, so only a holder of valid credentials learns their own account's portal."""

import pytest

from tests.bdm001_helpers import PASSWORD, make_manager, make_user

LOGIN = "/api/v1/auth/login"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "tried", "named"),
    [("bdm", "it", "overseas", "/it/login"), ("bdm", "overseas", "it", "/overseas/login"), ("bdm_manager", "global", "it", "/admin/login"), ("counselor", "overseas", "it", "/overseas/login")],
)
async def test_wrong_portal_names_the_right_sign_in(client, db_session, role, division, tried, named):
    user = await make_manager(db_session) if role == "bdm_manager" else await make_user(db_session, role, division)
    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD, "division": tried})
    assert response.status_code == 403
    assert named in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_wrong_password_never_reveals_the_portal(client, db_session):
    user = await make_user(db_session, "bdm", "it")
    response = await client.post(LOGIN, json={"email": user.email, "password": "wrong-password-123", "division": "overseas"})
    assert response.status_code == 401 and "/it/login" not in response.text
