"""AGN-002 -- staff logins through the API (DEC-SCOPE-040; spec §6-§7; AGN-002-AC01..AC10)."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AgentOrg, AuditLog, User
from app.services import agent_orgs, provisioning
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff

NEW_PASSWORD = "Staff-Secret-Pass-1!"


async def _create(client, **overrides):
    return await client.post(STAFF, json={"full_name": "Rahul Staff", "email": f"{uniq('s')}@example.local", **overrides})


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


# --- AC01: codes -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_codes_are_s001_s002_and_independent_of_masters(client, db_session):
    ctx = await mk_active_org(db_session, name="Codes Agency")
    await login(client, ctx["master"].email)
    first, second = (await _create(client)).json(), (await _create(client)).json()
    prefix = ctx["org"].prefix
    assert [first["member"]["code"], second["member"]["code"]] == [f"{prefix}-S001", f"{prefix}-S002"]
    invited = await client.post("/api/v1/workflows/overseas/agent/team/masters", json={"full_name": "M2", "email": f"{uniq('m')}@example.local"})
    assert invited.json()["member"]["code"] == f"{prefix}-M002"


@pytest.mark.asyncio
async def test_two_agencies_each_start_at_s001(db_session):
    for name in ("Alpha Staff", "Beta Staff"):
        ctx = await mk_active_org(db_session, name=name)
        async with client_for(ctx["master"].email) as c:
            assert (await _create(c)).json()["member"]["code"] == f"{ctx['org'].prefix}-S001"


@pytest.mark.asyncio
async def test_concurrent_creates_get_distinct_codes(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name="Race Staff")
    async with client_for(ctx["master"].email) as a, client_for(ctx["master"].email) as b:
        responses = await asyncio.gather(_create(a), _create(b))
    assert sorted(r.status_code for r in responses) == [201, 201]
    assert sorted(r.json()["member"]["code"] for r in responses) == [f"{ctx['org'].prefix}-S001", f"{ctx['org'].prefix}-S002"]
    assert (await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)).staff_seq == 2


# --- AC02: the set-password email --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_reports_the_email_and_never_returns_the_token(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    ctx = await mk_active_org(db_session, name="Mail Agency")
    await login(client, ctx["master"].email)
    response = await _create(client, phone="+91 90000 00000")
    assert response.status_code == 201
    body = response.json()
    # `email_status` is the SMTP outcome (not configured in the test stack); the webhook send is captured above.
    assert body["email_status"] in {"sent", "not_configured", "failed"} and body["expires_at"] and "development_welcome_token" not in body
    assert body["member"] | {"id": None} == {
        "id": None, "code": f"{ctx['org'].prefix}-S001", "full_name": "Rahul Staff", "email": body["member"]["email"],
        "phone": "+91 90000 00000", "status": "active", "setup": "pending_setup",
    }
    staff = await db_session.scalar(select(User).where(User.email == body["member"]["email"]))
    assert staff.role == "agent" and staff.division == "overseas" and staff.active and staff.profile["registration_source"] == "agent_staff_create"
    token = next(p["reset_token"] for p in sent if p.get("to") == staff.email)
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 200
    signed_in = await client.post("/api/v1/auth/login", json={"email": staff.email, "password": NEW_PASSWORD, "division": "overseas"})
    assert signed_in.status_code == 200


@pytest.mark.asyncio
async def test_a_failed_send_keeps_the_account_and_says_so(client, db_session, monkeypatch):  # Review Focus 4
    async def fail(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(provisioning, "send_welcome_email", fail)
    ctx = await mk_active_org(db_session, name="No Mail Agency")
    await login(client, ctx["master"].email)
    response = await _create(client)
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    assert await db_session.scalar(select(User.id).where(User.email == response.json()["member"]["email"])) is not None


# --- validation and duplicates ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"full_name": "   ", "email": "a@example.local"}, {"full_name": "A", "email": "not-an-email"}, {"full_name": "A"}])
async def test_create_validates(client, db_session, body):
    ctx = await mk_active_org(db_session, name="Valid Agency")
    await login(client, ctx["master"].email)
    assert (await client.post(STAFF, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_an_existing_email_is_409_audited_and_not_numbered(client, db_session):
    ctx = await mk_active_org(db_session, name="Dup Staff")
    other = await mk_user(db_session, role="overseas_student")
    await login(client, ctx["master"].email)
    response = await _create(client, email=other.email.upper())
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    assert (await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)).staff_seq == 0
    rejected = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_create_rejected", AuditLog.entity_id == str(ctx["org"].id)))
    assert rejected is not None and other.email not in str(rejected.metadata_json)


# --- AC08 (create) and list ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_is_audited_without_personal_data(client, db_session):
    ctx = await mk_active_org(db_session, name="Audit Staff")
    await login(client, ctx["master"].email)
    body = (await _create(client)).json()
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_create", AuditLog.entity_id == str(ctx["org"].id)))
    assert log.entity_type == "agent_org" and log.user_id == ctx["master"].id
    assert log.metadata_json == {"member_id": body["member"]["id"], "code": body["member"]["code"]}


@pytest.mark.asyncio
async def test_list_is_paginated_in_code_order(client, db_session):
    ctx = await mk_active_org(db_session, name="List Staff")
    for _ in range(3):
        await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    first = (await client.get(STAFF, params={"limit": 2})).json()
    second = (await client.get(STAFF, params={"limit": 2, "offset": 2})).json()
    prefix = ctx["org"].prefix
    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
    assert [m["code"] for m in first["items"] + second["items"]] == [f"{prefix}-S001", f"{prefix}-S002", f"{prefix}-S003"]
    assert first["items"][0]["setup"] is None  # inserted with a password: set-up complete
    assert (await client.get(STAFF, params={"limit": 101})).status_code == 422


# --- AC10 (create part) -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_21st_staff_action_in_a_day_is_429_and_master_invites_are_unaffected(client, db_session):
    ctx = await mk_active_org(db_session, name="Throttle Staff")
    now = datetime.now(UTC)
    db_session.add_all(
        AuditLog(user_id=ctx["master"].id, action="agent_org.staff_create", entity_type="agent_org", entity_id=str(ctx["org"].id), outcome="created", metadata_json={}, created_at=now - timedelta(hours=1))
        for _ in range(agent_orgs.STAFF_ACTION_LIMIT)
    )
    await db_session.commit()
    await login(client, ctx["master"].email)
    response = await _create(client)
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == f"This agency has created or reset {agent_orgs.STAFF_ACTION_LIMIT} staff logins in the last 24 hours. Try again later."
    invite = await client.post("/api/v1/workflows/overseas/agent/team/masters", json={"full_name": "M", "email": f"{uniq('m')}@example.local"})
    assert invite.status_code == 201


# --- Task 5 helpers -------------------------------------------------------------------------------------------------------------------


async def _staff_via_api(client, monkeypatch) -> tuple[dict, str]:
    """Create a staff member as the signed-in Master and set their password; returns (member, email)."""
    sent = _capture(monkeypatch)
    member = (await _create(client)).json()["member"]
    token = next(p["reset_token"] for p in sent if p.get("to") == member["email"])
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 200
    return member, member["email"]


async def _staff_client(email: str, password: str = NEW_PASSWORD) -> httpx.AsyncClient:
    """A signed-in client for the staff member (own cookie jar); the caller closes it."""
    c = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    response = await c.post("/api/v1/auth/login", json={"email": email, "password": password, "division": "overseas"})
    assert response.status_code == 200, response.text
    return c


async def _login_status(email: str, password: str = NEW_PASSWORD) -> int:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return (await c.post("/api/v1/auth/login", json={"email": email, "password": password, "division": "overseas"})).status_code


# --- AC03: edit -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_changes_name_and_phone_only(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Edit Staff")
    await login(client, ctx["master"].email)
    member, _ = await _staff_via_api(client, monkeypatch)
    response = await client.patch(f"{STAFF}/{member['id']}", json={"full_name": "  Rahul K  ", "phone": "+91 1"})
    assert response.status_code == 200 and response.json()["member"]["full_name"] == "Rahul K" and response.json()["member"]["phone"] == "+91 1"
    assert (await client.patch(f"{STAFF}/{member['id']}", json={"phone": None})).json()["member"]["phone"] is None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_update", AuditLog.entity_id == str(ctx["org"].id)).order_by(AuditLog.created_at.desc()))
    assert log.metadata_json == {"member_id": member["id"], "code": member["code"], "fields": ["phone"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "detail"), [({}, "Nothing to update"), ({"email": "new@example.local"}, None), ({"full_name": None}, "Full name is required"), ({"full_name": "  "}, "Full name is required")])
async def test_edit_validates(client, db_session, monkeypatch, body, detail):
    ctx = await mk_active_org(db_session, name="Edit Valid")
    await login(client, ctx["master"].email)
    member, _ = await _staff_via_api(client, monkeypatch)
    response = await client.patch(f"{STAFF}/{member['id']}", json=body)
    assert response.status_code == 422
    if detail:
        assert detail in str(response.json()["detail"])


# --- AC04 / AC05: deactivate and reactivate ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivated_staff_are_refused_everywhere_and_reactivation_restores_login(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Deact Staff")
    await login(client, ctx["master"].email)
    member, email = await _staff_via_api(client, monkeypatch)
    staff_client = await _staff_client(email)
    old_access, old_refresh = staff_client.cookies.get("edusphere_access"), staff_client.cookies.get("edusphere_refresh")
    try:
        response = await client.post(f"{STAFF}/{member['id']}/deactivate")
        assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"
        for path in ("/api/v1/auth/me", "/api/v1/workflows/overseas/agent/students", "/api/v1/portal/overseas/agent/dashboard"):
            assert (await staff_client.get(path)).status_code == 401, path
        assert (await staff_client.post("/api/v1/auth/refresh")).status_code == 401
        assert await _login_status(email) == 401
        assert (await client.post(f"{STAFF}/{member['id']}/deactivate")).json()["detail"] == "Already deactivated"

        reactivated = await client.post(f"{STAFF}/{member['id']}/reactivate")
        assert reactivated.status_code == 200 and reactivated.json()["member"]["status"] == "active"
        again = await _staff_client(email)
        assert (await again.get("/api/v1/auth/me")).status_code == 200
        await again.aclose()
        # E6: cookies from before the deactivation stay dead after reactivation.
        staff_client.cookies.set("edusphere_access", old_access)
        staff_client.cookies.set("edusphere_refresh", old_refresh)
        assert (await staff_client.get("/api/v1/auth/me")).status_code == 401
        assert (await staff_client.post("/api/v1/auth/refresh")).status_code == 401
        assert (await client.post(f"{STAFF}/{member['id']}/reactivate")).json()["detail"] == "Already active"
    finally:
        await staff_client.aclose()


@pytest.mark.asyncio
async def test_deactivation_revokes_an_unused_link_and_reactivation_does_not_revive_it(client, db_session, monkeypatch):  # E3
    sent = _capture(monkeypatch)
    ctx = await mk_active_org(db_session, name="Link Staff")
    await login(client, ctx["master"].email)
    member = (await _create(client)).json()["member"]
    token = next(p["reset_token"] for p in sent if p.get("to") == member["email"])
    await client.post(f"{STAFF}/{member['id']}/deactivate")
    await client.post(f"{STAFF}/{member['id']}/reactivate")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 400
    listed = (await client.get(STAFF)).json()["items"][0]
    assert listed["setup"] == "link_expired"


# --- AC06: reset --------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_kills_the_password_and_sessions_and_sends_a_working_link(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Reset Staff")
    await login(client, ctx["master"].email)
    member, email = await _staff_via_api(client, monkeypatch)
    sent = _capture(monkeypatch)
    staff_client = await _staff_client(email)
    try:
        # The create link is the account's only welcome token, so the first reset is inside `resend_wait_seconds`' free pass.
        response = await client.post(f"{STAFF}/{member['id']}/reset")
        assert response.status_code == 200 and response.json()["member"]["setup"] == "pending_setup" and "development_welcome_token" not in response.json()
        assert (await staff_client.get("/api/v1/auth/me")).status_code == 401
        assert await _login_status(email) == 401
        token = next(p["reset_token"] for p in sent if p.get("to") == email)
        assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Brand-New-Pass-22!"})).status_code == 200
        assert await _login_status(email, "Brand-New-Pass-22!") == 200
        second = await client.post(f"{STAFF}/{member['id']}/reset")
        assert second.status_code == 429 and second.json()["detail"].startswith("A link was just sent; wait ")
        assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "agent_org.staff_reset", AuditLog.entity_id == str(ctx["org"].id))) == 1
    finally:
        await staff_client.aclose()


@pytest.mark.asyncio
async def test_reset_of_deactivated_staff_is_409(client, db_session):
    ctx = await mk_active_org(db_session, name="Reset Deact")
    staff = await mk_staff(db_session, ctx["org"], active=False)
    await login(client, ctx["master"].email)
    response = await client.post(f"{STAFF}/{staff['member'].id}/reset")
    assert response.status_code == 409 and response.json()["detail"] == "Reactivate this staff member first"


# --- AC07 (team routes) / Review Focus 3 ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_agency_and_master_ids_get_404_on_every_staff_route(db_session):
    mine, theirs = await mk_active_org(db_session, name="Mine Staff"), await mk_active_org(db_session, name="Theirs Staff")
    their_staff = await mk_staff(db_session, theirs["org"])
    targets = {"their staff": their_staff["member"].id, "a master": mine["member"].id}
    async with client_for(mine["master"].email) as c:
        assert (await c.get(STAFF)).json()["total"] == 0
        for label, member_id in targets.items():
            for method, path, kwargs in (("patch", "", {"json": {"full_name": "Hacked"}}), ("post", "/deactivate", {}), ("post", "/reactivate", {}), ("post", "/reset", {})):
                response = await getattr(c, method)(f"{STAFF}/{member_id}{path}", **kwargs)
                assert response.status_code == 404 and response.json()["detail"] == "Staff member not found", (label, path)
    untouched = await db_session.get(User, their_staff["user"].id, populate_existing=True)
    assert untouched.full_name == "Staff Member" and untouched.active


# --- AC08: every action audited ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_action_writes_one_audit_row(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Audit All")
    await login(client, ctx["master"].email)
    member, _ = await _staff_via_api(client, monkeypatch)
    await client.patch(f"{STAFF}/{member['id']}", json={"full_name": "Renamed"})
    await client.post(f"{STAFF}/{member['id']}/deactivate")
    await client.post(f"{STAFF}/{member['id']}/reactivate")
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(ctx["org"].id), AuditLog.action.like("agent_org.staff_%")))).all()
    assert sorted(r.action for r in rows) == ["agent_org.staff_create", "agent_org.staff_deactivate", "agent_org.staff_reactivate", "agent_org.staff_update"]
    assert all(r.entity_type == "agent_org" and r.metadata_json["member_id"] == member["id"] and "@" not in str(r.metadata_json) for r in rows)
