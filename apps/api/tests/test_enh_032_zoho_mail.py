"""ENH-032 / DEC-SCOPE-225: EMAIL_TRANSPORT setting, the single email_configured() check and the
admin system-status email row."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.security import hash_password
from app.models import User
from app.services import mailer

ZOHO_FIELDS = ["smtp_from_email", "zoho_mail_client_id", "zoho_mail_client_secret", "zoho_mail_refresh_token", "zoho_mail_account_id"]


def _zoho_on(monkeypatch):
    monkeypatch.setattr(settings, "email_transport", "zoho_api")
    monkeypatch.setattr(settings, "smtp_host", None)
    for name in ZOHO_FIELDS:
        monkeypatch.setattr(settings, name, f"{name}-value")


def test_smtp_mode_needs_host_and_from(monkeypatch):
    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")
    assert mailer.email_configured() is True
    monkeypatch.setattr(settings, "smtp_host", None)
    assert mailer.email_configured() is False


def test_zoho_mode_needs_from_and_all_four_credentials(monkeypatch):
    _zoho_on(monkeypatch)
    assert mailer.email_configured() is True


@pytest.mark.parametrize("missing", ZOHO_FIELDS)
def test_zoho_mode_missing_any_value_is_not_configured(monkeypatch, missing):
    _zoho_on(monkeypatch)
    monkeypatch.setattr(settings, missing, None)
    assert mailer.email_configured() is False


def test_smtp_configured_is_the_same_check():
    assert mailer.smtp_configured is mailer.email_configured


def test_unknown_transport_is_rejected():
    with pytest.raises(ValidationError):
        Settings(email_transport="sendgrid")


@pytest.mark.asyncio
async def test_zoho_mode_without_smtp_host_is_not_reported_not_configured(monkeypatch):
    _zoho_on(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    result = await mailer.send_welcome_email(
        to_email="new@example.local", recipient_name="New User", role="student",
        set_password_url="https://example.local/set-password/token",
        expires_at=datetime.now(UTC) + timedelta(days=7), invited_by_name="Admin",
    )
    assert result == ("sent", None)
    assert len(sent) == 1


async def _email_row(db_session, client) -> dict:
    email = f"enh032-{uuid.uuid4().hex[:8]}@example.local"
    db_session.add(User(email=email, password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Admin", role="super_admin", division="it", active=True))
    await db_session.commit()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert login.status_code == 200
    response = await client.get("/api/v1/admin/system-status")
    assert response.status_code == 200
    rows = [r for r in response.json() if r["service"] == "Email delivery"]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_system_status_reports_the_email_transport(db_session, client, monkeypatch):
    _zoho_on(monkeypatch)
    assert (await _email_row(db_session, client))["status"] == "Zoho Mail API"

    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    assert (await _email_row(db_session, client))["status"] == "SMTP"

    monkeypatch.setattr(settings, "smtp_host", None)
    assert (await _email_row(db_session, client))["status"] == "not configured"
