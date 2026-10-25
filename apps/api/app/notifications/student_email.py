"""ccrm-037 (DEC-SCOPE-271 MT6): the worker side of a counselor's email to a student -- upc-012's `university_email` pattern on a
`student_messages` row (tel-014's SMTP classification `_send` and ENH-014's retry constants are reused). Claim the row atomically
(`queued`/`retrying` -> `sending`), so a duplicate task can never send twice; send with no transaction open; record `sent`, `retrying` or
`failed`. The address is the student's account email at send time. Logs carry the message id, the status and the error type -- never an
address, subject or body."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import StudentMessage, User
from app.notifications.delivery import CLAIMABLE, MAX_ATTEMPTS, RETRY_COUNTDOWNS, STALE_QUEUED, STALE_SENDING
from app.notifications.dispatch import enqueue_student_email
from app.notifications.lead_email import _send

logger = logging.getLogger(__name__)

SM = StudentMessage
EMAIL = SM.channel == "email"


async def deliver_student_email(message_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(SM)
                .where(SM.id == message_id, EMAIL, SM.delivery_status.in_(CLAIMABLE))
                .values(delivery_status="sending", attempt_count=SM.attempt_count + 1)
                .returning(SM.attempt_count, SM.sender_user_id, SM.student_user_id, SM.subject, SM.body)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        attempt, sender_id, student_id, subject, body = claimed
        to_email = await db.scalar(select(User.email).where(User.id == student_id))  # FK RESTRICT: the student exists
        sender_name, sender_email = (await db.execute(select(User.full_name, User.email).where(User.id == sender_id))).one()
        await db.commit()  # end the read transaction before sending

    status, error_type = await _send(to_email, subject or "", body, sender_name, sender_email)  # ck_student_messages_outbound_email: never empty
    if status == "retry":
        status = "retrying" if attempt < MAX_ATTEMPTS else "failed"
    async with SessionLocal() as db:
        await db.execute(update(SM).where(SM.id == message_id, SM.delivery_status == "sending").values(delivery_status=status))  # the sweeper may have given up
        await db.commit()
    if status == "retrying":
        enqueue_student_email(message_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("student_email_delivery", extra={"extra_fields": {"message_id": str(message_id), "status": status, "attempt": attempt, "error_type": error_type}})
    return status


async def sweep_stale_student_emails(now: datetime | None = None) -> dict[str, int]:
    """Republish queued/retrying emails nobody picked up (touching `updated_at`); a row stuck in `sending` has an unknown outcome, so it is
    failed, never resent -- a duplicate email to a student is worse than a visible failure."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (await db.scalars(update(SM).where(EMAIL, SM.delivery_status.in_(CLAIMABLE), SM.updated_at < now - STALE_QUEUED).values(updated_at=now).returning(SM.id))).all()
        interrupted = (await db.scalars(update(SM).where(EMAIL, SM.delivery_status == "sending", SM.updated_at < now - STALE_SENDING).values(delivery_status="failed").returning(SM.id))).all()
        await db.commit()
    for message_id in requeue:
        if not enqueue_student_email(message_id):  # the broker is down: the next sweep retries the rest
            break
    counts = {"requeued": len(requeue), "interrupted": len(interrupted)}
    logger.info("student_email_sweep", extra={"extra_fields": counts})
    return counts
