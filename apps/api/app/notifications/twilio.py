"""ENH-014 (spec §6.4; DEC-NOT-001 2026-09-30 D2, D13): Twilio WhatsApp + SMS over the Messages REST API with httpx.

The Twilio response is untrusted: only `sid` (shape-checked) and the numeric error `code` are read. Stored errors have
runs of 6+ digits redacted (Twilio messages can echo the recipient's number). The auth token is sent only as basic auth
and never appears in an error or a log."""

import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
TIMEOUT_SECONDS = 10
VARIABLE_MAX = 500
SMS_MAX = 320
_SID = re.compile(r"(SM|MM)[0-9a-f]{32}")
_DIGIT_RUN = re.compile(r"[0-9]{6,}")


@dataclass(frozen=True)
class SendResult:
    status: str  # "sent" | "failed" | "skipped" | "not_configured"
    provider_reference: str | None = None
    error: str | None = None
    transient: bool = False


def configured(channel: str) -> bool:
    sender = settings.twilio_whatsapp_from if channel == "whatsapp" else settings.twilio_sms_from
    template_ok = bool(settings.twilio_whatsapp_content_sid) if channel == "whatsapp" else True
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and sender and template_ok)


def plain(text: str | None, limit: int = VARIABLE_MAX) -> str:
    return " ".join((text or "").split())[:limit]


def portal_link(action_url: str | None) -> str:
    base = settings.frontend_url.rstrip("/")
    path = plain(action_url)  # flattened first, like the other variables: a newline would break the WhatsApp template
    internal = path.startswith("/") and not path.startswith(("//", "/\\"))
    return base + (path if internal else "/")


async def send_whatsapp(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult:
    variables = {"1": plain(title), "2": plain(body), "3": portal_link(action_url)}
    data = {"From": f"whatsapp:{settings.twilio_whatsapp_from}", "To": f"whatsapp:{to}", "ContentSid": settings.twilio_whatsapp_content_sid, "ContentVariables": json.dumps(variables, ensure_ascii=False)}
    return await _post(data, client)


async def send_sms(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult:
    link = portal_link(action_url)
    text = plain(f"{title} — {body}", max(0, SMS_MAX - len(link) - 1))
    return await _post({"From": settings.twilio_sms_from, "To": to, "Body": f"{text} {link}"}, client)


async def _post(data: dict, client: httpx.AsyncClient | None) -> SendResult:
    url = API.format(sid=settings.twilio_account_sid)
    auth = (settings.twilio_account_sid or "", settings.twilio_auth_token or "")
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as own:
                response = await own.post(url, data=data, auth=auth)
        else:
            response = await client.post(url, data=data, auth=auth)
    except httpx.HTTPError as exc:
        return SendResult("failed", error=f"twilio:network {type(exc).__name__}", transient=True)
    payload = _json_object(response)
    if response.is_success:
        sid = payload.get("sid")
        if isinstance(sid, str) and _SID.fullmatch(sid):
            return SendResult("sent", provider_reference=sid)
        return SendResult("failed", error="twilio:unexpected response")
    code, message = payload.get("code"), payload.get("message")
    detail = f"twilio:{code if isinstance(code, int) else response.status_code}"
    if isinstance(message, str):
        detail += " " + _DIGIT_RUN.sub("…", message)
    return SendResult("failed", error=detail[:500], transient=response.status_code == 429 or response.status_code >= 500)


def _json_object(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
