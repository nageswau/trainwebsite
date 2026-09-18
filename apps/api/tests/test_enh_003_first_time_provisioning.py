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
