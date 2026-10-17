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
from tests.test_tel_014_delivery import outbox, smtp_on  # noqa: F401 -- fixtures reused for the lead-email retry tests

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


# ---- Task 2: Zoho Mail transport module (httpx.MockTransport, no network) ----
import threading  # noqa: E402
import time  # noqa: E402
from email.message import EmailMessage  # noqa: E402
from urllib.parse import parse_qs  # noqa: E402

import httpx  # noqa: E402

SECRETS = {"client_id": "cid-value", "client_secret": "sekret-value", "refresh_token": "refresh-value"}


@pytest.fixture(autouse=True)
def _zoho_transport(monkeypatch):
    from app.services import zoho_mail

    zoho_mail.reset_token_cache()
    monkeypatch.setattr(settings, "email_transport", "zoho_api")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")
    monkeypatch.setattr(settings, "zoho_mail_client_id", SECRETS["client_id"])
    monkeypatch.setattr(settings, "zoho_mail_client_secret", SECRETS["client_secret"])
    monkeypatch.setattr(settings, "zoho_mail_refresh_token", SECRETS["refresh_token"])
    monkeypatch.setattr(settings, "zoho_mail_account_id", "acct42")
    monkeypatch.setattr(settings, "zoho_mail_api_base", "https://mail.zoho.test")
    yield
    zoho_mail.reset_token_cache()


def _lead_msg() -> EmailMessage:
    return mailer.lead_email_message(to_email="lead@example.local", subject="Hello there", body="Hi\nhttps://x.example/a", sender_name="Tina", sender_email="tina@example.local")


def _welcome_msg() -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Welcome"
    msg["From"] = "noreply@example.local"
    msg["To"] = "new@example.local"
    msg.set_content("plain welcome")
    msg.add_alternative(
        mailer._welcome_html(recipient_name="New", role_label="Student", set_password_url="https://x.example/p", expires_label="72 hours", invited_by_name="Admin"),
        subtype="html",
    )
    mailer._attach_logo(msg)
    return msg


def _mock(send_responses=None, token_response=None, token_delay=0.0):
    """The token endpoint answers `token_response`; the messages endpoint pops `send_responses` (the last one repeats)."""
    seen = []
    sends = list(send_responses or [httpx.Response(200, json={"status": {"code": 200}})])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/oauth/v2/token":
            if token_delay:
                time.sleep(token_delay)
            return token_response or httpx.Response(200, json={"access_token": "tok1", "expires_in": 3600})
        item = sends.pop(0) if len(sends) > 1 else sends[0]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_payload_is_from_the_system_address_with_html_and_no_reply_to():
    from app.services import zoho_mail

    msg = _lead_msg()
    assert msg["Reply-To"]
    payload = zoho_mail.payload_from_message(msg)
    assert payload["fromAddress"] == settings.smtp_from_email
    assert payload["toAddress"] == "lead@example.local"
    assert payload["subject"] == "Hello there"
    assert payload["mailFormat"] == "html"
    assert "replyTo" not in payload and not any("reply" in k.lower() for k in payload)


def test_the_logo_image_is_stripped_from_html():
    from app.services import zoho_mail

    msg = _welcome_msg()
    assert 'src="cid:' in msg.get_body(preferencelist=("html",)).get_content()  # precondition: the logo tag exists
    payload = zoho_mail.payload_from_message(msg)
    assert "cid:" not in payload["content"]
    assert 'alt="EduSphere"' not in payload["content"]
    assert "https://x.example/p" in payload["content"]


def test_a_text_only_message_sends_as_plaintext():
    from app.services import zoho_mail

    msg = EmailMessage()
    msg["Subject"], msg["To"] = "Plain", "a@example.local"
    msg.set_content("just text")
    payload = zoho_mail.payload_from_message(msg)
    assert payload["mailFormat"] == "plaintext"
    assert payload["content"].strip() == "just text"


