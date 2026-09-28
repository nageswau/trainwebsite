import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, PasswordResetToken, User
from app.services import provisioning
from tests.agn001_helpers import PASSWORD, client_for, login, membership, mk_active_org, mk_user, org_of, uniq

TEAM = "/api/v1/workflows/overseas/agent/team"
INVITE = TEAM + "/masters"
DEACTIVATE = TEAM + "/masters/{mid}/deactivate"


async def _invite(client, **overrides):
    return await client.post(INVITE, json={"full_name": "Invited Master", "email": f"{uniq('m')}@example.local", **overrides})


@pytest.mark.asyncio
async def test_invite_creates_m002_with_a_welcome_link_and_an_audit_row(client, db_session):  # AC08
    ctx = await mk_active_org(db_session, name="Team Agency")
    await login(client, ctx["master"].email)
    response = await _invite(client)
    assert response.status_code == 201
    body = response.json()
    assert body["member"]["code"] == f"{ctx['org'].prefix}-M002" and body["member"]["invite_pending"] is True and body["member"]["status"] == "active"
    assert body["email_status"] in {"sent", "not_configured", "failed"}
    invited = await db_session.scalar(select(User).where(User.email == body["member"]["email"]))
    assert invited.role == "agent" and invited.division == "overseas" and invited.active is True
    assert await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == invited.id, PasswordResetToken.purpose == "welcome")) is not None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.master_invite", AuditLog.entity_id == str(ctx["org"].id)))
    assert log.entity_type == "agent_org" and log.user_id == ctx["master"].id
    team = (await client.get(TEAM)).json()
    assert [m["code"] for m in team["masters"]] == [f"{ctx['org'].prefix}-M001", f"{ctx['org'].prefix}-M002"] and team["limit"] == 3


@pytest.mark.asyncio
async def test_the_invited_master_sets_a_password_and_sees_the_org(client, db_session, monkeypatch):  # AC08 end to end
    sent = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    ctx = await mk_active_org(db_session, name="Invite Flow")
    await login(client, ctx["master"].email)
    body = (await _invite(client)).json()
    # Final review #5: the inviting Master never receives the raw link token, even in dev/test.
    assert "development_welcome_token" not in body
    token = next(p["reset_token"] for p in sent if p.get("to") == body["member"]["email"])
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "An0ther-Secret-Pass!"})).status_code == 200
    login_response = await client.post("/api/v1/auth/login", json={"email": body["member"]["email"], "password": "An0ther-Secret-Pass!", "division": "overseas"})
    assert login_response.status_code == 200
    assert (await client.get(TEAM)).json()["org"]["id"] == str(ctx["org"].id)


@pytest.mark.asyncio
async def test_a_fourth_active_master_is_422(client, db_session):  # AC07
    ctx = await mk_active_org(db_session, name="Limit Agency")
    await login(client, ctx["master"].email)
    assert (await _invite(client)).status_code == 201
    assert (await _invite(client)).status_code == 201
    response = await _invite(client)
    assert response.status_code == 422 and response.json()["detail"] == "This agency already has 3 active Masters"


@pytest.mark.asyncio
async def test_an_existing_email_is_409(client, db_session):
    ctx = await mk_active_org(db_session, name="Dup Agency")
    other = await mk_user(db_session, role="overseas_student")
    await login(client, ctx["master"].email)
    response = await _invite(client, email=other.email)
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    assert (await org_of(db_session, ctx["master"].id)).master_seq == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"full_name": "", "email": "x@example.local"}, {"full_name": "A", "email": "not-an-email"}, {"full_name": "A" * 161, "email": "y@example.local"}])
async def test_invalid_invites_are_422(client, db_session, payload):
    ctx = await mk_active_org(db_session, name="Bad Invite")
    await login(client, ctx["master"].email)
    assert (await client.post(INVITE, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_deactivation_disables_login_revokes_the_link_and_codes_are_never_reused(client, db_session):  # AC07, E3
    ctx = await mk_active_org(db_session, name="Deact Team")
    await login(client, ctx["master"].email)
    second = (await _invite(client)).json()["member"]
    response = await client.post(DEACTIVATE.format(mid=second["id"]))
    assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"
    user = await db_session.scalar(select(User).where(User.email == second["email"]).execution_options(populate_existing=True))
    assert user.active is False
    token = await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert token.superseded_at is not None
    assert (await client.post(DEACTIVATE.format(mid=second["id"]))).json()["detail"] == "Already deactivated"
    third = (await _invite(client)).json()["member"]
    assert third["code"] == f"{ctx['org'].prefix}-M003"
    assert (await _invite(client)).json()["member"]["code"] == f"{ctx['org'].prefix}-M004"
    assert (await client.post(f"{TEAM}/masters/{second['id']}/reactivate")).status_code == 404  # no reactivation path (D8)


@pytest.mark.asyncio
async def test_the_last_active_master_cannot_be_deactivated(client, db_session):  # AC07
    ctx = await mk_active_org(db_session, name="Last Master")
    await login(client, ctx["master"].email)
    response = await client.post(DEACTIVATE.format(mid=ctx["member"].id))
    assert response.status_code == 422 and response.json()["detail"] == "An agency must keep at least one active Master"


async def _accept_invite(db, email):
    """The invitee sets their password: their welcome token is used."""
    user = await db.scalar(select(User).where(User.email == email))
    token = await db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "welcome"))
    token.used_at = datetime.now(UTC)
    await db.commit()


