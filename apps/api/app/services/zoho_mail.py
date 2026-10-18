"""ENH-032 / DEC-SCOPE-225: Zoho Mail REST API email transport (alternative to SMTP; selected by settings.email_transport).

E4: the OAuth access token is cached in memory and refreshed under a lock (one refresh for concurrent senders).
E9: the outcome is mapped to two errors only. EmailTransientError means the message was definitely NOT accepted (safe to retry);
    EmailPermanentError means do not retry -- including every case where the outcome is unknown (read timeout etc.), so no duplicate.
E9 (ruling R1): an HTTP 504 response to the send is also permanent (the gateway may have accepted the message); other 5xx are transient.
E10: HTTP 429 is permanent: Zoho's daily-limit response is not distinguishable from a rate limit in the docs, so it is never retried.
E10 (live test): a 5xx whose data.moreInfo carries an SMTP 5.x.x refusal (Zoho's "550 5.4.6 Unusual sending activity") is permanent;
    error text includes moreInfo (markup stripped) so the stored failure names the real reason.
M2: a refused (permanent) token refresh is remembered for REFUSED_REFRESH_BACKOFF seconds; sends in that window fail at once with the
    same message, without calling the token endpoint again. On a 401 the cache is cleared only if it still holds the rejected token.
Error messages never contain the URL query, headers, request body, tokens or secrets.
"""

import re
import threading
import time
from email.message import EmailMessage

import httpx

from app.core.config import settings

_TIMEOUT = 15
_IMG_CID = re.compile(r'<img\b[^>]*\bsrc="cid:[^"]*"[^>]*>', re.IGNORECASE)
_MAX_ERROR = 200
_TAG = re.compile(r"<[^>]*>")
_SMTP_PERMANENT = re.compile(r"\b5\d\d[ -]5\.\d{1,3}\.\d{1,3}\b")  # an SMTP 5xx reply with a 5.x.x enhanced status code

_lock = threading.Lock()
_token: tuple[str, float] | None = None  # (access_token, expires_at on the monotonic clock)
REFUSED_REFRESH_BACKOFF = 60.0
_refused: tuple[str, float] | None = None  # (secret-free error message, retry-after on the monotonic clock)


class EmailTransientError(Exception):
    """The message was definitely not accepted; safe to retry."""


class EmailPermanentError(Exception):
    """Do not retry."""


def reset_token_cache() -> None:
    """Forget the cached token and any remembered refused refresh."""
    global _token, _refused
    with _lock:
        _token = None
        _refused = None


def _drop_token(rejected: str) -> None:
    """ENH-032 M2: a 401 drops the cached token only if it is still the rejected one -- a concurrent sender may already have
    refreshed, and that new token must not be thrown away (one refresh, not one per 401)."""
    global _token
    with _lock:
        if _token is not None and _token[0] == rejected:
            _token = None


def _cap(text: str) -> str:
    return text[:_MAX_ERROR]


def payload_from_message(msg: EmailMessage) -> dict:
    """fromAddress is the bare system address (display-name support is unverified, spec 4.3); no replyTo is ever sent.
    The inline logo is a cid: attachment Zoho cannot resolve, so its <img> tag is removed."""
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        content, fmt = _IMG_CID.sub("", html_part.get_content()), "html"
    else:
        text_part = msg.get_body(preferencelist=("plain",))
        content, fmt = (text_part.get_content() if text_part is not None else ""), "plaintext"
    return {
        "fromAddress": settings.smtp_from_email,
        "toAddress": msg["To"],
        "subject": msg["Subject"],
        "content": content,
        "mailFormat": fmt,
    }