def test_send_posts_to_the_account_messages_url_with_the_oauth_header():
    from app.services import zoho_mail

    client, seen = _mock()
    zoho_mail.send(_lead_msg(), client=client)
    token_req, send_req = seen
    assert str(token_req.url) == f"{settings.zoho_accounts_url}/oauth/v2/token"
    assert token_req.url.query == b""
    form = {k: v[0] for k, v in parse_qs(token_req.content.decode()).items()}
    assert form == {"grant_type": "refresh_token", **SECRETS}
    assert str(send_req.url) == "https://mail.zoho.test/api/accounts/acct42/messages"
    assert send_req.headers["authorization"] == "Zoho-oauthtoken tok1"


def test_the_token_is_cached_across_sends():
    from app.services import zoho_mail

    client, seen = _mock()
    zoho_mail.send(_lead_msg(), client=client)
    zoho_mail.send(_lead_msg(), client=client)
    assert sum(r.url.path == "/oauth/v2/token" for r in seen) == 1


def test_concurrent_sends_refresh_once():
    from app.services import zoho_mail

    client, seen = _mock(token_delay=0.2)
    threads = [threading.Thread(target=zoho_mail.send, args=(_lead_msg(),), kwargs={"client": client}) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r.url.path == "/oauth/v2/token" for r in seen) == 1
    assert sum(r.url.path.endswith("/messages") for r in seen) == 2


def test_a_401_refreshes_once_and_retries():
    from app.services import zoho_mail

    client, seen = _mock(send_responses=[httpx.Response(401, json={}), httpx.Response(200, json={})])
    zoho_mail.send(_lead_msg(), client=client)
    assert sum(r.url.path == "/oauth/v2/token" for r in seen) == 2
    assert sum(r.url.path.endswith("/messages") for r in seen) == 2

    zoho_mail.reset_token_cache()
    client, _ = _mock(send_responses=[httpx.Response(401, json={})])
    with pytest.raises(zoho_mail.EmailPermanentError):
        zoho_mail.send(_lead_msg(), client=client)


def test_a_refused_refresh_token_is_permanent_and_secret_free():
    from app.services import zoho_mail

    client, _ = _mock(token_response=httpx.Response(200, json={"error": "invalid_code"}))
    with pytest.raises(zoho_mail.EmailPermanentError) as exc:
        zoho_mail.send(_lead_msg(), client=client)
    text = str(exc.value)
    assert "invalid_code" in text
    assert SECRETS["refresh_token"] not in text and SECRETS["client_secret"] not in text


CASES = [
    (httpx.ConnectError("boom"), "transient"),
    (httpx.ConnectTimeout("boom"), "transient"),
    (httpx.ReadTimeout("boom"), "permanent"),
    (httpx.RemoteProtocolError("boom"), "permanent"),
    (httpx.Response(500, json={}), "transient"),
    (httpx.Response(503, json={}), "transient"),
    (httpx.Response(429, json={}), "permanent"),
    (httpx.Response(400, json={"data": {"errorCode": "INVALID_INPUT"}}), "permanent"),
    (httpx.Response(403, json={}), "permanent"),
]


def _error_type(kind: str):
    from app.services import zoho_mail

    return zoho_mail.EmailTransientError if kind == "transient" else zoho_mail.EmailPermanentError


@pytest.mark.parametrize("outcome,kind", CASES)
def test_error_classification(outcome, kind):
    from app.services import zoho_mail

    client, _ = _mock(send_responses=[outcome])
    with pytest.raises(_error_type(kind)):
        zoho_mail.send(_lead_msg(), client=client)


@pytest.mark.parametrize("outcome,kind", CASES)
def test_errors_never_carry_secrets(outcome, kind):
    from app.services import zoho_mail

    client, _ = _mock(send_responses=[outcome])
    with pytest.raises(_error_type(kind)) as exc:
        zoho_mail.send(_lead_msg(), client=client)
    text = str(exc.value)
    assert "tok1" not in text and len(text) <= 200
    assert not any(v in text for v in SECRETS.values())