@pytest.mark.asyncio
async def test_a_master_may_deactivate_themselves_once_another_master_has_accepted(client, db_session):
    ctx = await mk_active_org(db_session, name="Self Deact")
    await login(client, ctx["master"].email)
    second = (await _invite(client)).json()["member"]
    await _accept_invite(db_session, second["email"])
    assert (await client.post(DEACTIVATE.format(mid=ctx["member"].id))).status_code == 200
    assert (await client.get(TEAM)).status_code == 401  # login disabled: next request is refused


@pytest.mark.asyncio
async def test_no_self_lockout_while_every_other_master_is_still_invite_pending(client, db_session):  # review #6
    ctx = await mk_active_org(db_session, name="No Lockout")
    await login(client, ctx["master"].email)
    await _invite(client)  # M002 has not accepted yet
    response = await client.post(DEACTIVATE.format(mid=ctx["member"].id))
    assert response.status_code == 422 and response.json()["detail"] == "At least one other Master must have accepted their invite first"
    assert (await membership(db_session, ctx["master"].id)).status == "active"


@pytest.mark.asyncio
async def test_a_pending_invitee_can_still_be_deactivated_by_an_accepted_master(client, db_session):  # review #6
    ctx = await mk_active_org(db_session, name="Cancel Invite")
    await login(client, ctx["master"].email)
    second = (await _invite(client)).json()["member"]
    assert (await client.post(DEACTIVATE.format(mid=second["id"]))).status_code == 200


@pytest.mark.asyncio
async def test_other_orgs_members_are_404_and_non_agents_are_403(client, db_session):  # AC06/AC08 team routes
    a = await mk_active_org(db_session, name="Team A")
    b = await mk_active_org(db_session, name="Team B")
    await login(client, a["master"].email)
    assert (await client.post(DEACTIVATE.format(mid=b["member"].id))).status_code == 404
    assert (await client.post(DEACTIVATE.format(mid=uuid.uuid4()))).status_code == 404
    assert b["master"].email not in (await client.get(TEAM)).text
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await client.get(TEAM)).status_code == 403
    assert (await _invite(client)).status_code == 403


@pytest.mark.asyncio
async def test_a_suspended_org_cannot_use_the_team_routes(client, db_session):
    ctx = await mk_active_org(db_session, name="Susp Team")
    ctx["org"].status = "suspended"
    await db_session.commit()
    await login(client, ctx["master"].email)
    assert (await client.get(TEAM)).status_code == 403
    assert (await _invite(client)).status_code == 403


@pytest.mark.asyncio
async def test_two_invites_racing_for_the_last_place_admit_one(db_session):  # race: invite
    ctx = await mk_active_org(db_session, name="Race Invite")
    async with client_for(ctx["master"].email) as c:
        assert (await _invite(c)).status_code == 201
        results = await asyncio.gather(_invite(c), _invite(c))
    assert sorted(r.status_code for r in results) == [201, 422]


@pytest.mark.asyncio
async def test_two_masters_deactivating_each_other_leave_one_active(db_session):  # race: deactivate
    ctx = await mk_active_org(db_session, name="Race Deact")
    async with client_for(ctx["master"].email) as c1:
        second = (await _invite(c1)).json()["member"]
        user = await db_session.scalar(select(User).where(User.email == second["email"]))
        user.password_hash = hash_password(PASSWORD)  # skip the email step: M002 can sign in
        await db_session.commit()
        async with client_for(user.email) as c2:
            results = await asyncio.gather(c1.post(DEACTIVATE.format(mid=second["id"])), c2.post(DEACTIVATE.format(mid=ctx["member"].id)))
    # The org lock serialises the two: the loser sees either the 422 (last Master) or, if the winner deactivated the
    # loser itself first, a 401 (its login is already disabled). Either way exactly one Master stays active.
    assert sorted(r.status_code for r in results) in ([200, 401], [200, 422])
    states = [(await membership(db_session, uid)).status for uid in (ctx["master"].id, user.id)]
    assert states.count("active") == 1


