"""rec-026 (DEC-SCOPE-135 MS7, AC2; spec §4): the worker side of a recruiter's email to a company contact or a candidate -- tel-014's
`lead_email` pattern on a `recruiter_messages` row (its SMTP classification `_send` and ENH-014's retry constants are reused; tel-014 itself
is untouched). Claim the row atomically (`queued`/`retrying` -> `sending`), so a duplicate task can never send twice; send with no
transaction open; record `sent`, `retrying` or `failed`. The address is the party's now (the tel-014 E7 rule). Logs carry the message id,
the status and the error type -- never an address, subject or body."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update

from app.core.database import SessionLocal
from app.models import Candidate, CompanyContact, RecruiterMessage, User
from app.notifications.delivery import CLAIMABLE, MAX_ATTEMPTS, RETRY_COUNTDOWNS, STALE_QUEUED, STALE_SENDING
from app.notifications.dispatch import enqueue_recruiter_email
from app.notifications.lead_email import _send

logger = logging.getLogger(__name__)

RM = RecruiterMessage
EMAIL = RM.channel == "email"


async def deliver_recruiter_email(message_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(RM)
                .where(RM.id == message_id, EMAIL, RM.delivery_status.in_(CLAIMABLE))
                .values(delivery_status="sending", attempt_count=RM.attempt_count + 1)
                .returning(RM.attempt_count, RM.sender_user_id, RM.subject, RM.body)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        attempt, sender_id, subject, body = claimed
        to_email = await db.scalar(  # the party's address now: exactly one of the joins matches (ck_recruiter_messages_party)
            select(func.coalesce(CompanyContact.email, Candidate.email))
            .select_from(RM)
            .outerjoin(CompanyContact, CompanyContact.id == RM.contact_id)
            .outerjoin(Candidate, Candidate.id == RM.candidate_id)
            .where(RM.id == message_id)
        )
        sender_name, sender_email = (await db.execute(select(User.full_name, User.email).where(User.id == sender_id))).one()  # FK RESTRICT
        await db.commit()  # end the read transaction before sending

    status, error_type = await _send(to_email, subject or "", body, sender_name, sender_email)  # ck_recruiter_messages_email: never empty
    if status == "retry":
        status = "retrying" if attempt < MAX_ATTEMPTS else "failed"
    async with SessionLocal() as db:
        await db.execute(update(RM).where(RM.id == message_id, RM.delivery_status == "sending").values(delivery_status=status))  # the sweeper may have given up
        await db.commit()
    if status == "retrying":
        enqueue_recruiter_email(message_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("recruiter_email_delivery", extra={"extra_fields": {"message_id": str(message_id), "status": status, "attempt": attempt, "error_type": error_type}})
    return status


async def sweep_stale_recruiter_emails(now: datetime | None = None) -> dict[str, int]:
    """Republish queued/retrying emails nobody picked up (touching `updated_at`); a row stuck in `sending` has an unknown outcome, so it is
    failed, never resent -- a duplicate email to a company contact is worse than a visible failure."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (await db.scalars(update(RM).where(EMAIL, RM.delivery_status.in_(CLAIMABLE), RM.updated_at < now - STALE_QUEUED).values(updated_at=now).returning(RM.id))).all()
        interrupted = (await db.scalars(update(RM).where(EMAIL, RM.delivery_status == "sending", RM.updated_at < now - STALE_SENDING).values(delivery_status="failed").returning(RM.id))).all()
        await db.commit()
    for message_id in requeue:
        if not enqueue_recruiter_email(message_id):  # the broker is down: the next sweep retries the rest
            break
    counts = {"requeued": len(requeue), "interrupted": len(interrupted)}
    logger.info("recruiter_email_sweep", extra={"extra_fields": counts})
    return counts
