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
from app.models import AuditLog, PasswordResetToken, User

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
        user_id=user.id, token_hash=_sha(raw), purpose=purpose, expires_at=now + expires_in,
        used_at=now if used else None, superseded_at=now if superseded else None,
    )
    if created_at is not None:
        token.created_at = created_at
    db_session.add(token)
    await db_session.commit()
    return raw, token


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
    base = dict(to_email="new.staff@example.local", recipient_name="Asha", role="academic_team", set_password_url=LINK, expires_at=datetime.now(UTC) + timedelta(hours=72), invited_by_name="Overseas Admin")
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
    assert result[pending.id].status == "pending_setup"
    assert result[expired.id].status == "link_expired"
    assert result[resent.id].status == "pending_setup"
    assert result[revoked.id].status == "link_expired"
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
    dev = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert dev["email_status"] == "sent" and dev["development_welcome_token"] == issued.raw and dev["expires_at"] == issued.expires_at

    monkeypatch.setattr(settings, "environment", "production")
    prod = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert "development_welcome_token" not in prod

    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))).all()
    assert len(audit) == 2 and all(issued.raw not in json.dumps(a.metadata_json) for a in audit)
    assert audit[0].metadata_json["smtp_status"] == "sent"


@pytest.mark.asyncio
async def test_deliver_redacts_urls_from_the_errors_it_stores(db_session, monkeypatch):
    leaky = "Client error '404 Not Found' for url 'https://hooks.example.local/secret-path?key=abc123'"
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "connect to https://smtp.example.local:587 failed"), webhook=("failed", leaky))
    await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    stored = json.dumps(audit.metadata_json)
    assert "hooks.example.local" not in stored and "abc123" not in stored and "smtp.example.local" not in stored
    assert "[redacted-url]" in stored


@pytest.mark.asyncio
async def test_deliver_treats_a_raising_sender_as_a_failed_send_not_an_exception(db_session, monkeypatch):
    def boom():
        raise ValueError("Header values may not contain linefeed or carriage return characters")

    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=boom, webhook=("not_configured", None))
    result = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert result["email_status"] == "failed"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    assert audit.metadata_json["smtp_status"] == "failed" and "linefeed" in audit.metadata_json["smtp_error"]


@pytest.mark.asyncio
async def test_deliver_never_raises_when_the_audit_write_fails(db_session, monkeypatch):
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "boom"), webhook=("not_configured", None))

    async def broken_commit():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "commit", broken_commit)
    result = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
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
        await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
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
        await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    records, blob = _provisioning_log_blob(caplog)
    record = next(r for r in records if r.getMessage() == "welcome_link_not_delivered")
    assert record.levelno == logging.WARNING
    assert record.extra_fields["smtp_status"] == "failed" and record.extra_fields["token_id"] == str(issued.token_id)
    assert "victim@example.local" not in blob and "smtp.example.local" not in blob and issued.raw not in blob and target.email not in blob
    stored = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    assert "victim@example.local" not in json.dumps(stored.metadata_json)