@pytest.mark.asyncio
async def test_two_agencies_inviting_one_email_at_once_is_201_and_409_not_500(db_session):  # Review Focus 4
    # Different organisations hold different locks, so both pass the "email exists?" check; the users.email unique
    # constraint settles it inside flush_unique_email. (Self-registration's own race handling is pre-existing and out
    # of AGN-001's scope.)
    a = await mk_active_org(db_session, name="Email Race A")
    b = await mk_active_org(db_session, name="Email Race B")
    email = f"{uniq('race')}@example.local"
    async with client_for(a["master"].email) as ca, client_for(b["master"].email) as cb:
        results = await asyncio.gather(ca.post(INVITE, json={"full_name": "Racer", "email": email}), cb.post(INVITE, json={"full_name": "Racer", "email": email}))
    assert sorted(r.status_code for r in results) == [201, 409]
    seqs = sorted([(await org_of(db_session, a["master"].id)).master_seq, (await org_of(db_session, b["master"].id)).master_seq])
    assert seqs == [1, 2]  # the loser's master_seq was not advanced


async def _past_invites(db, org_id, actor_id, count, hours_ago):
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    for _ in range(count):
        db.add(AuditLog(user_id=actor_id, action="agent_org.master_invite", entity_type="agent_org", entity_id=str(org_id), outcome="invited", metadata_json={}, created_at=when))
    await db.commit()


@pytest.mark.asyncio
async def test_invites_are_throttled_to_10_per_agency_per_24_hours(client, db_session):  # security review: invite flood
    ctx = await mk_active_org(db_session, name="Throttle Agency")
    await _past_invites(db_session, ctx["org"].id, ctx["master"].id, 10, hours_ago=2)
    await login(client, ctx["master"].email)
    response = await _invite(client)
    assert response.status_code == 429
    assert response.json()["detail"] == "This agency has sent 10 invites in the last 24 hours. Try again later."
    retry_after = int(response.headers["Retry-After"])
    assert 21 * 3600 < retry_after <= 22 * 3600  # the oldest of the 10 leaves the window in ~22 hours
    assert (await org_of(db_session, ctx["master"].id)).master_seq == 1  # nothing created


@pytest.mark.asyncio
async def test_invites_older_than_24_hours_do_not_count(client, db_session):
    ctx = await mk_active_org(db_session, name="Old Invites")
    await _past_invites(db_session, ctx["org"].id, ctx["master"].id, 10, hours_ago=25)
    await _past_invites(db_session, ctx["org"].id, ctx["master"].id, 9, hours_ago=1)
    await login(client, ctx["master"].email)
    assert (await _invite(client)).status_code == 201


@pytest.mark.asyncio
async def test_another_agencys_invites_do_not_count(client, db_session):
    busy = await mk_active_org(db_session, name="Busy Agency")
    quiet = await mk_active_org(db_session, name="Quiet Agency")
    await _past_invites(db_session, busy["org"].id, busy["master"].id, 10, hours_ago=1)
    await login(client, quiet["master"].email)
    assert (await _invite(client)).status_code == 201


@pytest.mark.asyncio
async def test_the_team_portal_section_lists_only_own_masters(client, db_session):  # AC06 portal team
    a = await mk_active_org(db_session, name="Portal Team A")
    b = await mk_active_org(db_session, name="Portal Team B")
    await login(client, a["master"].email)
    response = await client.get("/api/v1/portal/overseas/agent/team")
    assert response.status_code == 200
    assert [row["code"] for row in response.json()["rows"]] == [a["member"].code]
    assert b["master"].email not in response.text


@pytest.mark.asyncio
async def test_the_dashboard_shows_the_callers_code(client, db_session):
    ctx = await mk_active_org(db_session, name="Dash Code")
    await login(client, ctx["master"].email)
    metrics = (await client.get("/api/v1/portal/overseas/agent/dashboard")).json()["metrics"]
    assert {"label": "Your code", "value": ctx["member"].code} in metrics
