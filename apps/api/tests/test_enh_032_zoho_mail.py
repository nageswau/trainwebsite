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