# --- Task 3: dispatch in _send_sync and the retry mapping in the callers -----------------------------------------------------------
def test_send_sync_dispatches_by_transport(monkeypatch):
    import smtplib

    from app.services import zoho_mail

    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            calls.append("smtp")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self): ...
        def login(self, *a): ...
        def send_message(self, msg): ...

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(zoho_mail, "send", lambda msg, **k: calls.append("zoho"))
    msg = mailer.EmailMessage()
    monkeypatch.setattr(settings, "email_transport", "zoho_api")
    mailer._send_sync(msg)
    assert calls == ["zoho"]
    calls.clear()
    monkeypatch.setattr(settings, "email_transport", "smtp")
    mailer._send_sync(msg)
    assert calls == ["smtp"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected,enqueued", [("transient", "retrying", 1), ("permanent", "failed", 0)])
async def test_lead_email_retries_transient_and_fails_permanent(db_session, smtp_on, outbox, lead_emails_enqueued, kind, expected, enqueued):
    from app.notifications import lead_email
    from tests.test_tel_014_delivery import queued

    message, _, _ = await queued(db_session)
    outbox.fail(_error_type(kind)("boom"))
    assert await lead_email.deliver_lead_email(message.id) == expected
    assert len(lead_emails_enqueued) == enqueued
    if enqueued:
        assert lead_emails_enqueued == [(str(message.id), 60)]


def _snapshot():
    from app.notifications.delivery import _Snapshot

    return _Snapshot(title="T", body="B", action_url=None, email="a@example.com", full_name="A", phone=None, active=True, whatsapp_opt_in=False, sms_opt_in=False)


@pytest.mark.asyncio
async def test_a_permanent_mailer_failure_is_not_a_transient_delivery(monkeypatch):
    from app.notifications import delivery
    from app.services import zoho_mail

    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")
    monkeypatch.setattr(settings, "email_transport", "smtp")

    def boom(exc):
        def fail(msg):
            raise exc

        return fail

    kwargs = dict(to_email="a@example.com", recipient_name="A", title="T", body="B", links=[])
    monkeypatch.setattr(mailer, "_send_sync", boom(zoho_mail.EmailPermanentError("x")))
    assert await mailer.send_bdm_reminder_email(**kwargs) == ("failed", "permanent: x")
    result = await delivery._send_email(_snapshot(), {"kind": "bdm_reminder"})
    assert result.transient is False
    monkeypatch.setattr(mailer, "_send_sync", boom(zoho_mail.EmailTransientError("x")))
    assert (await delivery._send_email(_snapshot(), {"kind": "bdm_reminder"})).transient is True


@pytest.mark.asyncio
async def test_smtp_failures_keep_todays_transient_behaviour(monkeypatch):
    from app.notifications import delivery

    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")
    monkeypatch.setattr(settings, "email_transport", "smtp")

    def fail(msg):
        raise OSError("conn reset")

    monkeypatch.setattr(mailer, "_send_sync", fail)
    result = await delivery._send_email(_snapshot(), {"kind": "bdm_reminder"})
    assert result.status == "failed" and result.transient is True


def test_failure_text_and_is_permanent():
    from app.services import zoho_mail

    assert mailer.failure_text(zoho_mail.EmailPermanentError("x" * 600)) == "permanent: " + "x" * 480
    assert mailer.failure_text(OSError("y" * 600)) == "y" * 500
    assert mailer.is_permanent("permanent: x") and not mailer.is_permanent("x") and not mailer.is_permanent(None)
    assert mailer.EmailTransientError is zoho_mail.EmailTransientError


# --- E8: password-reset and generic/inbound notification emails --------------------------------------------------------------


async def _forgot(client, db_session, role, division, monkeypatch, outbox_unused=None):
    from tests.enh014_helpers import make_user

    return await make_user(db_session, role=role, division=division)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "segment"), [("it_student", "overseas", "overseas"), ("bdm_manager", "global", "admin")])
async def test_forgot_password_emails_the_portal_reset_link(client, db_session, outbox, monkeypatch, role, division, segment):
    from sqlalchemy import select

    from app.models import NotificationDelivery

    user = await _forgot(client, db_session, role, division, monkeypatch)
    response = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert response.status_code == 202
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == user.email and msg["Subject"] == "Reset your EduSphere password"
    assert f"{settings.frontend_url}/{segment}/reset-password?token=" in msg.get_body(("plain",)).get_content()
    assert (await db_session.scalars(select(NotificationDelivery.status).order_by(NotificationDelivery.created_at.desc()))).first() == "sent"


