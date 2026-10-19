"""csc-002 (DEC-SCOPE-227) -- an overseas counselor creates a walk-in student's login (POST /counselor/students); the student gets the
ENH-003 set-password email; the student belongs to the counselor (csc-001 link). GET /counselor/students lists the counselor's own."""

import asyncio

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, OverseasStudentCounselor, PasswordResetToken, User, UserRoleAssignment
from app.services import counselor_students, provisioning
from tests.agn001_helpers import client_for, login, mk_user, uniq

URL = "/api/v1/counselor/students"
NEW_PASSWORD = "Walk-in-Secret-Pass-1!"


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


async def _create(client, **overrides):
    return await client.post(URL, json={"full_name": "Vikram Walk-in", "email": f"{uniq('w')}@example.local", **overrides})


# --- create ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_counselor_creates_a_linked_overseas_student_and_the_link_is_emailed(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    email = f"{uniq('w')}@Example.local"
    response = await _create(client, email=email, phone="+91 98765 43210")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email_status"] in {"sent", "not_configured", "failed"} and body["expires_at"]
    assert "development_welcome_token" not in body  # a counselor never sees the link token, in any environment
    student = await db_session.scalar(select(User).where(User.email == email.lower()))
    assert body["student"] == {
        "id": str(student.id), "full_name": "Vikram Walk-in", "email": email.lower(), "phone": "+91 98765 43210",
        "student_code": student.student_code, "setup": "pending_setup",
    }  # fmt: skip
    assert (student.role, student.division, student.active, student.email_verified) == ("overseas_student", "overseas", True, False)
    assert student.student_code and student.profile == {"registration_source": "counselor_walk_in"}
    link = await db_session.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id))
    assert (link.counselor_user_id, link.assigned_by_user_id) == (counselor.id, counselor.id)
    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == student.id))
    assert (assignment.role, assignment.division, assignment.approval_status, assignment.assigned_by_user_id) == ("overseas_student", "overseas", "approved", counselor.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_create", AuditLog.entity_id == str(student.id)))
    assert audit.user_id == counselor.id and email.lower() not in str(audit.metadata_json)

    token = next(p["reset_token"] for p in sent if p.get("to") == student.email)
    await client.post("/api/v1/auth/logout")
    reset = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert reset.status_code == 200 and reset.json()["login_portal"] is None
    signed_in = await client.post("/api/v1/auth/login", json={"email": student.email, "password": NEW_PASSWORD, "division": "overseas"})
    assert signed_in.status_code == 200, signed_in.text


@pytest.mark.asyncio
async def test_the_welcome_email_goes_to_the_student_with_the_overseas_link_and_the_counselor_as_inviter(client, db_session, monkeypatch):
    calls: list[dict] = []

    async def fake_smtp(**kwargs):
        calls.append(kwargs)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_welcome_email", fake_smtp)
    counselor = await mk_user(db_session, role="counselor", full_name="Ritika Counselor")
    await login(client, counselor.email)
    response = await _create(client)
    assert response.json()["email_status"] == "sent"
    (call,) = calls
    assert call["to_email"] == response.json()["student"]["email"] and call["role"] == "overseas_student"
    assert "/overseas/reset-password?token=" in call["set_password_url"] and call["invited_by_name"] == "Ritika Counselor"


@pytest.mark.asyncio
async def test_a_failed_send_keeps_the_account_and_says_so(client, db_session, monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(provisioning, "send_welcome_email", fail)
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    response = await _create(client)
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    assert await db_session.scalar(select(User.id).where(User.email == response.json()["student"]["email"]))


@pytest.mark.asyncio
async def test_a_counselor_created_student_is_in_the_counselors_picker(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    name = f"{uniq('pick')} Walk-in"
    student_id = (await _create(client, full_name=name)).json()["student"]["id"]
    picked = await client.get("/api/v1/lookups/overseas-students", params={"q": name})
    assert [item["id"] for item in picked.json()["items"]] == [student_id]


# --- refusals -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_existing_email_is_409_case_insensitively_and_audited_without_the_address(client, db_session):
    existing = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    response = await _create(client, email=existing.email.upper())
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    rejected = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_create_rejected", AuditLog.user_id == counselor.id))
    assert rejected.outcome == "rejected" and existing.email not in str(rejected.metadata_json)


@pytest.mark.asyncio
async def test_two_concurrent_creates_for_one_email_make_one_account(db_session):
    counselor = await mk_user(db_session, role="counselor")
    email = f"{uniq('race')}@example.local"
    async with client_for(counselor.email) as a, client_for(counselor.email) as b:
        responses = await asyncio.gather(_create(a, email=email), _create(b, email=email))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [{"role": "overseas_admin"}, {"division": "it"}, {"password": "Secret-Pass-123"}, {"active": False}, {"email_verified": True}, {"profile": {"x": 1}}],
)
async def test_server_set_fields_cannot_be_supplied(client, db_session, extra):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    response = await _create(client, **extra)
    assert response.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(OverseasStudentCounselor).where(OverseasStudentCounselor.counselor_user_id == counselor.id)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [{"full_name": "   "}, {"full_name": "x" * 161}, {"email": "not-an-email"}, {"email": "a@b"}, {"email": f"{'a' * 250}@example.local"}, {"phone": "9" * 41}],
)
async def test_invalid_input_is_422(client, db_session, body):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await _create(client, **body)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_student", "overseas"), ("overseas_admin", "overseas"), ("agent", "overseas"), ("telecaller", "overseas"), ("counselor", "it")])
async def test_other_roles_and_the_it_counselor_are_403(client, db_session, role, division):
    actor = await mk_user(db_session, role=role, division=division)
    await login(client, actor.email, division=division)
    assert (await _create(client)).status_code == 403
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await _create(client)).status_code == 401
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_creations_are_throttled_per_counselor_and_rejections_count(client, db_session, monkeypatch):
    monkeypatch.setattr(counselor_students, "MAIL_LIMIT", 2)
    existing = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await _create(client)).status_code == 201
    assert (await _create(client, email=existing.email)).status_code == 409
    throttled = await _create(client)
    assert throttled.status_code == 429 and int(throttled.headers["Retry-After"]) > 0
    await login(client, other.email)
    assert (await _create(client)).status_code == 201  # the budget is per counselor


# --- list -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_list_is_the_counselors_own_linked_students_newest_first_with_setup_status(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    await login(client, other.email)
    await _create(client, full_name="Not Mine")
    await login(client, counselor.email)
    first = (await _create(client, full_name="First Walk-in")).json()["student"]
    second = (await _create(client, full_name="Second Walk-in")).json()["student"]
    # The first student sets a password: their row reads active (setup null).
    token = await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == first["id"]))
    token.used_at = func.now()
    await db_session.commit()
    response = await client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (2, 20, 0)
    assert [(s["full_name"], s["setup"]) for s in body["items"]] == [("Second Walk-in", "pending_setup"), ("First Walk-in", None)]
    assert body["items"][0] == second | {"setup": "pending_setup"}


@pytest.mark.asyncio
async def test_the_list_pages(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    for i in range(3):
        await _create(client, full_name=f"Paged {i}")
    page = (await client.get(URL, params={"limit": 2, "offset": 2})).json()
    assert (page["total"], [s["full_name"] for s in page["items"]]) == (3, ["Paged 0"])
    assert (await client.get(URL, params={"limit": 51})).status_code == 422
