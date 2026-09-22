"""ENH-003 / DEC-SCOPE-019 -- first-time provisioning: emailed, single-use, 72-hour set-password
link for admin-provisioned accounts. Spec: docs/superpowers/specs/2026-09-19-enh-003-first-time-provisioning-design.md
"""

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import AuditLog, PasswordResetToken, School, User

PASSWORD = "Sup3r-Secret-Pass!"
NEW_PASSWORD = "Brand-New-Pass-1!"


def _email(prefix: str = "enh003") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.local"


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _make_user(db_session, *, role="overseas_admin", division="overseas", active=True, email_verified=True, password=PASSWORD) -> User:
    user = User(email=_email(), password_hash=hash_password(password), full_name="ENH-003 User", role=role, division=division, active=active, email_verified=email_verified)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, password: str = PASSWORD, division: str = "overseas"):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password, "division": division})


async def _seed_token(db_session, user, *, purpose="welcome", expires_in=timedelta(hours=72), used=False, superseded=False, created_at=None):
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(UTC)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_sha(raw),
        purpose=purpose,
        expires_at=now + expires_in,
        used_at=now if used else None,
        superseded_at=now if superseded else None,
    )
    if created_at is not None:
        token.created_at = created_at
    db_session.add(token)
    await db_session.commit()
    return raw, token


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Alembic's env.py calls `logging.config.fileConfig`, which by default DISABLES every logger that
    already exists. Any earlier test that runs a migration in-process (ENH-001's downgrade/upgrade
    cycle) therefore silences `app.*` loggers for the rest of the pytest session -- so `caplog` sees
    nothing and the logging tests below fail depending on test order. Production is unaffected
    (Alembic runs in its own process before the server starts); this only keeps the tests order-proof."""
    import logging

    for name in ("app.provisioning", "app.auth", "app.admin"):
        logging.getLogger(name).disabled = False
    yield


# --- Task 1: schema -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_reset_tokens_have_purpose_and_superseded_columns(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync_conn: {c["name"]: c for c in sa.inspect(sync_conn).get_columns("password_reset_tokens")})
    assert "purpose" in columns and "superseded_at" in columns
    assert columns["purpose"]["nullable"] is False
    assert columns["superseded_at"]["nullable"] is True


@pytest.mark.asyncio
async def test_a_token_created_without_a_purpose_defaults_to_reset(db_session):
    user = await _make_user(db_session)
    token = PasswordResetToken(user_id=user.id, token_hash=_sha(uuid.uuid4().hex), expires_at=datetime.now(UTC) + timedelta(minutes=30))
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    assert token.purpose == "reset"
    assert token.superseded_at is None


# --- Task 2: welcome email ------------------------------------------------------------

from app.services import mailer  # noqa: E402

LINK = "https://example.local/overseas/reset-password?token=abc123"


def _configure_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@edusphere.local")
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)


def _welcome_kwargs(**overrides):
    base = dict(
        to_email="new.staff@example.local", recipient_name="Asha", role="academic_team", set_password_url=LINK, expires_at=datetime.now(UTC) + timedelta(hours=72), invited_by_name="Overseas Admin"
    )
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_welcome_email_reports_not_configured_without_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert await mailer.send_welcome_email(**_welcome_kwargs()) == ("not_configured", None)


@pytest.mark.asyncio
async def test_welcome_email_carries_the_link_and_expiry_and_no_password(monkeypatch):
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    status, error = await mailer.send_welcome_email(**_welcome_kwargs())
    assert (status, error) == ("sent", None)
    msg = sent[0]
    assert msg["To"] == "new.staff@example.local"
    assert "no-reply@edusphere.local" in msg["From"]
    text = msg.get_body(preferencelist=("plain",)).get_content()
    html_body = msg.get_body(preferencelist=("html",)).get_content()
    assert LINK in text and LINK in html_body
    assert "72 hours" in text
    assert "ChangeMe" not in text and "ChangeMe" not in html_body


@pytest.mark.asyncio
async def test_welcome_email_escapes_names_in_html(monkeypatch):
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    await mailer.send_welcome_email(**_welcome_kwargs(recipient_name="<b>Eve</b>", invited_by_name="<i>Admin</i>"))
    html_body = sent[0].get_body(preferencelist=("html",)).get_content()
    assert "<b>Eve</b>" not in html_body and "&lt;b&gt;Eve&lt;/b&gt;" in html_body
    assert "<i>Admin</i>" not in html_body


@pytest.mark.asyncio
async def test_welcome_email_reports_a_send_failure(monkeypatch):
    _configure_smtp(monkeypatch)

    def boom(msg):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(mailer, "_send_sync", boom)
    status, error = await mailer.send_welcome_email(**_welcome_kwargs())
    assert status == "failed" and "smtp down" in error


@pytest.mark.asyncio
async def test_welcome_email_never_raises_on_a_malformed_address(monkeypatch):
    _configure_smtp(monkeypatch)
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: None)
    status, error = await mailer.send_welcome_email(**_welcome_kwargs(to_email="victim@example.local\r\nBcc: attacker@example.local"))
    assert status == "failed" and error


# --- Task 3: provisioning service -----------------------------------------------------

from app.services import provisioning  # noqa: E402


@pytest.mark.asyncio
async def test_unusable_password_hash_is_random_and_matches_nothing_guessable():
    first, second = provisioning.unusable_password_hash(), provisioning.unusable_password_hash()
    assert first != second
    assert not verify_password("ChangeMe@12345", first)


@pytest.mark.asyncio
async def test_issue_welcome_token_stores_only_the_hash_for_72_hours_and_audits_without_the_raw_token(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor", email_verified=False)
    issued = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()

    row = await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.id == issued.token_id))
    assert row.purpose == "welcome" and row.token_hash == _sha(issued.raw) and issued.raw not in row.token_hash
    assert timedelta(hours=71, minutes=59) < row.expires_at - datetime.now(UTC) <= timedelta(hours=72)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_issue"))
    assert audit is not None and issued.raw not in json.dumps(audit.metadata_json)


@pytest.mark.asyncio
async def test_a_second_issue_supersedes_the_first_and_only_one_stays_open(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    first = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    second = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    rows = {r.id: r for r in (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == target.id))).all()}
    assert rows[first.token_id].superseded_at is not None
    assert rows[second.token_id].superseded_at is None


@pytest.mark.asyncio
async def test_statuses_pending_expired_resent_revoked_and_resolved(db_session):
    pending = await _make_user(db_session, role="counselor")
    expired = await _make_user(db_session, role="counselor")
    resent = await _make_user(db_session, role="counselor")
    revoked = await _make_user(db_session, role="counselor")
    consumed = await _make_user(db_session, role="counselor")
    resolved = await _make_user(db_session, role="counselor")
    plain = await _make_user(db_session, role="counselor")

    await _seed_token(db_session, pending)
    await _seed_token(db_session, expired, expires_in=timedelta(hours=-1))
    # a Re-send: the old token is superseded (and long expired), the newest one is open -> pending
    await _seed_token(db_session, resent, expires_in=timedelta(hours=-5), superseded=True, created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resent)
    # revoked (e.g. account deactivated): the only token is superseded and nothing newer exists
    await _seed_token(db_session, revoked, superseded=True)
    await _seed_token(db_session, consumed, used=True)
    # link expired, but the user later set a password through forgot-password
    await _seed_token(db_session, resolved, expires_in=timedelta(hours=-1), created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resolved, purpose="reset", used=True)

    ids = [u.id for u in (pending, expired, resent, revoked, consumed, resolved, plain)]
    result = await provisioning.provisioning_statuses(db_session, ids)
    assert result[pending.id] == "pending_setup"
    assert result[expired.id] == "link_expired"
    assert result[resent.id] == "pending_setup"
    assert result[revoked.id] == "link_expired"
    assert consumed.id not in result and resolved.id not in result and plain.id not in result
    assert await provisioning.provisioning_statuses(db_session, []) == {}


@pytest.mark.asyncio
async def test_revoke_supersedes_only_open_welcome_tokens_and_leaves_the_account_re_sendable(db_session):
    user = await _make_user(db_session, role="counselor")
    _, open_token = await _seed_token(db_session, user)
    _, used_token = await _seed_token(db_session, user, used=True, created_at=datetime.now(UTC) - timedelta(days=5))
    _, reset_token = await _seed_token(db_session, user, purpose="reset", expires_in=timedelta(minutes=30))
    await provisioning.revoke_welcome_tokens(db_session, user.id)
    await db_session.commit()
    for token in (open_token, used_token, reset_token):
        await db_session.refresh(token)
    assert open_token.superseded_at is not None
    assert used_token.superseded_at is None and reset_token.superseded_at is None


@pytest.mark.asyncio
async def test_user_ids_with_status_is_division_scoped_and_skips_inactive_users(db_session):
    overseas_admin = await _make_user(db_session)
    it_admin = await _make_user(db_session, role="it_admin", division="it")
    super_admin = await _make_user(db_session, role="super_admin", division="global")
    overseas_expired = await _make_user(db_session, role="counselor", division="overseas")
    it_expired = await _make_user(db_session, role="trainer", division="it")
    inactive_expired = await _make_user(db_session, role="counselor", division="overseas", active=False)
    for u in (overseas_expired, it_expired, inactive_expired):
        await _seed_token(db_session, u, expires_in=timedelta(hours=-1))

    overseas_ids = set(await provisioning.user_ids_with_status(db_session, overseas_admin, "link_expired"))
    it_ids = set(await provisioning.user_ids_with_status(db_session, it_admin, "link_expired"))
    all_ids = set(await provisioning.user_ids_with_status(db_session, super_admin, "link_expired"))
    assert overseas_expired.id in overseas_ids and it_expired.id not in overseas_ids
    assert it_expired.id in it_ids and overseas_expired.id not in it_ids
    assert inactive_expired.id not in overseas_ids and inactive_expired.id not in all_ids
    assert {overseas_expired.id, it_expired.id} <= all_ids


@pytest.mark.asyncio
async def test_resend_cooldown_only_applies_after_a_first_re_send_and_lapses(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    assert await provisioning.resend_wait_seconds(db_session, target.id) == 0  # first Re-send is always allowed

    await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    wait = await provisioning.resend_wait_seconds(db_session, target.id)
    assert 0 < wait <= provisioning.RESEND_COOLDOWN_SECONDS

    for token in (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == target.id))).all():
        token.created_at = datetime.now(UTC) - timedelta(minutes=2)
    await db_session.commit()
    assert await provisioning.resend_wait_seconds(db_session, target.id) == 0


async def _delivery_setup(db_session, monkeypatch, *, smtp, webhook):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    issued = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()

    async def fake_smtp(**kwargs):
        return smtp() if callable(smtp) else smtp

    async def fake_webhook(channel, payload):
        return webhook

    monkeypatch.setattr(provisioning, "send_welcome_email", fake_smtp)
    monkeypatch.setattr(provisioning, "send_notification", fake_webhook)
    return admin, target, issued


@pytest.mark.asyncio
async def test_deliver_reports_status_and_only_returns_the_dev_token_in_dev_or_test(db_session, monkeypatch):
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("sent", None), webhook=("not_configured", None))

    monkeypatch.setattr(settings, "environment", "test")
    dev = await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    assert dev["email_status"] == "sent" and dev["development_welcome_token"] == issued.raw and dev["expires_at"] == issued.expires_at

    monkeypatch.setattr(settings, "environment", "production")
    prod = await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    assert "development_welcome_token" not in prod

    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))).all()
    assert len(audit) == 2 and all(issued.raw not in json.dumps(a.metadata_json) for a in audit)
    assert audit[0].metadata_json["smtp_status"] == "sent"


@pytest.mark.asyncio
async def test_deliver_redacts_urls_from_the_errors_it_stores(db_session, monkeypatch):
    leaky = "Client error '404 Not Found' for url 'https://hooks.example.local/secret-path?key=abc123'"
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "connect to https://smtp.example.local:587 failed"), webhook=("failed", leaky))
    await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    stored = json.dumps(audit.metadata_json)
    assert "hooks.example.local" not in stored and "abc123" not in stored and "smtp.example.local" not in stored
    assert "[redacted-url]" in stored


@pytest.mark.asyncio
async def test_deliver_treats_a_raising_sender_as_a_failed_send_not_an_exception(db_session, monkeypatch):
    def boom():
        raise ValueError("Header values may not contain linefeed or carriage return characters")

    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=boom, webhook=("not_configured", None))
    result = await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    assert result["email_status"] == "failed"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    assert audit.metadata_json["smtp_status"] == "failed" and "linefeed" in audit.metadata_json["smtp_error"]


@pytest.mark.asyncio
async def test_deliver_never_raises_when_the_audit_write_fails(db_session, monkeypatch):
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "boom"), webhook=("not_configured", None))

    async def broken_commit():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "commit", broken_commit)
    result = await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    assert result["email_status"] == "failed"


def _provisioning_log_blob(caplog) -> tuple[list, str]:
    import logging

    records = [r for r in caplog.records if r.name == "app.provisioning" and r.levelno >= logging.INFO]
    blob = " ".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in records)
    return records, blob


@pytest.mark.asyncio
async def test_a_delivered_link_is_logged_at_info_without_secrets(db_session, monkeypatch, caplog):
    import logging

    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("sent", None), webhook=("not_configured", None))
    with caplog.at_level(logging.INFO, logger="app.provisioning"):
        await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    records, blob = _provisioning_log_blob(caplog)
    record = next(r for r in records if r.getMessage() == "welcome_link_delivered")
    assert record.levelno == logging.INFO
    assert record.extra_fields["user_id"] == str(target.id) and record.extra_fields["issued_by"] == str(admin.id)
    assert record.extra_fields["smtp_status"] == "sent"
    assert issued.raw not in blob and target.email not in blob


@pytest.mark.asyncio
async def test_an_undelivered_link_is_logged_at_warning_and_redacts_addresses_and_urls(db_session, monkeypatch, caplog):
    import logging

    error = "550 <victim@example.local> rejected via https://smtp.example.local:587"
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", error), webhook=("not_configured", None))
    with caplog.at_level(logging.INFO, logger="app.provisioning"):
        await provisioning.deliver_welcome_link(user=target, issued=issued, issued_by=admin)
    records, blob = _provisioning_log_blob(caplog)
    record = next(r for r in records if r.getMessage() == "welcome_link_not_delivered")
    assert record.levelno == logging.WARNING
    assert record.extra_fields["smtp_status"] == "failed" and record.extra_fields["token_id"] == str(issued.token_id)
    assert "victim@example.local" not in blob and "smtp.example.local" not in blob and issued.raw not in blob and target.email not in blob
    stored = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    assert "victim@example.local" not in json.dumps(stored.metadata_json)


# --- Task 4: reset_password -----------------------------------------------------------

RESET_URL = "/api/v1/auth/reset-password"
INVALID = "Reset token is invalid or expired"


async def _pending_user(db_session, *, active=True, **token_kwargs):
    user = await _make_user(db_session, role="counselor", email_verified=False, active=active, password=uuid.uuid4().hex + "Zz1!")
    raw, token = await _seed_token(db_session, user, **token_kwargs)
    return user, raw, token


@pytest.mark.asyncio
async def test_a_welcome_link_sets_the_password_verifies_the_email_and_allows_login(client, db_session):
    user, raw, token = await _pending_user(db_session)
    response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 200 and response.json() == {"ok": True}
    await db_session.refresh(user)
    await db_session.refresh(token)
    assert user.email_verified is True and token.used_at is not None
    assert (await _login(client, user.email, NEW_PASSWORD)).status_code == 200
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "auth.welcome_password_set")) is not None


@pytest.mark.asyncio
async def test_a_used_link_is_rejected_with_the_generic_400(client, db_session):
    user, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200
    second = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert second.status_code == 400 and second.json()["detail"] == INVALID


@pytest.mark.asyncio
async def test_two_simultaneous_submissions_yield_exactly_one_success(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    results = await asyncio.gather(
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD}),
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD}),
    )
    assert sorted(r.status_code for r in results) == [200, 400]


@pytest.mark.asyncio
async def test_expired_superseded_and_unknown_links_all_return_the_same_400(client, db_session):
    _, expired, _ = await _pending_user(db_session, expires_in=timedelta(hours=-1))
    _, superseded, _ = await _pending_user(db_session, superseded=True)
    for raw in (expired, superseded, "not-a-real-token"):
        response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert response.status_code == 400 and response.json()["detail"] == INVALID


@pytest.mark.asyncio
async def test_a_too_short_password_is_422_and_does_not_burn_the_link(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "short"})).status_code == 422
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_password_length_is_capped_at_128_and_an_oversized_one_does_not_burn_the_link(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "x" * 129})).status_code == 422
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "A1" + "x" * 126})).status_code == 200  # exactly 128


@pytest.mark.asyncio
async def test_a_welcome_link_is_refused_for_a_deactivated_account_and_is_not_consumed(client, db_session):
    user, raw, token = await _pending_user(db_session, active=False)
    response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json()["detail"] == INVALID
    await db_session.refresh(token)
    await db_session.refresh(user)
    assert token.used_at is None  # the failed attempt rolled back; the link was not burned
    assert not verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_a_forgot_password_token_keeps_its_behavior_and_does_not_verify_the_email(client, db_session):
    user, raw, _ = await _pending_user(db_session, purpose="reset", expires_in=timedelta(minutes=30))
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(user)
    assert user.email_verified is False
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "auth.password_reset")) is not None


@pytest.mark.asyncio
async def test_setting_a_password_from_a_welcome_link_is_logged_without_secrets(client, db_session, caplog):
    import logging

    user, raw, _ = await _pending_user(db_session)
    with caplog.at_level(logging.INFO, logger="app.auth"):
        assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200
    records = [r for r in caplog.records if r.name == "app.auth"]
    record = next(r for r in records if r.getMessage() == "welcome_password_set")
    assert record.extra_fields["user_id"] == str(user.id)
    blob = " ".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in records)
    assert raw not in blob and NEW_PASSWORD not in blob and user.email not in blob


@pytest.mark.asyncio
async def test_a_refused_welcome_link_for_an_inactive_account_is_logged_as_a_warning(client, db_session, caplog):
    import logging

    user, raw, _ = await _pending_user(db_session, active=False)
    with caplog.at_level(logging.INFO, logger="app.auth"):
        assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 400
    record = next(r for r in caplog.records if r.name == "app.auth" and r.getMessage() == "welcome_link_refused_inactive_account")
    assert record.levelno == logging.WARNING and record.extra_fields["user_id"] == str(user.id)
    assert raw not in json.dumps(record.extra_fields, default=str)


# --- Task 5: create routes ------------------------------------------------------------


async def _admin_client(client, db_session, *, role="overseas_admin", division="overseas"):
    admin = await _make_user(db_session, role=role, division=division)
    assert (await _login(client, admin.email, division="it" if division in ("it", "global") else division)).status_code == 200
    return admin


def _no_password_keys(body: dict) -> bool:
    return not any("password" in key.lower() for key in body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body,field",
    [
        ("/api/v1/admin/users", {"role": "counselor", "division": "overseas", "full_name": "X"}, "password"),
        ("/api/v1/overseas-admin/school-staff", {"role": "academic_team", "full_name": "X"}, "password"),
        ("/api/v1/overseas-admin/schools", {"name": "S", "coordinator_full_name": "X"}, "coordinator_password"),
    ],
)
async def test_a_supplied_password_is_rejected_with_422_and_creates_nothing(client, db_session, path, body, field):
    await _admin_client(client, db_session)
    email = _email()
    payload = {**body, ("coordinator_email" if field == "coordinator_password" else "email"): email, field: "Should-Be-Ignored-1!"}
    response = await client.post(path, json=payload)
    assert response.status_code == 422
    # ENH-009: /overseas-admin/schools now validates via a typed, extra="forbid" Pydantic
    # schema, so a supplied `coordinator_password` is rejected by Pydantic itself (a list-
    # shaped `detail`) rather than by this route's own string-message check -- the other two
    # paths are still untyped `dict` bodies and keep the original flat-string 422. Both are a
    # real 422 naming the rejected field; accept either response shape.
    detail = response.json()["detail"]
    detail_text = detail.lower() if isinstance(detail, str) else json.dumps(detail).lower()
    assert "password" in detail_text
    assert await db_session.scalar(select(User).where(User.email == email)) is None


@pytest.mark.asyncio
async def test_create_user_issues_a_welcome_link_and_never_a_password(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "smtp_host", None)
    admin = await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New Counselor"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and "ChangeMe" not in response.text
    assert body["email_status"] == "not_configured" and body["email"] == email
    assert timedelta(hours=71, minutes=59) < datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC) <= timedelta(hours=72)

    user = await db_session.scalar(select(User).where(User.email == email))
    assert not verify_password("ChangeMe@12345", user.password_hash)
    assert (await _login(client, email, "ChangeMe@12345")).status_code == 401
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).all()
    assert len(tokens) == 1 and tokens[0].purpose == "welcome"
    assert tokens[0].token_hash == _sha(body["development_welcome_token"])

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(user.id)))).all()
    assert {"user.create", "user.welcome_link_issue", "user.welcome_link_delivery"} <= {a.action for a in audits}
    assert all(body["development_welcome_token"] not in json.dumps(a.metadata_json) for a in audits)
    assert any(a.user_id == admin.id for a in audits)


@pytest.mark.asyncio
async def test_the_created_user_can_activate_from_the_link_and_log_in(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New Counselor"})).json()
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
    user = await db_session.scalar(select(User).where(User.email == email))
    await db_session.refresh(user)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_the_dev_token_is_never_returned_in_production(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    await _admin_client(client, db_session)
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": _email(), "full_name": "P"})).json()
    assert "development_welcome_token" not in body and "email_status" in body


@pytest.mark.asyncio
async def test_school_staff_route_provisions_with_a_welcome_link(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "academic_team", "full_name": "Staff", "email": email, "school_ids": []})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and body["role"] == "academic_team" and body["school_ids"] == []
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_create_school_seeds_a_coordinator_with_a_welcome_link(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/overseas-admin/schools", json={"name": f"S {uuid.uuid4().hex[:6]}", "coordinator_full_name": "Coord", "coordinator_email": email})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and body["coordinator_email"] == email
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
    assert (await client.get("/api/v1/school/team")).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_send_never_blocks_creation_and_is_audited(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")

    async def failing_smtp(**kwargs):
        return "failed", "smtp down"

    monkeypatch.setattr(provisioning, "send_welcome_email", failing_smtp)
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "F"})
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    user = await db_session.scalar(select(User).where(User.email == email))
    delivery = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "user.welcome_link_delivery"))
    assert delivery.metadata_json["smtp_status"] == "failed" and delivery.metadata_json["smtp_error"] == "smtp down"
    assert await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)) is not None


@pytest.mark.asyncio
async def test_the_composed_email_goes_to_the_new_user_with_the_link_and_no_password(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    await _admin_client(client, db_session)
    email = _email()
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New"})).json()
    assert body["email_status"] == "sent" and len(sent) == 1 and sent[0]["To"] == email
    text = sent[0].get_body(preferencelist=("plain",)).get_content()
    assert f"/overseas/reset-password?token={body['development_welcome_token']}" in text
    assert "72 hours" in text and "ChangeMe" not in text


@pytest.mark.asyncio
async def test_a_duplicate_email_is_409_including_under_a_race(client, db_session):
    await _admin_client(client, db_session)
    email = _email()
    payload = {"role": "counselor", "division": "overseas", "email": email, "full_name": "Dup"}
    results = await asyncio.gather(client.post("/api/v1/admin/users", json=payload), client.post("/api/v1/admin/users", json=payload))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert (await client.post("/api/v1/admin/users", json=payload)).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/admin/users", "/api/v1/overseas-admin/school-staff", "/api/v1/overseas-admin/schools"])
@pytest.mark.parametrize("bad_email", ["not-an-email", "a b@example.local", "a@b", "victim@example.local\r\nBcc: attacker@example.local", "x" * 250 + "@example.local", ""])
async def test_a_malformed_email_is_422_and_creates_nothing(client, db_session, path, bad_email):
    await _admin_client(client, db_session)
    payloads = {
        "/api/v1/admin/users": {"role": "counselor", "division": "overseas", "full_name": "X", "email": bad_email},
        "/api/v1/overseas-admin/school-staff": {"role": "academic_team", "full_name": "X", "email": bad_email, "school_ids": []},
        "/api/v1/overseas-admin/schools": {"name": "S", "coordinator_full_name": "X", "coordinator_email": bad_email},
    }
    before = await db_session.scalar(sa.select(sa.func.count()).select_from(User))
    response = await client.post(path, json=payloads[path])
    assert response.status_code == 422, response.text
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(User)) == before


# QA-001: a value longer than its column (users.full_name 160, schools.name 200, schools.city/state 120)
# used to reach Postgres and come back as an unhandled 500; it is now a 422 that names the field.
def _create_payload(path: str, **override) -> dict:
    base = {
        "/api/v1/admin/users": {"role": "counselor", "division": "overseas", "full_name": "Ok Name", "email": _email()},
        "/api/v1/overseas-admin/school-staff": {"role": "academic_team", "full_name": "Ok Name", "email": _email(), "school_ids": []},
        "/api/v1/overseas-admin/schools": {"name": "Ok School", "coordinator_full_name": "Ok Name", "coordinator_email": _email()},
    }[path]
    return {**base, **override}


LENGTH_CASES = [
    ("/api/v1/admin/users", "full_name", 160),
    ("/api/v1/overseas-admin/school-staff", "full_name", 160),
    ("/api/v1/overseas-admin/schools", "coordinator_full_name", 160),
    ("/api/v1/overseas-admin/schools", "name", 200),
    ("/api/v1/overseas-admin/schools", "city", 120),
    ("/api/v1/overseas-admin/schools", "state", 120),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path,field,limit", LENGTH_CASES)
async def test_a_value_longer_than_its_column_is_422_naming_the_field_and_creates_nothing(client, db_session, path, field, limit):
    await _admin_client(client, db_session)
    users_before = await db_session.scalar(sa.select(sa.func.count()).select_from(User))
    schools_before = await db_session.scalar(sa.select(sa.func.count()).select_from(School))
    response = await client.post(path, json=_create_payload(path, **{field: "N" * (limit + 1)}))
    assert response.status_code == 422, response.text
    # ENH-009: /overseas-admin/schools' name/city/state/coordinator_full_name are now enforced
    # by SchoolCreate's Field(max_length=...) rather than this route's own _fit() helper, so the
    # 422 is Pydantic's list-shaped `detail` there; the other paths keep the original flat string.
    detail = response.json()["detail"]
    detail_text = detail if isinstance(detail, str) else json.dumps(detail)
    assert str(limit) in detail_text
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(User)) == users_before
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(School)) == schools_before


@pytest.mark.asyncio
@pytest.mark.parametrize("path,field,limit", LENGTH_CASES)
async def test_a_value_exactly_at_its_column_limit_is_accepted(client, db_session, monkeypatch, path, field, limit):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    response = await client.post(path, json=_create_payload(path, **{field: "N" * limit}))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_a_sender_that_raises_never_turns_a_committed_creation_into_a_500(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")

    async def exploding_smtp(**kwargs):
        raise ValueError("bad header")

    monkeypatch.setattr(provisioning, "send_welcome_email", exploding_smtp)
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "Boom"})
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    assert await db_session.scalar(select(User).where(User.email == email)) is not None


def test_no_default_password_constant_remains_in_the_api_source():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py") if "ChangeMe@12345" in p.read_text(encoding="utf-8")]
    assert offenders == []


@pytest.mark.asyncio
async def test_a_rejected_password_field_is_logged_as_a_warning_naming_the_actor(client, db_session, caplog):
    import logging

    admin = await _admin_client(client, db_session)
    with caplog.at_level(logging.INFO, logger="app.admin"):
        response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": _email(), "full_name": "X", "password": "Nope-Nope-1!"})
    assert response.status_code == 422
    record = next(r for r in caplog.records if r.name == "app.admin" and r.getMessage() == "provisioning_password_field_rejected")
    assert record.levelno == logging.WARNING
    assert record.extra_fields["actor_id"] == str(admin.id) and record.extra_fields["route"] == "/api/v1/admin/users"
    assert "Nope-Nope-1!" not in json.dumps(record.extra_fields, default=str)


# --- Task 6: Re-send, status, filter, dashboard, revoke -------------------------------


async def _provision_via_api(client, monkeypatch, *, role="counselor", division="overseas"):
    monkeypatch.setattr(settings, "environment", "test")
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": role, "division": division, "email": email, "full_name": "Pending"})
    assert response.status_code == 201, response.text
    return response.json()


async def _age_welcome_tokens(db_session, user_id, minutes=2):
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(str(user_id)), PasswordResetToken.purpose == "welcome"))).all()
    for token in tokens:
        token.created_at = datetime.now(UTC) - timedelta(minutes=minutes)
    await db_session.commit()


@pytest.mark.asyncio
async def test_resend_supersedes_the_old_link_and_issues_a_new_72_hour_one(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    old = created["development_welcome_token"]
    response = await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == created["id"] and body["email_status"] in {"sent", "failed", "not_configured"}
    assert timedelta(hours=71, minutes=59) < datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC) <= timedelta(hours=72)

    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400
    open_tokens = (
        await db_session.scalars(
            select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(created["id"]), PasswordResetToken.purpose == "welcome", PasswordResetToken.superseded_at.is_(None))
        )
    ).all()
    assert len(open_tokens) == 1
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_a_second_resend_inside_the_cooldown_is_429_with_retry_after_and_lapses(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    url = f"/api/v1/admin/users/{created['id']}/welcome-links"
    assert (await client.post(url)).status_code == 201  # the first Re-send after creation is allowed

    blocked = await client.post(url)
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 60 and "wait" in blocked.json()["detail"].lower()
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(created["id"]), PasswordResetToken.purpose == "welcome"))).all()
    assert len(tokens) == 2  # the blocked call issued nothing

    await _age_welcome_tokens(db_session, created["id"])
    assert (await client.post(url)).status_code == 201


@pytest.mark.asyncio
async def test_resend_guards_404_403_409_and_non_admin(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    assert (await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/welcome-links")).status_code == 404

    # already active -> 409
    activated = await _make_user(db_session, role="counselor", division="overseas")
    assert (await client.post(f"/api/v1/admin/users/{activated.id}/welcome-links")).status_code == 409
    # deactivated but never set up -> 409
    inactive = await _make_user(db_session, role="counselor", division="overseas", active=False)
    await _seed_token(db_session, inactive)
    assert (await client.post(f"/api/v1/admin/users/{inactive.id}/welcome-links")).status_code == 409

    # another division -> 403
    it_admin = await _make_user(db_session, role="it_admin", division="it")
    assert (await _login(client, it_admin.email, division="it")).status_code == 200
    assert (await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")).status_code == 403

    # non-admin -> refused
    trainer = await _make_user(db_session, role="trainer", division="it")
    assert (await _login(client, trainer.email, division="it")).status_code == 200
    assert (await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")).status_code == 403


@pytest.mark.asyncio
async def test_users_list_carries_provisioning_status_and_keeps_its_existing_fields(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    rows = (await client.get("/api/v1/admin/users")).json()
    row = next(r for r in rows if r["id"] == created["id"])
    assert row["provisioning_status"] == "pending_setup"
    assert {"id", "name", "email", "division", "role", "active", "phone", "profile"} <= set(row)
    assert any(r["provisioning_status"] == "active" for r in rows)


@pytest.mark.asyncio
async def test_the_filter_returns_exactly_the_expired_users_in_scope(client, db_session):
    overseas_admin = await _make_user(db_session)
    assert (await _login(client, overseas_admin.email)).status_code == 200
    expired = await _make_user(db_session, role="counselor", division="overseas")
    pending = await _make_user(db_session, role="counselor", division="overseas")
    resent = await _make_user(db_session, role="counselor", division="overseas")
    revoked = await _make_user(db_session, role="counselor", division="overseas")
    inactive = await _make_user(db_session, role="counselor", division="overseas", active=False)
    it_user = await _make_user(db_session, role="trainer", division="it")
    await _seed_token(db_session, expired, expires_in=timedelta(hours=-1))
    await _seed_token(db_session, pending)
    await _seed_token(db_session, resent, expires_in=timedelta(hours=-5), superseded=True, created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resent)  # the Re-send's new open link wins
    await _seed_token(db_session, revoked, superseded=True)  # revoked, nothing newer -> needs a Re-send
    await _seed_token(db_session, inactive, expires_in=timedelta(hours=-1))
    await _seed_token(db_session, it_user, expires_in=timedelta(hours=-1))

    rows = (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()
    ids = {r["id"] for r in rows}
    assert {str(expired.id), str(revoked.id)} <= ids
    assert not ({str(pending.id), str(resent.id), str(inactive.id), str(it_user.id)} & ids)
    assert all(r["provisioning_status"] == "link_expired" for r in rows)
    pending_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=pending_setup")).json()}
    assert {str(pending.id), str(resent.id)} <= pending_ids and str(expired.id) not in pending_ids
    assert (await client.get("/api/v1/admin/users?provisioning_status=bogus")).status_code == 422

    it_admin = await _make_user(db_session, role="it_admin", division="it")
    assert (await _login(client, it_admin.email, division="it")).status_code == 200
    it_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(it_user.id) in it_ids and str(expired.id) not in it_ids

    super_admin = await _make_user(db_session, role="super_admin", division="global")
    assert (await _login(client, super_admin.email, division="it")).status_code == 200
    all_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert {str(expired.id), str(it_user.id)} <= all_ids


@pytest.mark.asyncio
async def test_a_later_password_set_via_forgot_password_resolves_the_expired_status(client, db_session):
    admin = await _make_user(db_session)
    assert (await _login(client, admin.email)).status_code == 200
    user = await _make_user(db_session, role="counselor", division="overseas")
    await _seed_token(db_session, user, expires_in=timedelta(hours=-1), created_at=datetime.now(UTC) - timedelta(hours=100))
    ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(user.id) in ids
    await _seed_token(db_session, user, purpose="reset", used=True)
    ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(user.id) not in ids


# Codex review, finding 1: the status filter resolves the exact id set, but the route then applied the 500-row cap to
# that set. "Not limited by the 500-row cap" (spec 6.4, API contract) means the FILTERED set is never truncated.
@pytest.mark.asyncio
async def test_a_status_filter_returns_the_whole_set_even_when_it_exceeds_the_list_cap(client, db_session, monkeypatch):
    from app.api import admin as admin_module

    monkeypatch.setattr(admin_module, "USER_LIST_CAP", 2)
    admin = await _make_user(db_session)
    assert (await _login(client, admin.email)).status_code == 200
    emails = []
    for _ in range(3):
        member = await _make_user(db_session, role="counselor", email_verified=False)
        await _seed_token(db_session, member, expires_in=timedelta(hours=-1))
        emails.append(member.email)
    filtered = (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()
    assert set(emails) <= {row["email"] for row in filtered}, "a matching account was hidden by the list cap"
    assert len((await client.get("/api/v1/admin/users")).json()) == 2  # the unfiltered directory keeps its cap


# Codex review, finding 5: `deliver_welcome_link` rolls back when its own audit write fails, and a rollback expires every
# ORM object on the session; the routes then read `item.id` etc. and hit implicit async IO (MissingGreenlet -> 500)
# although the account and token were already committed. "Never raises" must hold for the whole request.
@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["users", "school-staff", "schools", "resend"])
async def test_a_failing_delivery_audit_never_turns_a_committed_provisioning_into_a_500(client, db_session, monkeypatch, route):
    monkeypatch.setattr(settings, "environment", "test")
    from sqlalchemy.ext.asyncio import AsyncSession

    real_commit = AsyncSession.commit

    async def commit(self):
        # Fail only the delivery-audit commit, AFTER its row has been flushed -- as a real commit failure would --
        # so the session holds an open transaction and the service's rollback actually expires every loaded object.
        if any(isinstance(obj, AuditLog) and obj.action == "user.welcome_link_delivery" for obj in self.sync_session.new):
            await self.flush()
            raise RuntimeError("audit store unavailable")
        return await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", commit)
    await _admin_client(client, db_session)
    if route == "resend":
        member, _, _ = await _pending_user(db_session)
        response = await client.post(f"/api/v1/admin/users/{member.id}/welcome-links")
    else:
        body = {
            "users": ("/api/v1/admin/users", {"role": "counselor", "division": "overseas", "full_name": "Audit Down", "email": _email()}),
            "school-staff": ("/api/v1/overseas-admin/school-staff", {"role": "academic_team", "full_name": "Audit Down", "email": _email(), "school_ids": []}),
            "schools": ("/api/v1/overseas-admin/schools", {"name": "Audit Down School", "coordinator_full_name": "Audit Down", "coordinator_email": _email()}),
        }[route]
        response = await client.post(body[0], json=body[1])
    assert response.status_code == 201, response.text
    assert response.json()["email_status"] in {"sent", "failed", "not_configured"}


# Codex review, finding 6: Re-send locks the user row and THEN revokes tokens; reset used to consume the token first and
# update the user afterwards -- the opposite order, so a reset racing a Re-send could deadlock (Postgres aborts one
# transaction -> a 500). Both must take the user row first. Here a Re-send-like transaction holds the user lock while a
# reset request is in flight and then revokes the token; with a consistent order that just supersedes the link.
@pytest.mark.asyncio
async def test_a_reset_racing_a_resend_cannot_deadlock(client, db_session):
    member, raw, _ = await _pending_user(db_session)
    await db_session.execute(select(User).where(User.id == member.id).with_for_update())  # Re-send step 1: lock the user
    reset = asyncio.create_task(client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD}))
    await asyncio.sleep(2)  # let the reset request reach its first lock wait
    revoke_error = None
    try:  # Re-send step 2: revoke the open welcome tokens (what `revoke_welcome_tokens` does)
        await asyncio.wait_for(
            db_session.execute(
                sa.update(PasswordResetToken)
                .where(PasswordResetToken.user_id == member.id, PasswordResetToken.purpose == "welcome", PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None))
                .values(superseded_at=datetime.now(UTC))
            ),
            timeout=10,
        )
        await db_session.commit()
    except Exception as exc:  # a Postgres deadlock abort lands here (or in the reset request below)
        revoke_error = exc
        await db_session.rollback()
    reset_error = None
    try:
        response = await asyncio.wait_for(reset, timeout=15)
    except Exception as exc:
        reset_error, response = exc, None
    assert revoke_error is None and reset_error is None, f"deadlock: revoke={revoke_error!r} reset={reset_error!r}"
    assert response.status_code == 400  # the Re-send superseded the link first, so the reset is refused, cleanly


# QA-006: the expired-links panel sat below the fold on the IT and Overseas dashboards, so nothing at the top told an
# admin there was anything to act on. Both portal dashboards now lead with the same scoped count as a metric tile.
def _expired_tile(payload: dict):
    return next((m["value"] for m in payload["metrics"] if m["label"] == "Expired welcome links"), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division,other_division,other_role", [("it_admin", "it", "overseas", "counselor"), ("overseas_admin", "overseas", "it", "trainer")])
async def test_the_portal_dashboard_leads_with_a_scoped_expired_links_tile(client, db_session, role, division, other_division, other_role):
    admin = await _make_user(db_session, role=role, division=division)
    assert (await _login(client, admin.email, division=division)).status_code == 200
    url = f"/api/v1/portal/{division}/{'admin'}/dashboard"
    before = _expired_tile((await client.get(url)).json())
    assert isinstance(before, int), "the dashboard has no 'Expired welcome links' metric"
    mine = await _make_user(db_session, role="counselor" if division == "overseas" else "trainer", division=division, email_verified=False)
    await _seed_token(db_session, mine, expires_in=timedelta(hours=-1))
    theirs = await _make_user(db_session, role=other_role, division=other_division, email_verified=False)
    await _seed_token(db_session, theirs, expires_in=timedelta(hours=-1))
    live = await _make_user(db_session, role="counselor" if division == "overseas" else "trainer", division=division, email_verified=False)
    await _seed_token(db_session, live)  # still valid: not expired
    assert _expired_tile((await client.get(url)).json()) == before + 1


# QA-005: the Users table next to the Manage users panel listed a not-yet-activated account as just "Active: true", while the
# panel said "Awaiting setup". Both adjacent lists now agree, and use the same labels as the Super Admin table's Setup column.
@pytest.mark.asyncio
@pytest.mark.parametrize("role,division,section_division", [("it_admin", "it", "it"), ("overseas_admin", "overseas", "overseas")])
async def test_the_users_table_shows_each_accounts_setup_state(client, db_session, role, division, section_division):
    admin = await _make_user(db_session, role=role, division=division)
    assert (await _login(client, admin.email, division=division)).status_code == 200
    member_role = "counselor" if division == "overseas" else "trainer"
    pending = await _make_user(db_session, role=member_role, division=division, email_verified=False)
    await _seed_token(db_session, pending)
    expired = await _make_user(db_session, role=member_role, division=division, email_verified=False)
    await _seed_token(db_session, expired, expires_in=timedelta(hours=-1))
    active = await _make_user(db_session, role=member_role, division=division)
    payload = (await client.get(f"/api/v1/portal/{section_division}/admin/users")).json()
    assert {"key": "setup", "label": "Setup"} in payload["columns"]
    by_email = {row["email"]: row for row in payload["rows"]}
    assert by_email[pending.email]["setup"] == "Awaiting setup"
    assert by_email[expired.email]["setup"] == "Link expired"
    assert by_email[active.email]["setup"] == "Password set"


@pytest.mark.asyncio
async def test_dashboard_reports_the_scoped_expired_link_count(client, db_session):
    admin = await _make_user(db_session)
    assert (await _login(client, admin.email)).status_code == 200
    before = (await client.get("/api/v1/admin/dashboard")).json()["expired_welcome_links"]
    assert isinstance(before, int)
    await _seed_token(db_session, await _make_user(db_session, role="counselor", division="overseas"), expires_in=timedelta(hours=-1))
    await _seed_token(db_session, await _make_user(db_session, role="trainer", division="it"), expires_in=timedelta(hours=-1))
    after = (await client.get("/api/v1/admin/dashboard")).json()["expired_welcome_links"]
    assert after == before + 1  # only the overseas one is in this admin's scope


@pytest.mark.asyncio
async def test_changing_active_revokes_the_open_welcome_link_and_reactivation_needs_a_resend(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    old, uid = created["development_welcome_token"], created["id"]

    assert (await client.patch(f"/api/v1/admin/users/{uid}", json={"active": False})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400
    assert (await client.post(f"/api/v1/admin/users/{uid}/welcome-links")).status_code == 409  # deactivated: reactivate first

    assert (await client.patch(f"/api/v1/admin/users/{uid}", json={"active": True})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400  # the old link stays dead
    assert uid in {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}

    fresh = await client.post(f"/api/v1/admin/users/{uid}/welcome-links")
    assert fresh.status_code == 201
    assert (await client.post(RESET_URL, json={"token": fresh.json()["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_a_patch_that_leaves_active_unchanged_does_not_revoke_the_link(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    assert (await client.patch(f"/api/v1/admin/users/{created['id']}", json={"active": True, "full_name": "Renamed"})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": created["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_resend_and_its_throttle_are_logged_without_secrets(client, db_session, monkeypatch, caplog):
    import logging

    admin = await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    url = f"/api/v1/admin/users/{created['id']}/welcome-links"
    with caplog.at_level(logging.INFO, logger="app.admin"):
        assert (await client.post(url)).status_code == 201
        assert (await client.post(url)).status_code == 429
    by_message = {r.getMessage(): r for r in caplog.records if r.name == "app.admin"}
    resent = by_message["welcome_link_resent"]
    assert resent.levelno == logging.INFO and resent.extra_fields == {"actor_id": str(admin.id), "user_id": created["id"]}
    throttled = by_message["welcome_link_resend_throttled"]
    assert throttled.levelno == logging.WARNING and throttled.extra_fields["user_id"] == created["id"] and throttled.extra_fields["wait_seconds"] > 0
    blob = json.dumps([getattr(r, "extra_fields", {}) for r in caplog.records if r.name == "app.admin"], default=str)
    assert created["development_welcome_token"] not in blob and created["email"] not in blob


@pytest.mark.asyncio
async def test_revoking_links_on_an_active_change_is_logged(client, db_session, monkeypatch, caplog):
    import logging

    admin = await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    with caplog.at_level(logging.INFO, logger="app.admin"):
        assert (await client.patch(f"/api/v1/admin/users/{created['id']}", json={"active": False})).status_code == 200
    record = next(r for r in caplog.records if r.name == "app.admin" and r.getMessage() == "welcome_links_revoked_on_active_change")
    assert record.levelno == logging.INFO
    assert record.extra_fields == {"actor_id": str(admin.id), "user_id": created["id"], "active": False}


@pytest.mark.asyncio
async def test_two_simultaneous_resends_serialize_to_one_link_and_one_throttle(client, db_session, monkeypatch):
    """The user-row lock makes the second request wait for the first one's commit and so see its new
    token (and the cooldown); without it both pass the throttle and two links go out. A short pause
    right after the cooldown check widens the race window so an unlocked implementation fails
    reliably (a bare gather happens to interleave harmlessly and would pass either way)."""
    from app.api import admin as admin_module

    real_wait = admin_module.resend_wait_seconds

    async def slow_wait(db, user_id):
        wait = await real_wait(db, user_id)
        await asyncio.sleep(0.3)
        return wait

    monkeypatch.setattr(admin_module, "resend_wait_seconds", slow_wait)
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    url = f"/api/v1/admin/users/{created['id']}/welcome-links"
    results = await asyncio.gather(client.post(url), client.post(url))
    assert sorted(r.status_code for r in results) == [201, 429]
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(created["id"]), PasswordResetToken.purpose == "welcome"))).all()
    assert len(tokens) == 2 and sum(1 for t in tokens if t.superseded_at is None) == 1
