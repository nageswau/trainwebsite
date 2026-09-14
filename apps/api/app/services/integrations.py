import httpx

from app.core.config import settings


async def post_optional_webhook(url: str | None, payload: dict) -> tuple[str, str | None]:
    if not url:
        return "not_configured", None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json=payload)
            r.raise_for_status()
        return "sent", None
    except Exception as exc:
        return "failed", str(exc)[:500]


async def sync_crm_enquiry(payload: dict) -> str:
    status, _ = await post_optional_webhook(settings.crm_webhook_url, payload)
    return status


async def send_notification(channel: str, payload: dict) -> tuple[str, str | None]:
    """Returns (status, error). NOT-001-AC02: a failed send is never silently dropped --
    callers persist both the status and the real error detail on `NotificationDelivery`.
    The retry *policy* (attempt count/backoff) is open (`PRD_OPEN_ITEMS.md` item 13) and
    is not invented here; only the failure reason is captured."""
    url = {"whatsapp": settings.whatsapp_webhook_url, "sms": settings.sms_webhook_url, "email": settings.email_webhook_url}.get(channel)
    return await post_optional_webhook(url, payload)
