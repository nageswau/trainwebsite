"""upc-012 (DEC-SCOPE-139 UC7, AC1; spec §4): the worker side of a partnership manager's email to a university contact -- rec-026's
`recruiter_email` pattern on a `university_messages` row (tel-014's SMTP classification `_send` and ENH-014's retry constants are reused;
tel-014 and rec-026 are untouched). Claim the row atomically (`queued`/`retrying` -> `sending`), so a duplicate task can never send twice;
send with no transaction open; record `sent`, `retrying` or `failed`. The address is the contact's now; a deleted contact (UC2) fails as
`no_address`. Logs carry the message id, the status and the error type -- never an address, subject or body."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import UniversityContact, UniversityMessage, User
from app.notifications.delivery import CLAIMABLE, MAX_ATTEMPTS, RETRY_COUNTDOWNS, STALE_QUEUED, STALE_SENDING
from app.notifications.dispatch import enqueue_university_email
from app.notifications.lead_email import _send

logger = logging.getLogger(__name__)

UM = UniversityMessage
EMAIL = UM.channel == "email"


async def deliver_university_email(message_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(UM)
                .where(UM.id == message_id, EMAIL, UM.delivery_status.in_(CLAIMABLE))
                .values(delivery_status="sending", attempt_count=UM.attempt_count + 1)
                .returning(UM.attempt_count, UM.sender_user_id, UM.contact_id, UM.subject, UM.body)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        attempt, sender_id, contact_id, subject, body = claimed
        to_email = await db.scalar(select(UniversityContact.email).where(UniversityContact.id == contact_id)) if contact_id else None
        sender_name, sender_email = (await db.execute(select(User.full_name, User.email).where(User.id == sender_id))).one()  # FK RESTRICT
        await db.commit()  # end the read transaction before sending

    status, error_type = await _send(to_email, subject or "", body, sender_name, sender_email)  # ck_university_messages_email: never empty
    if status == "retry":
        status = "retrying" if attempt < MAX_ATTEMPTS else "failed"
    async with SessionLocal() as db:
        await db.execute(update(UM).where(UM.id == message_id, UM.delivery_status == "sending").values(delivery_status=status))  # the sweeper may have given up
        await db.commit()
    if status == "retrying":
        enqueue_university_email(message_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("university_email_delivery", extra={"extra_fields": {"message_id": str(message_id), "status": status, "attempt": attempt, "error_type": error_type}})
    return status


async def sweep_stale_university_emails(now: datetime | None = None) -> dict[str, int]:
    """Republish queued/retrying emails nobody picked up (touching `updated_at`); a row stuck in `sending` has an unknown outcome, so it is
    failed, never resent -- a duplicate email to a university contact is worse than a visible failure."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (await db.scalars(update(UM).where(EMAIL, UM.delivery_status.in_(CLAIMABLE), UM.updated_at < now - STALE_QUEUED).values(updated_at=now).returning(UM.id))).all()
        interrupted = (await db.scalars(update(UM).where(EMAIL, UM.delivery_status == "sending", UM.updated_at < now - STALE_SENDING).values(delivery_status="failed").returning(UM.id))).all()
        await db.commit()
    for message_id in requeue:
        if not enqueue_university_email(message_id):  # the broker is down: the next sweep retries the rest
            break
    counts = {"requeued": len(requeue), "interrupted": len(interrupted)}
    logger.info("university_email_sweep", extra={"extra_fields": counts})
    return counts
