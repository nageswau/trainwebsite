"""ENH-006 / DEC-SCOPE-021 -- self-service change password (authenticated).
Spec: docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md

Every test creates its own user: never change a seeded account's password (other suites log in with it).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models import AuditLog, User

PASSWORD = "Sup3r-Secret-Pass!"
NEW_PASSWORD = "Brand-New-Pass-1!"
URL = "/api/v1/auth/change-password"
FAILED = "auth.change_password_failed"
CHANGED = "auth.change_password"


async def _make_user(db_session, *, role="it_student", division="it", active=True) -> User:
    user = User(email=f"enh006-{uuid.uuid4().hex[:10]}@example.local", password_hash=hash_password(PASSWORD), full_name="ENH-006 User", role=role, division=division, active=active, email_verified=True)
    db_session.add(user)
    await db_session.commit()
    return user


async def _sign_in(client, user, password=PASSWORD):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password, "division": user.division})
    assert response.status_code == 200, response.text


async def _signed_in_user(client, db_session, **kwargs) -> User:
    user = await _make_user(db_session, **kwargs)
    await _sign_in(client, user)
    return user


async def _rows(db_session, user, action) -> list[AuditLog]:
    return list((await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == action))).all())


async def _password_is(db_session, user, password) -> bool:
    await db_session.refresh(user)
    return verify_password(password, user.password_hash)


@pytest.mark.asyncio
async def test_change_password_succeeds_and_only_the_new_password_logs_in(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "set-cookie" not in response.headers  # no token or cookie is reissued
    assert await _password_is(db_session, user, NEW_PASSWORD)
    login = {"email": user.email, "division": user.division}
    assert (await client.post("/api/v1/auth/login", json={**login, "password": NEW_PASSWORD})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={**login, "password": PASSWORD})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("it_student", "it"), ("overseas_admin", "overseas"), ("school_coordinator", "overseas"), ("super_admin", "global")])
async def test_every_role_changes_its_own_password_and_gets_one_audit_row(client, db_session, role, division):
    user = await _signed_in_user(client, db_session, role=role, division=division)
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert await _password_is(db_session, user, NEW_PASSWORD)
    assert len(await _rows(db_session, user, CHANGED)) == 1
    assert await _rows(db_session, user, FAILED) == []


@pytest.mark.asyncio
async def test_a_change_never_touches_another_account(client, db_session):
    other = await _make_user(db_session)
    await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    assert await _password_is(db_session, other, PASSWORD)


@pytest.mark.asyncio
async def test_a_wrong_current_password_is_400_changes_nothing_and_is_audited_as_denied(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": "not-the-password", "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect current password"}
    assert await _password_is(db_session, user, PASSWORD)
    rows = await _rows(db_session, user, FAILED)
    assert len(rows) == 1
    assert rows[0].outcome == "denied"
    assert rows[0].metadata_json == {"reason": "incorrect_current_password"}
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_no_session_is_401_even_when_the_body_is_also_invalid(client):
    assert (await client.post(URL, json={"current_password": "", "new_password": "x"})).status_code == 401
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401


@pytest.mark.asyncio
async def test_a_deactivated_account_session_is_401(client, db_session):
    user = await _signed_in_user(client, db_session)
    user.active = False
    await db_session.commit()
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"current_password": PASSWORD, "new_password": "short-9ch"},
        {"current_password": PASSWORD, "new_password": "x" * 129},
        {"current_password": "", "new_password": NEW_PASSWORD},
        {"current_password": PASSWORD},
        {"new_password": NEW_PASSWORD},
    ],
    ids=["new-too-short", "new-too-long", "current-empty", "new-missing", "current-missing"],
)
async def test_a_malformed_body_is_422_changes_nothing_and_uses_no_attempt(client, db_session, payload):
    user = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json=payload)).status_code == 422
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_a_new_password_equal_to_the_current_one_is_422_and_no_oracle(client, db_session):
    user = await _signed_in_user(client, db_session)
    for current in (PASSWORD, "not-the-password"):  # correct or wrong: the same answer, so it reveals nothing
        response = await client.post(URL, json={"current_password": current, "new_password": current})
        assert response.status_code == 422
        assert response.json() == {"detail": "New password must be different from the current password"}
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []
