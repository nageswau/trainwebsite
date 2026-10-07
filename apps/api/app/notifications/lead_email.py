"""tel-014 (DEC-SCOPE-106 E4-E7, E10; spec §4): the worker side of a telecaller's email to a lead -- ENH-014's delivery pattern on a
`lead_messages` row. Claim the row atomically (`queued`/`retrying` -> `sending`), so a duplicate task, a redelivered message or a
concurrent worker can never send twice; send through the existing SMTP mailer with no transaction open; record `sent`, `retrying` (re-enqueued
with the D11 countdowns) or `failed`. Logs carry the message id, the status and the error type -- never an address, subject or body."""

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import Enquiry, LeadMessage, User
from app.notifications.delivery import CLAIMABLE, MAX_ATTEMPTS, RETRY_COUNTDOWNS, STALE_QUEUED, STALE_SENDING
from app.notifications.dispatch import enqueue_lead_email
from app.services import mailer

logger = logging.getLogger(__name__)

EMAIL = LeadMessage.channel == "email"


async def deliver_lead_email(message_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(LeadMessage)
                .where(LeadMessage.id == message_id, EMAIL, LeadMessage.delivery_status.in_(CLAIMABLE))
                .values(delivery_status="sending", attempt_count=LeadMessage.attempt_count + 1)
                .returning(LeadMessage.attempt_count, LeadMessage.lead_id, LeadMessage.sender_user_id, LeadMessage.subject, LeadMessage.body)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        attempt, lead_id, sender_id, subject, body = claimed
        to_email = await db.scalar(select(Enquiry.email).where(Enquiry.id == lead_id))  # E7: the lead's address now
        sender_name, sender_email = (await db.execute(select(User.full_name, User.email).where(User.id == sender_id))).one()  # FK RESTRICT
        await db.commit()  # end the read transaction before sending

    status, error_type = await _send(to_email, subject or "", body, sender_name, sender_email)  # ck_lead_messages_email: never empty
    if status == "retry":
        status = "retrying" if attempt < MAX_ATTEMPTS else "failed"
    async with SessionLocal() as db:
        await db.execute(
            update(LeadMessage)
            .where(LeadMessage.id == message_id, LeadMessage.delivery_status == "sending")  # the sweeper may have given up
            .values(delivery_status=status)
        )
        await db.commit()
    if status == "retrying":
        enqueue_lead_email(message_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("lead_email_delivery", extra={"extra_fields": {"message_id": str(message_id), "status": status, "attempt": attempt, "error_type": error_type}})
    return status


async def _send(to_email: str | None, subject: str, body: str, sender_name: str, sender_email: str) -> tuple[str, str | None]:
    """("sent" | "retry" | "failed", error type). Transient: the connection, a timeout, an SMTP 4xx. Permanent: a 5xx, a refused recipient,
    a malformed address, SMTP unset since the request (E3) or the lead's address removed (E7)."""
    if not mailer.smtp_configured():
        return "failed", "not_configured"
    if not to_email:
        return "failed", "no_address"
    try:
        msg = mailer.lead_email_message(to_email=to_email, subject=subject, body=body, sender_name=sender_name, sender_email=sender_email)
        await asyncio.to_thread(mailer._send_sync, msg)
    except smtplib.SMTPRecipientsRefused as exc:
        return "failed", type(exc).__name__
    except smtplib.SMTPResponseException as exc:
        return ("retry" if exc.smtp_code < 500 else "failed"), type(exc).__name__
    except (OSError, smtplib.SMTPException) as exc:  # connection refused/reset, timeouts, a dropped server
        return "retry", type(exc).__name__
    except Exception as exc:  # noqa: BLE001 -- a malformed address (ValueError) or anything unexpected must never leave the row 'sending'
        return "failed", type(exc).__name__
    return "sent", None


async def sweep_stale_lead_emails(now: datetime | None = None) -> dict[str, int]:
    """E5, as `delivery.sweep_stale_deliveries`: republish queued/retrying emails nobody picked up (touching `updated_at`); a row stuck in
    `sending` has an unknown outcome, so it is failed, never resent -- a duplicate email to a lead is worse than a visible failure."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (
            await db.scalars(update(LeadMessage).where(EMAIL, LeadMessage.delivery_status.in_(CLAIMABLE), LeadMessage.updated_at < now - STALE_QUEUED).values(updated_at=now).returning(LeadMessage.id))
        ).all()
        interrupted = (
            await db.scalars(
                update(LeadMessage).where(EMAIL, LeadMessage.delivery_status == "sending", LeadMessage.updated_at < now - STALE_SENDING).values(delivery_status="failed").returning(LeadMessage.id)
            )
        ).all()
        await db.commit()
    for message_id in requeue:
        if not enqueue_lead_email(message_id):  # the broker is down: the next sweep retries the rest
            break
    counts = {"requeued": len(requeue), "interrupted": len(interrupted)}
    logger.info("lead_email_sweep", extra={"extra_fields": counts})
    return counts
