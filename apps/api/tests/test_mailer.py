"""app.services.mailer -- real SMTP sending for School invite emails (added alongside the
roster parent-invite addendum). Not_configured/sent/failed states, and that the composed
message actually carries the Coordinator's name/email for Reply-To (not the recipient's).
"""

import smtplib
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.services import mailer


@pytest.mark.asyncio
async def test_returns_not_configured_when_smtp_host_is_unset(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    status, error = await mailer.send_school_invite_email(
        to_email="parent@example.local", recipient_name="Parent One", role="school_parent",
        school_name="Test School", accept_url="https://example.local/accept/token",
        coordinator_name="Coordinator One", coordinator_email="coord@example.local",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    assert status == "not_configured"
    assert error is None


@pytest.mark.asyncio
async def test_sends_via_smtp_with_coordinator_as_reply_to(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "invites@edusphere.local")
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)

    sent_messages = []

    def fake_send_sync(msg):
        sent_messages.append(msg)

    monkeypatch.setattr(mailer, "_send_sync", fake_send_sync)

    status, error = await mailer.send_school_invite_email(
        to_email="parent@example.local", recipient_name="Parent One", role="school_parent",
        school_name="Test School", accept_url="https://example.local/accept/token",
        coordinator_name="Coordinator One", coordinator_email="coord@example.local",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    assert status == "sent"
    assert error is None
    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg["To"] == "parent@example.local"
    assert "invites@edusphere.local" in msg["From"]  # technical sender must be the verified account
    assert "Coordinator One" in msg["From"]  # display name still carries the coordinator
    assert msg["Reply-To"] == "Coordinator One <coord@example.local>"
    html_part = msg.get_body(preferencelist=("html",))
    assert "Test School" in html_part.get_content()
    assert "https://example.local/accept/token" in html_part.get_content()
    assert f'src="{mailer.LOGO_SRC}"' in html_part.get_content()


@pytest.mark.asyncio
async def test_returns_failed_with_reason_when_smtp_raises(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "invites@edusphere.local")

    def raising_send_sync(msg):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(mailer, "_send_sync", raising_send_sync)

    status, error = await mailer.send_school_invite_email(
        to_email="parent@example.local", recipient_name="Parent One", role="school_parent",
        school_name="Test School", accept_url="https://example.local/accept/token",
        coordinator_name="Coordinator One", coordinator_email="coord@example.local",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    assert status == "failed"
    assert error is not None and "535" in error


# The header logo is embedded in the message (cid:), not fetched from FRONTEND_URL: a localhost/private FRONTEND_URL left
# every client showing a broken image, since mail clients fetch remote images through their own proxies.
@pytest.mark.asyncio
@pytest.mark.parametrize("send", [
    lambda: mailer.send_school_invite_email(
        to_email="p@example.local", recipient_name="P", role="school_parent", school_name="S",
        accept_url="https://example.local/a", coordinator_name="C", coordinator_email="c@example.local",
        expires_at=datetime.now(UTC) + timedelta(days=7)),
    lambda: mailer.send_parent_notification_email(
        to_email="p@example.local", recipient_name="P", school_name="S", title="T", body="B", action_url=None),
    lambda: mailer.send_welcome_email(
        to_email="p@example.local", recipient_name="P", role="it_student", set_password_url="https://example.local/s",
        expires_at=datetime.now(UTC) + timedelta(hours=72), invited_by_name="Admin"),
    lambda: mailer.send_bdm_reminder_email(
        to_email="p@example.local", recipient_name="P", title="T", body="B", links=[{"label": "Open", "path": "/bdm"}]),
], ids=["school_invite", "parent_notification", "welcome", "bdm_reminder"])
async def test_logo_is_embedded_inline_not_linked_to_frontend_url(monkeypatch, send):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "invites@edusphere.local")
    monkeypatch.setattr(settings, "frontend_url", "http://localhost:3000")
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", sent.append)

    status, error = await send()

    assert (status, error) == ("sent", None)
    msg = sent[0]
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert f'src="{mailer.LOGO_SRC}"' in html
    assert "/brand/logo-dark.png" not in html
    images = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert len(images) == 1
    assert images[0]["Content-ID"] == f"<{mailer.LOGO_CID}>"
    assert images[0].get_content_disposition() == "inline"
    assert images[0].get_content().startswith(b"\x89PNG")
    # The plain-text alternative is still there for clients that do not render HTML.
    assert msg.get_body(preferencelist=("plain",)) is not None