def _refresh(client: httpx.Client) -> str:
    """Caller holds `_lock`."""
    global _token, _refused
    try:
        response = client.post(
            f"{settings.zoho_accounts_url}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.zoho_mail_client_id,
                "client_secret": settings.zoho_mail_client_secret,
                "refresh_token": settings.zoho_mail_refresh_token,
            },
        )
    except httpx.TransportError as exc:
        raise EmailTransientError(_cap(f"zoho_mail token refresh failed: {type(exc).__name__}")) from None
    if response.status_code >= 500:
        raise EmailTransientError(f"zoho_mail token refresh HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if response.status_code != 200 or data.get("error") or not data.get("access_token"):
        reason = data.get("error") or f"HTTP {response.status_code}"
        message = _cap(f"zoho_mail token refresh refused: {reason}")
        _refused = (message, time.monotonic() + REFUSED_REFRESH_BACKOFF)
        raise EmailPermanentError(message)
    expires_in = data.get("expires_in")
    ttl = float(expires_in) if isinstance(expires_in, (int, float)) else 3600.0
    _token = (data["access_token"], time.monotonic() + max(ttl - 60, 0))
    _refused = None
    return _token[0]


def _access_token(client: httpx.Client) -> str:
    with _lock:
        if _token is not None and time.monotonic() < _token[1]:
            return _token[0]
        if _refused is not None and time.monotonic() < _refused[1]:  # M2: fail fast, do not hammer the token endpoint
            raise EmailPermanentError(_refused[0])
        return _refresh(client)


def _zoho_body(response: httpx.Response) -> tuple[dict, dict]:
    """Zoho's error envelope: {"status": {...}, "data": {...}}; anything else reads as empty."""
    try:
        body = response.json()
    except ValueError:
        return {}, {}
    if not isinstance(body, dict):
        return {}, {}
    raw_status, raw_data = body.get("status"), body.get("data")
    return (raw_status if isinstance(raw_status, dict) else {}), (raw_data if isinstance(raw_data, dict) else {})


def _more_info(data: dict) -> str:
    """data.moreInfo carries the real reason (e.g. the SMTP refusal behind a 500), sometimes with an HTML link; keep the text only."""
    return " ".join(_TAG.sub("", str(data.get("moreInfo") or "")).split())


def _error_text(response: httpx.Response) -> str:
    status, data = _zoho_body(response)
    detail = str(status.get("description") or data.get("errorCode") or "")
    more = _more_info(data)
    return _cap(f"zoho_mail HTTP {response.status_code}: {detail}" + (f" -- {more}" if more else ""))


def _smtp_refused(response: httpx.Response) -> bool:
    """ENH-032 live test (2026-10-18): Zoho wraps a permanent SMTP refusal (e.g. "550 5.4.6 Unusual sending activity detected")
    in an HTTP 500. A 5.x.x reply means the message was refused and retrying only worsens a sending block (E10), so it is
    permanent; a 4.x.x reply keeps the ordinary 5xx-is-transient rule."""
    return bool(_SMTP_PERMANENT.search(_more_info(_zoho_body(response)[1])))


def _post(client: httpx.Client, payload: dict, token: str) -> httpx.Response:
    try:
        return client.post(
            f"{settings.zoho_mail_api_base}/api/accounts/{settings.zoho_mail_account_id}/messages",
            json=payload,
            headers={"Authorization": f"Zoho-oauthtoken {token}", "Accept": "application/json"},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise EmailTransientError(_cap(f"zoho_mail connect failed: {type(exc).__name__}")) from None
    except httpx.TransportError as exc:  # the request may have reached Zoho: outcome unknown, never retry (E9)
        raise EmailPermanentError(_cap(f"zoho_mail outcome unknown: {type(exc).__name__}")) from None


def send(msg: EmailMessage, *, client: httpx.Client | None = None) -> None:
    """Raises only EmailTransientError / EmailPermanentError."""
    payload = payload_from_message(msg)
    owned = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        token = _access_token(client)
        response = _post(client, payload, token)
        if response.status_code == 401:  # token revoked/expired early: refresh once and retry once
            _drop_token(token)
            response = _post(client, payload, _access_token(client))
        code = response.status_code
        if 200 <= code < 300:
            return
        # 504: the gateway may have accepted the message -> outcome unknown (E9); a 5.x.x SMTP refusal inside a 5xx is final (E10)
        if code >= 500 and code != 504 and not _smtp_refused(response):
            raise EmailTransientError(_error_text(response))
        raise EmailPermanentError(_error_text(response))  # incl. 504 (E9), 5xx + SMTP 5.x.x, 401 twice, 429 (E10), other 4xx
    finally:
        if owned:
            client.close()
