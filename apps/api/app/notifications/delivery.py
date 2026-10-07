"""ENH-014 (spec §6.5): the worker side. Claim one queued delivery atomically, send it on its channel, record the outcome,
and re-enqueue transient failures with the D11 countdowns. The row -- not the broker -- is the source of truth, so a
duplicate task, a redelivered message or a concurrent worker can never send twice (the claim lets exactly one through)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications import twilio
from app.notifications.dispatch import enqueue, publish_all
from app.notifications.phone import normalise_phone
from app.services.integrations import send_notification
from app.services.mailer import send_bdm_reminder_email, send_parent_notification_email

logger = logging.getLogger(__name__)

RETRY_COUNTDOWNS = {1: 60, 2: 300, 3: 1500}  # seconds, after failed attempt n (D11)
MAX_ATTEMPTS = 4  # the first try plus three retries
CLAIMABLE = ("queued", "retrying")


@dataclass(frozen=True)
class _Snapshot:
    """Plain values read before any network call, so no transaction is held open while a provider is slow."""

    title: str
    body: str
    action_url: str | None
    email: str
    full_name: str
    phone: str | None
    active: bool
    whatsapp_opt_in: bool
    sms_opt_in: bool


async def deliver(delivery_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id, NotificationDelivery.status.in_(CLAIMABLE))
                .values(status="sending", attempt_count=NotificationDelivery.attempt_count + 1)
                .returning(NotificationDelivery.channel, NotificationDelivery.notification_id, NotificationDelivery.attempt_count, NotificationDelivery.context)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        channel, notification_id, attempt, context = claimed
        snapshot = await _snapshot(db, notification_id)
        await db.commit()  # end the read transaction before sending

    try:
        result = await _send(channel, snapshot, context)
    except Exception as exc:  # an unexpected sender error must never leave the row stuck in 'sending'
        logger.error("notification_delivery_send_error", extra={"extra_fields": {"delivery_id": str(delivery_id), "error_type": type(exc).__name__}})
        result = twilio.SendResult("failed", error=f"unexpected {type(exc).__name__}", transient=False)
    status = "retrying" if result.status == "failed" and result.transient and attempt < MAX_ATTEMPTS else result.status
    async with SessionLocal() as db:
        await db.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id, NotificationDelivery.status == "sending")  # the sweeper may have given up on it
            .values(status=status, error=result.error[:500] if result.error else None, provider_reference=result.provider_reference, sent_at=datetime.now(UTC) if status == "sent" else None)
        )
        await db.commit()
    if status == "retrying":
        enqueue(delivery_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("notification_delivery", extra={"extra_fields": {"delivery_id": str(delivery_id), "channel": channel, "status": status, "attempt": attempt}})
    return status


async def _snapshot(db, notification_id: UUID) -> _Snapshot | None:
    note = await db.get(Notification, notification_id)
    user = await db.get(User, note.user_id) if note else None
    if note is None or user is None:
        return None
    pref = await db.get(NotificationPreference, user.id)
    return _Snapshot(note.title, note.body, note.action_url, user.email, user.full_name, user.phone, bool(user.active), bool(pref and pref.whatsapp_opt_in), bool(pref and pref.sms_opt_in))


async def _send(channel: str, s: _Snapshot | None, context: dict | None) -> twilio.SendResult:
    if s is None or not s.active:
        return twilio.SendResult("skipped", error="recipient unavailable")
    if channel == "email":
        return await _send_email(s, context)
    if not (s.whatsapp_opt_in if channel == "whatsapp" else s.sms_opt_in):
        return twilio.SendResult("skipped", error="opted_out")
    phone = normalise_phone(s.phone)
    if phone is None:
        return twilio.SendResult("failed", error="invalid_phone")
    if twilio.configured(channel):
        send = twilio.send_whatsapp if channel == "whatsapp" else twilio.send_sms
        return await send(phone, s.title, s.body, s.action_url)
    status, error = await send_notification(channel, {"to": s.email, "phone": phone, "title": s.title, "body": s.body, "action_url": s.action_url})
    return twilio.SendResult(status, error=error, transient=status == "failed")


async def _send_email(s: _Snapshot, context: dict | None) -> twilio.SendResult:
    """Exactly the email paths that existed inline before ENH-014 (AC12): school SMTP (webhook fallback), inbound's webhook
    payload without the phone, and _notify_user's webhook payload with it."""
    if context and context.get("kind") == "school":
        status, error = await send_parent_notification_email(to_email=s.email, recipient_name=s.full_name, school_name=context.get("school_name") or "your school", title=s.title, body=s.body, action_url=s.action_url)
        if status == "not_configured":
            status, error = await send_notification("email", {"to": s.email, "title": s.title, "body": s.body, "action_url": s.action_url})
    elif context and context.get("kind") == "bdm_reminder":  # bdm-012 (DEC-SCOPE-102 R9): SMTP only; not_configured stays recorded
        status, error = await send_bdm_reminder_email(to_email=s.email, recipient_name=s.full_name, title=s.title, body=s.body, links=context.get("links") or [])
    elif context and context.get("kind") == "inbound":  # inbound._notify_student never sent the phone
        status, error = await send_notification("email", {"to": s.email, "title": s.title, "body": s.body, "action_url": s.action_url})
    else:
        status, error = await send_notification("email", {"to": s.email, "phone": s.phone, "title": s.title, "body": s.body, "action_url": s.action_url})
    return twilio.SendResult(status, error=error, transient=status == "failed")


STALE_QUEUED = timedelta(minutes=30)  # longer than the largest retry countdown (25 min)
STALE_SENDING = timedelta(minutes=15)


async def sweep_stale_deliveries(now: datetime | None = None) -> dict[str, int]:
    """Publish queued/retrying rows nobody picked up (broker outage, lost message) again, touching `updated_at` so the
    next sweep does not re-publish them at once; a duplicate publish is harmless because the claim lets one through.
    A row stuck in `sending` has an unknown outcome (the worker died mid-send): it is failed, never resent -- Twilio has
    no idempotency key, and a duplicate message to a parent is worse than a missed copy (email and in-app remain)."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (
            await db.scalars(
                update(NotificationDelivery)
                .where(NotificationDelivery.status.in_(CLAIMABLE), NotificationDelivery.updated_at < now - STALE_QUEUED)
                .values(updated_at=now)
                .returning(NotificationDelivery.id)
            )
        ).all()
        interrupted = (
            await db.scalars(
                update(NotificationDelivery)
                .where(NotificationDelivery.status == "sending", NotificationDelivery.updated_at < now - STALE_SENDING)
                .values(status="failed", error="worker interrupted")
                .returning(NotificationDelivery.id)
            )
        ).all()
        await db.commit()
    publish_all(list(requeue), "sweeper")  # stops at the first broker failure; the next sweep retries the rest
    counts = {"requeued": len(requeue), "interrupted": len(interrupted)}
    logger.info("notification_sweep", extra={"extra_fields": counts})
    return counts
