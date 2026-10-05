"""ENH-006 / DEC-SCOPE-021 -- self-service change password (authenticated).
Spec: docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md

Every test creates its own user: never change a seeded account's password (other suites log in with it).
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import create_token, hash_password, verify_password
from app.main import app
from app.models import AuditLog, PasswordResetToken, User

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


@pytest.mark.asyncio
async def test_two_simultaneous_wrong_guesses_at_attempt_five_yield_one_400_and_one_429(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 1, 1, 1])
    results = await asyncio.gather(client.post(URL, json=WRONG), client.post(URL, json=WRONG))
    assert sorted(r.status_code for r in results) == [400, 429]
    assert len(await _rows(db_session, user, FAILED)) == 5


@pytest.mark.asyncio
async def test_two_simultaneous_changes_with_the_same_current_password_yield_one_200_and_one_400(client, db_session):
    user = await _signed_in_user(client, db_session)
    first = {"current_password": PASSWORD, "new_password": "First-New-Pass-1!"}
    second = {"current_password": PASSWORD, "new_password": "Second-New-Pass-1!"}
    results = await asyncio.gather(client.post(URL, json=first), client.post(URL, json=second))
    assert sorted(r.status_code for r in results) == [200, 400]
    winner = first["new_password"] if results[0].status_code == 200 else second["new_password"]
    assert await _password_is(db_session, user, winner)
    assert len(await _rows(db_session, user, CHANGED)) == 1


@pytest.mark.asyncio
async def test_a_change_racing_a_reset_password_completes_without_error_or_deadlock(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    db_session.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(minutes=30)))
    await db_session.commit()
    results = await asyncio.wait_for(
        asyncio.gather(
            client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
            client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Reset-New-Pass-1!"}),
        ),
        timeout=30,
    )
    statuses = [r.status_code for r in results]
    assert 500 not in statuses  # a deadlock surfaces as a 500 (Postgres aborts one transaction)
    assert 200 in statuses


@pytest.mark.asyncio
async def test_no_password_or_hash_reaches_the_logs_or_audit_rows(client, db_session, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")
    changed = await _signed_in_user(client, db_session)
    old_hash = changed.password_hash
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(changed)
    blocked = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, blocked, [1, 1, 1, 1, 1])
    assert (await client.post(URL, json=WRONG)).status_code == 429

    messages = {r.getMessage() for r in caplog.records}
    assert {"password_changed", "change_password_throttled"} <= messages  # the records exist, so the scan below is not vacuous
    haystack = "\n".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in caplog.records)
    for user in (changed, blocked):
        haystack += json.dumps([row.metadata_json for row in await _rows(db_session, user, FAILED) + await _rows(db_session, user, CHANGED)])
    for secret in (PASSWORD, NEW_PASSWORD, WRONG["current_password"], old_hash, changed.password_hash):
        assert secret not in haystack


async def _seed_reset_token(db_session, user, *, purpose="reset", used=False):
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(UTC)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        purpose=purpose,
        expires_at=now + timedelta(minutes=30),
        used_at=now if used else None,
    )
    db_session.add(token)
    await db_session.commit()
    return raw, token


@pytest.mark.asyncio
async def test_a_change_revokes_unused_reset_links_so_an_emailed_link_cannot_overwrite_it(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw, token = await _seed_reset_token(db_session, user)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(token)
    assert token.superseded_at is not None
    replay = await client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Attacker-Chosen-1!"})
    assert replay.status_code == 400
    assert replay.json() == {"detail": "Reset token is invalid or expired"}
    assert await _password_is(db_session, user, NEW_PASSWORD)


@pytest.mark.asyncio
async def test_a_change_leaves_used_links_welcome_links_and_other_users_links_alone(client, db_session):
    user = await _signed_in_user(client, db_session)
    other = await _make_user(db_session)
    _, used = await _seed_reset_token(db_session, user, used=True)
    _, welcome = await _seed_reset_token(db_session, user, purpose="welcome")
    _, others = await _seed_reset_token(db_session, other)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    for token in (used, welcome, others):
        await db_session.refresh(token)
        assert token.superseded_at is None


@pytest.mark.asyncio
async def test_a_refused_change_revokes_nothing(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw, token = await _seed_reset_token(db_session, user)
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": PASSWORD})).status_code == 422
    await db_session.refresh(token)
    assert token.superseded_at is None


@pytest.mark.asyncio
async def test_extra_fields_cannot_change_role_division_email_or_anything_but_the_password(client, db_session):
    user = await _signed_in_user(client, db_session)
    original = (user.role, user.division, user.email, user.active, user.full_name)
    response = await client.post(
        URL,
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "role": "super_admin",
            "division": "global",
            "email": "attacker@example.local",
            "active": False,
            "full_name": "Hacked",
            "password_hash": "x",
            "id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 200
    await db_session.refresh(user)
    assert (user.role, user.division, user.email, user.active, user.full_name) == original
    assert verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_a_refresh_token_is_not_accepted_as_a_session_here(db_session):
    user = await _make_user(db_session)
    token = create_token(str(user.id), user.role, user.division, "refresh")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={"edusphere_access": token}) as anonymous:
        assert (await anonymous.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401
    assert await _password_is(db_session, user, PASSWORD)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [12345678901, ["a"], {"a": 1}, True, None], ids=["int", "list", "object", "bool", "null"])
async def test_non_string_passwords_are_422_and_never_coerced(client, db_session, bad):
    user = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": bad, "new_password": NEW_PASSWORD})).status_code == 422
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": bad})).status_code == 422
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile",
    ["'; DROP TABLE users; --", "pw\u0000tail-of-the-password", "<script>alert(1)</script>", "\U0001f511" * 30],
    ids=["sql", "nul-byte", "markup", "astral"],
)
async def test_hostile_strings_are_just_wrong_passwords_and_are_never_echoed(client, db_session, hostile):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": hostile, "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect current password"}
    rows = await _rows(db_session, user, FAILED)
    assert len(rows) == 1
    assert hostile not in json.dumps(rows[0].metadata_json)
    assert await _password_is(db_session, user, PASSWORD)


@pytest.mark.asyncio
async def test_a_password_with_odd_characters_round_trips_as_a_new_password(client, db_session):
    user = await _signed_in_user(client, db_session)
    odd = "pässwörd-\u0000-'\"<>-\U0001f511-end"
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": odd})).status_code == 200
    login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": odd, "division": user.division})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_the_endpoint_does_not_accept_a_non_json_body(client, db_session):
    # A cross-site "simple request" (text/plain or a form) must not be able to carry the JSON. SameSite=Lax cookies and the
    # current-password requirement are the primary CSRF defences; this is the third. If this fails, the image's FastAPI
    # parses non-JSON content types as JSON: report it to the user -- do not change app-wide body parsing here.
    user = await _signed_in_user(client, db_session)
    body = json.dumps({"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        response = await client.post(URL, content=body, headers={"Content-Type": content_type})
        assert response.status_code == 422
    assert await _password_is(db_session, user, PASSWORD)


# QA-007 (browser QA): a 10-space password satisfied the length rule and worked for login. Whitespace alone is not a password.
@pytest.mark.asyncio
@pytest.mark.parametrize("blank", [" " * 10, "\t" * 10, " \t\n " * 3, "\u00a0" * 10], ids=["spaces", "tabs", "mixed-whitespace", "non-breaking-spaces"])
async def test_a_new_password_of_only_whitespace_is_422_with_a_clear_message(client, db_session, blank):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": blank})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Password must not consist only of spaces"
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []  # a refused rule uses no attempt
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_spaces_inside_or_around_a_real_password_are_kept_exactly(client, db_session):
    user = await _signed_in_user(client, db_session)
    spaced = "  spaced out pass  "  # not stripped, not normalised
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": spaced})).status_code == 200
    login = {"email": user.email, "division": user.division}
    assert (await client.post("/api/v1/auth/login", json={**login, "password": spaced})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={**login, "password": spaced.strip()})).status_code == 401
