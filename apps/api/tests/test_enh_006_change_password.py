"""ENH-006 / DEC-SCOPE-021 -- self-service change password (authenticated).
Spec: docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md

Every test creates its own user: never change a seeded account's password (other suites log in with it).
"""

import uuid
from datetime import UTC, datetime, timedelta

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


async def _seed_failures(db_session, user, ages_minutes):
    """Insert denied change-password audit rows, each back-dated by the given number of minutes."""
    now = datetime.now(UTC)
    for age in ages_minutes:
        db_session.add(
            AuditLog(user_id=user.id, action=FAILED, entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"reason": "incorrect_current_password"}, created_at=now - timedelta(minutes=age))
        )
    await db_session.commit()


WRONG = {"current_password": "not-the-password", "new_password": NEW_PASSWORD}


@pytest.mark.asyncio
async def test_five_wrong_attempts_are_400_and_the_sixth_is_429_with_retry_after(client, db_session):
    user = await _signed_in_user(client, db_session)
    for _ in range(5):
        assert (await client.post(URL, json=WRONG)).status_code == 400
    blocked = await client.post(URL, json=WRONG)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900
    assert "try again in" in blocked.json()["detail"]
    assert len(await _rows(db_session, user, FAILED)) == 5  # the blocked attempt added no row


@pytest.mark.asyncio
async def test_a_correct_password_is_still_refused_while_blocked(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 1, 1, 1, 1])
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 429
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_retry_after_is_when_the_fifth_newest_failure_leaves_the_window(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [14, 13, 12, 11, 10])  # the oldest, 14 min ago, leaves the window in ~60 s
    blocked = await client.post(URL, json=WRONG)
    assert blocked.status_code == 429
    assert 55 <= int(blocked.headers["Retry-After"]) <= 61


@pytest.mark.asyncio
async def test_failures_older_than_the_window_do_not_count(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [16, 17, 18, 19, 20])
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert await _password_is(db_session, user, NEW_PASSWORD)


@pytest.mark.asyncio
async def test_four_recent_failures_do_not_block_and_the_fifth_wrong_attempt_arms_the_block(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 2, 3, 4, 20])  # the 20-minute-old row is outside the window
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json=WRONG)).status_code == 429


@pytest.mark.asyncio
async def test_the_limit_is_per_user(client, db_session):
    blocked_user = await _make_user(db_session)
    await _seed_failures(db_session, blocked_user, [1, 1, 1, 1, 1])
    other = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    assert await _password_is(db_session, other, NEW_PASSWORD)
    assert len(await _rows(db_session, blocked_user, FAILED)) == 5
