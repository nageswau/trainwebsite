"""AGN-002 browser QA (2026-09-30) -- user-facing messages: QA-01 email, QA-02 deactivated staff, QA-03 ended session,
QA-07 staff pages never mention commissions."""

import pytest
from sqlalchemy import update

from app.models import User
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff

TEAM = "/api/v1/workflows/overseas/agent/team"
EMAIL_MESSAGE = "Enter a valid email address"
DEACTIVATED_STAFF = "Your account was deactivated by your agency. Contact your agency's Master."
SESSION_ENDED = "Your session has ended. Please sign in again."


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [STAFF, TEAM + "/masters"])
@pytest.mark.parametrize("email", ["short@nodot", "no-at-sign", "two@@example.local"])
async def test_an_invalid_email_reads_as_plain_language(client, db_session, path, email):  # QA-01
    ctx = await mk_active_org(db_session, name="Qa Email")
    await login(client, ctx["master"].email)
    response = await client.post(path, json={"full_name": "Someone", "email": email})
    assert response.status_code == 422
    assert EMAIL_MESSAGE in str(response.json()["detail"])
    assert "pattern" not in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_a_deactivated_staff_member_is_told_why(db_session):  # QA-02
    ctx = await mk_active_org(db_session, name="Qa Deact Msg")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as staff_client, client_for(ctx["master"].email) as master:
        assert (await master.post(f"{STAFF}/{staff['member'].id}/deactivate")).status_code == 200
        me = await staff_client.get("/api/v1/auth/me")
        assert me.status_code == 401 and me.json()["detail"] == DEACTIVATED_STAFF
        refreshed = await staff_client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 401 and refreshed.json()["detail"] == DEACTIVATED_STAFF


@pytest.mark.asyncio
async def test_other_inactive_accounts_keep_the_generic_message(client, db_session):  # QA-02 scope: staff only
    user = await mk_user(db_session, role="overseas_student")
    await login(client, user.email)
    await db_session.execute(update(User).where(User.id == user.id).values(active=False))
    await db_session.commit()
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["detail"] == "User unavailable"


@pytest.mark.asyncio
async def test_an_ended_session_says_to_sign_in_again(client, db_session):  # QA-03
    user = await mk_user(db_session, role="overseas_student")
    await login(client, user.email)
    await db_session.execute(update(User).where(User.id == user.id).values(session_version=User.session_version + 1))
    await db_session.commit()
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["detail"] == SESSION_ENDED


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "reports"])
async def test_staff_pages_never_mention_commissions(db_session, section):  # QA-07
    ctx = await mk_active_org(db_session, name=f"Qa Words {uniq()}")
    # AGN-003 (DEC-SCOPE-043 P1): Reports is off for staff by default; this test keeps its intent with it switched on.
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(staff["user"].email) as c:
        page = (await c.get(f"/api/v1/portal/overseas/agent/{section}")).json()
    assert "commission" not in str(page).lower()
    async with client_for(ctx["master"].email) as m:
        assert "commission" in str((await m.get(f"/api/v1/portal/overseas/agent/{section}")).json()).lower()
