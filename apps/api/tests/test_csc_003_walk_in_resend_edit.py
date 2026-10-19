"""csc-003 (DEC-SCOPE-228, W6) -- on a pending walk-in account (never activated) linked to them, an overseas counselor resends the
set-password link (POST /counselor/students/{id}/welcome-links) or fixes name/phone/email (PATCH /counselor/students/{id}). An email
change revokes the old link and mails a new one to the new address. Mail-sending actions share the csc-002 budget."""

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, User
from app.services import counselor_students, provisioning
from tests.agn001_helpers import login, mk_user, uniq

URL = "/api/v1/counselor/students"
NEW_PASSWORD = "Walk-in-Secret-Pass-1!"


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


def _token(sent: list[dict], email: str) -> str:
    return [p["reset_token"] for p in sent if p.get("to") == email][-1]


async def _walk_in(client, counselor, **overrides) -> dict:
    await login(client, counselor.email)
    response = await client.post(URL, json={"full_name": "Pending Walk-in", "email": f"{uniq('p')}@example.local", **overrides})
    assert response.status_code == 201, response.text
    return response.json()["student"]


async def _set_password(client, token: str) -> int:
    return (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code


async def _activate(client, sent, student, counselor) -> None:
    await client.post("/api/v1/auth/logout")
    assert await _set_password(client, _token(sent, student["email"])) == 200
    await login(client, counselor.email)


# --- resend ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_mails_a_new_link_and_the_old_one_stops_working(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    old = _token(sent, student["email"])
    response = await client.post(f"{URL}/{student['id']}/welcome-links")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["student"]["setup"] == "pending_setup" and body["email_status"] and body["expires_at"]
    assert "development_welcome_token" not in body
    new = _token(sent, student["email"])
    assert new != old
    await client.post("/api/v1/auth/logout")
    assert await _set_password(client, old) == 400
    assert await _set_password(client, new) == 200
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_resend", AuditLog.entity_id == student["id"]))
    assert audit.user_id == counselor.id


@pytest.mark.asyncio
async def test_a_second_resend_within_the_cooldown_is_429(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    assert (await client.post(f"{URL}/{student['id']}/welcome-links")).status_code == 201
    second = await client.post(f"{URL}/{student['id']}/welcome-links")
    assert second.status_code == 429 and int(second.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_resend_on_an_active_account_is_409(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    await _activate(client, sent, student, counselor)
    response = await client.post(f"{URL}/{student['id']}/welcome-links")
    assert response.status_code == 409 and response.json()["detail"] == "This student has already set a password"


@pytest.mark.asyncio
async def test_resend_and_edit_on_a_deactivated_account_are_409(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    row = await db_session.get(User, student["id"])
    row.active = False
    await db_session.commit()
    for response in (await client.post(f"{URL}/{student['id']}/welcome-links"), await client.patch(f"{URL}/{student['id']}", json={"full_name": "X"})):
        assert response.status_code == 409 and response.json()["detail"] == "This account is deactivated"


@pytest.mark.asyncio
async def test_another_counselors_or_an_unknown_or_a_non_student_is_404(client, db_session):
    owner = await mk_user(db_session, role="counselor")
    theirs = await _walk_in(client, owner)
    me = await mk_user(db_session, role="counselor")
    unlinked = await mk_user(db_session, role="overseas_student")
    await login(client, me.email)
    for target in (theirs["id"], str(unlinked.id), str(me.id), "00000000-0000-0000-0000-000000000000"):
        assert (await client.post(f"{URL}/{target}/welcome-links")).status_code == 404
        response = await client.patch(f"{URL}/{target}", json={"full_name": "Hijack"})
        assert response.status_code == 404 and response.json()["detail"] == "Student not found"
    assert (await db_session.get(User, theirs["id"], populate_existing=True)).full_name == "Pending Walk-in"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("overseas_student", "overseas"), ("agent", "overseas"), ("counselor", "it")])
async def test_other_roles_and_the_it_counselor_are_403(client, db_session, role, division):
    owner = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, owner)
    actor = await mk_user(db_session, role=role, division=division)
    await login(client, actor.email, division=division)
    assert (await client.post(f"{URL}/{student['id']}/welcome-links")).status_code == 403
    assert (await client.patch(f"{URL}/{student['id']}", json={"full_name": "X"})).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    target = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"{URL}/{target}/welcome-links")).status_code == 401
    assert (await client.patch(f"{URL}/{target}", json={"full_name": "X"})).status_code == 401