@pytest.mark.asyncio
async def test_forgot_password_falls_back_to_the_webhook_when_email_is_not_configured(client, db_session, monkeypatch):
    from app.api import auth

    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", None)
    calls, sent = [], []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))

    async def fake(channel, payload):
        calls.append((channel, payload))
        return "sent", None

    monkeypatch.setattr(auth, "send_notification", fake)
    user = await _forgot(client, db_session, "it_student", "overseas", monkeypatch)
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": user.email})).status_code == 202
    assert len(calls) == 1 and calls[0][1]["template"] == "password_reset" and calls[0][1]["to"] == user.email
    assert sent == []


@pytest.mark.asyncio
async def test_forgot_password_for_an_unknown_email_sends_nothing(client, outbox, monkeypatch):
    from app.api import auth

    calls = []

    async def fake(channel, payload):
        calls.append(payload)
        return "sent", None

    monkeypatch.setattr(auth, "send_notification", fake)
    response = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody-here@example.local"})
    assert response.status_code == 202
    assert len(outbox) == 0 and calls == []


@pytest.mark.asyncio
async def test_the_reset_token_appears_only_in_the_link(client, db_session, outbox, monkeypatch):
    from sqlalchemy import select

    from app.models import NotificationDelivery
    from app.services import zoho_mail

    monkeypatch.setattr(settings, "environment", "development")
    user = await _forgot(client, db_session, "it_student", "overseas", monkeypatch)
    outbox.fail(zoho_mail.EmailPermanentError("rejected"))
    response = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    raw = response.json()["development_reset_token"]
    row = (await db_session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()))).first()
    assert row.status == "failed" and row.error.startswith("permanent: ")
    assert raw not in (row.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("context", [None, {"kind": "inbound"}])
@pytest.mark.parametrize("configured", [True, False])
async def test_generic_and_inbound_notifications_use_the_mailer_then_the_webhook(monkeypatch, outbox, context, configured):
    from app.notifications import delivery

    if not configured:
        monkeypatch.setattr(settings, "email_transport", "smtp")
        monkeypatch.setattr(settings, "smtp_host", None)
    calls = []

    async def fake(channel, payload):
        calls.append((channel, payload))
        return "sent", None

    monkeypatch.setattr(delivery, "send_notification", fake)
    import dataclasses

    snap = dataclasses.replace(_snapshot(), phone="+441234567890")
    result = await delivery._send_email(snap, context)
    assert result.status == "sent"
    if configured:
        assert calls == [] and len(outbox) == 1 and outbox[0]["Subject"] == "T -- EduSphere"
    else:
        assert outbox == []
        expected = {"to": "a@example.com", "title": "T", "body": "B", "action_url": None}
        if context is None:
            expected["phone"] = "+441234567890"
        assert calls == [("email", expected)]


@pytest.mark.asyncio
async def test_new_emails_escape_html(outbox):
    evil = "<script>alert(1)</script>"
    assert await mailer.send_generic_notification_email(to_email="a@example.com", recipient_name=evil, title=evil, body=evil, action_url="https://x.example/?a=1&b=\"2") == ("sent", None)
    assert await mailer.send_password_reset_email(to_email="a@example.com", recipient_name=evil, reset_url="https://x.example/?a=\"<b>", expires_minutes=30) == ("sent", None)
    for msg in outbox:
        html = msg.get_body(("html",)).get_content()
        assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>" not in outbox[1].get_body(("html",)).get_content()


@pytest.mark.asyncio
async def test_reset_email_copy_and_not_configured(monkeypatch, outbox):
    await mailer.send_password_reset_email(to_email="a@example.com", recipient_name="Ann", reset_url="https://x.example/r?token=t", expires_minutes=30)
    assert outbox[0].get_body(("plain",)).get_content() == "Hi Ann,\n\nWe received a request to reset your EduSphere password. Use this link within 30 minutes:\nhttps://x.example/r?token=t\n\nIf you did not ask for this, ignore this email; your password stays the same.\n"
    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", None)
    assert await mailer.send_password_reset_email(to_email="a@example.com", recipient_name="Ann", reset_url="u", expires_minutes=30) == ("not_configured", None)
    assert await mailer.send_generic_notification_email(to_email="a@example.com", recipient_name="Ann", title="t", body="b", action_url=None) == ("not_configured", None)
