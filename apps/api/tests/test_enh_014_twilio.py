"""ENH-014 Task 5 -- Twilio Messages API adapter (spec §6.4; AC16). httpx.MockTransport: no network."""

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.notifications import twilio

SID = "SM" + "a" * 32


@pytest.fixture(autouse=True)
def _twilio_settings(monkeypatch):
    for key, value in {
        "twilio_account_sid": "AC123",
        "twilio_auth_token": "secret-token",
        "twilio_whatsapp_from": "+14155238886",
        "twilio_sms_from": "+15005550006",
        "twilio_whatsapp_content_sid": "HX123",
        "frontend_url": "https://portal.example",
    }.items():
        monkeypatch.setattr(settings, key, value)


def _client(status: int, body, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _form(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


@pytest.mark.asyncio
async def test_whatsapp_uses_the_template_with_basic_auth():
    seen = []
    result = await twilio.send_whatsapp("+919876543210", "Result published", "Maths is out.", "/school/parent/dashboard", client=_client(201, {"sid": SID}, seen))
    assert result == twilio.SendResult("sent", provider_reference=SID)
    [request] = seen
    assert str(request.url) == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"AC123:secret-token").decode()
    form = _form(request)
    assert (form["From"], form["To"], form["ContentSid"]) == ("whatsapp:+14155238886", "whatsapp:+919876543210", "HX123")
    assert json.loads(form["ContentVariables"]) == {"1": "Result published", "2": "Maths is out.", "3": "https://portal.example/school/parent/dashboard"}


@pytest.mark.asyncio
async def test_sms_is_one_capped_line_with_the_link():
    seen = []
    await twilio.send_sms("+919876543210", "Result", "x" * 1000, "/school/parent/dashboard", client=_client(201, {"sid": SID}, seen))
    form = _form(seen[0])
    assert (form["From"], form["To"]) == ("+15005550006", "+919876543210")
    assert len(form["Body"]) <= 320 and form["Body"].startswith("Result — x") and form["Body"].endswith(" https://portal.example/school/parent/dashboard")


@pytest.mark.parametrize("action_url", [None, "", "https://evil.example/x", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
def test_missing_or_offsite_link_falls_back_to_portal_home(action_url):
    # Review Focus 3 + spec §6.4: never an off-site link, and never an empty template variable.
    assert twilio.portal_link(action_url) == "https://portal.example/"


def test_variables_are_single_line_and_capped():
    # Review Focus 5: newlines/tabs collapse (WhatsApp rejects them in variables); non-Latin text survives the cap.
    assert twilio.plain("विद्यालय\n\n  परिणाम\tघोषित") == "विद्यालय परिणाम घोषित"
    assert len(twilio.plain("अ" * 900)) == 500


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "transient"), [(429, True), (500, True), (503, True), (400, False), (401, False)])
async def test_failures_are_classified_and_redacted(status, transient):
    body = {"code": 21211, "message": "The 'To' number +919876543210 is not a valid phone number."}
    result = await twilio.send_sms("+919876543210", "t", "b", None, client=_client(status, body, []))
    assert result.status == "failed" and result.transient is transient
    assert result.error.startswith("twilio:21211 ")
    assert "9876543210" not in result.error and "secret-token" not in result.error


@pytest.mark.asyncio
async def test_network_errors_are_transient_and_carry_no_detail():
    def handler(request):
        raise httpx.ConnectTimeout("timed out talking to https://AC123:secret-token@api.twilio.com")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await twilio.send_whatsapp("+919876543210", "t", "b", None, client=client)
    assert (result.status, result.transient, result.error) == ("failed", True, "twilio:network ConnectTimeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"sid": "not-a-sid"}, {}, "<html>ok</html>", ["SM"]])
async def test_an_unrecognised_success_body_is_a_permanent_failure(body):
    # Accepted-but-unparseable must not be retried: a retry could send the message twice.
    result = await twilio.send_sms("+919876543210", "t", "b", None, client=_client(201, body, []))
    assert (result.status, result.transient, result.error) == ("failed", False, "twilio:unexpected response")


def test_configured_needs_every_value(monkeypatch):
    assert twilio.configured("whatsapp") and twilio.configured("sms")
    monkeypatch.setattr(settings, "twilio_whatsapp_content_sid", "")
    assert not twilio.configured("whatsapp") and twilio.configured("sms")
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    assert not twilio.configured("sms")