# --- edit -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_name_and_phone_edits_send_no_mail_and_audit_field_names_only(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor, phone="+91 90000 00001")
    before = len(sent)
    response = await client.patch(f"{URL}/{student['id']}", json={"full_name": "  Corrected Name ", "phone": ""})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"student": student | {"full_name": "Corrected Name", "phone": None}}
    assert len(sent) == before
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_update", AuditLog.entity_id == student["id"]))
    assert sorted(audit.metadata_json["fields"]) == ["full_name", "phone"] and "Corrected" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_an_email_change_revokes_the_old_link_and_mails_a_new_one_to_the_new_address(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor, email=f"{uniq('typo')}@exmaple.local")
    old = _token(sent, student["email"])
    new_email = f"{uniq('fixed')}@Example.local"
    response = await client.patch(f"{URL}/{student['id']}", json={"email": new_email})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"]["email"] == new_email.lower() and body["student"]["setup"] == "pending_setup" and body["email_status"]
    assert "development_welcome_token" not in body
    new = _token(sent, new_email.lower())
    row = await db_session.get(User, student["id"], populate_existing=True)
    assert row.email == new_email.lower() and row.email_verified is False
    await client.post("/api/v1/auth/logout")
    assert await _set_password(client, old) == 400
    assert await _set_password(client, new) == 200
    signed_in = await client.post("/api/v1/auth/login", json={"email": new_email.lower(), "password": NEW_PASSWORD, "division": "overseas"})
    assert signed_in.status_code == 200
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_update", AuditLog.entity_id == student["id"]))
    assert audit.metadata_json["fields"] == ["email"] and new_email.lower() not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_a_case_only_email_change_is_not_a_change(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    before = len(sent)
    response = await client.patch(f"{URL}/{student['id']}", json={"email": student["email"].upper()})
    assert response.status_code == 200 and "email_status" not in response.json() and len(sent) == before


@pytest.mark.asyncio
async def test_an_email_that_belongs_to_another_account_is_409_and_audited_without_it(client, db_session):
    existing = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    response = await client.patch(f"{URL}/{student['id']}", json={"email": existing.email.upper(), "full_name": "Should Not Save"})
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    row = await db_session.get(User, student["id"], populate_existing=True)
    assert row.email == student["email"] and row.full_name == "Pending Walk-in"
    rejected = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor.student_update_rejected", AuditLog.user_id == counselor.id))
    assert rejected.outcome == "rejected" and existing.email not in str(rejected.metadata_json)


@pytest.mark.asyncio
async def test_edit_on_an_active_account_is_409(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    await _activate(client, sent, student, counselor)
    response = await client.patch(f"{URL}/{student['id']}", json={"email": f"{uniq('late')}@example.local"})
    assert response.status_code == 409 and response.json()["detail"] == "This student has already set a password"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [{"role": "overseas_admin"}, {"active": False}, {"full_name": "   "}, {"full_name": None}, {"email": "a@b"}, {"email": None}, {"phone": "9" * 41}],
)
async def test_invalid_edits_are_422(client, db_session, body):
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    assert (await client.patch(f"{URL}/{student['id']}", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_an_empty_edit_is_a_no_op(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)
    response = await client.patch(f"{URL}/{student['id']}", json={})
    assert response.status_code == 200 and response.json() == {"student": student}


# --- the shared mail budget ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resends_and_email_changes_count_toward_the_budget_but_name_edits_do_not(client, db_session, monkeypatch):
    monkeypatch.setattr(counselor_students, "MAIL_LIMIT", 3)
    counselor = await mk_user(db_session, role="counselor")
    student = await _walk_in(client, counselor)  # 1
    for i in range(3):
        assert (await client.patch(f"{URL}/{student['id']}", json={"full_name": f"Name {i}"})).status_code == 200  # not counted
    assert (await client.post(f"{URL}/{student['id']}/welcome-links")).status_code == 201  # 2
    assert (await client.patch(f"{URL}/{student['id']}", json={"email": f"{uniq('b')}@example.local"})).status_code == 200  # 3
    throttled = await client.post(URL, json={"full_name": "Fourth", "email": f"{uniq('f')}@example.local"})
    assert throttled.status_code == 429
    assert (await client.patch(f"{URL}/{student['id']}", json={"email": f"{uniq('c')}@example.local"})).status_code == 429
    assert (await client.patch(f"{URL}/{student['id']}", json={"phone": "123"})).status_code == 200
    created = await db_session.scalar(select(func.count()).select_from(User).where(User.full_name == "Fourth"))
    assert created == 0
