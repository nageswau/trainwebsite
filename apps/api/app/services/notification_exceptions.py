"""hrc-032 (DEC-SCOPE-412 N8-N10): the Delivery exceptions page -- recruitment notices whose delivery failed (retries exhausted, a permanent
error, or a worker that died mid-send) and failed recruiter emails (rec-026), with a manual retry.

Reads never return a notice's body or an email's subject: the type, the recipient's name, the channel, the error and the attempts are enough
to act on. Functions only; the route owns the transaction and publishes after its commit."""

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, literal, null, or_, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, CompanyContact, Notification, NotificationDelivery, RecruiterMessage, User
from app.notifications.dispatch import enqueue_recruiter_email, publish_all
from app.notifications.events import RECRUITMENT_EVENTS

ND = NotificationDelivery
RM = RecruiterMessage
EMAIL_TYPE = "recruiter.email"
TYPES = {**RECRUITMENT_EVENTS, EMAIL_TYPE: "Recruiter email"}
NOT_FOUND = "Failed notification not found"
NOT_FAILED = "This notification is no longer failed"
_URL = re.compile(r"https?://\S+")
_RECRUITMENT_NOTICE = select(Notification.id).where(Notification.event_type.in_(RECRUITMENT_EVENTS))
# Someone who must not be written to any more: an anonymised candidate (hrc-035), a contact marked do-not-contact (pob-005).
_REACHABLE = (or_(RM.candidate_id.is_(None), RM.candidate_id.in_(select(Candidate.id).where(Candidate.anonymised_at.is_(None)))),
              or_(RM.contact_id.is_(None), RM.contact_id.in_(select(CompanyContact.id).where(CompanyContact.status != "do_not_contact"))))  # fmt: skip


def _safe_error(error: str | None) -> str | None:
    """A webhook's error text quotes its URL, which can carry a token."""
    return _URL.sub("[link]", error) if error else None


async def page(db: AsyncSession, type_: str | None, channel: str | None, limit: int, offset: int) -> dict:
    """Newest failure first. An unknown type matches nothing."""
    deliveries = (
        select(literal("delivery").label("source"), ND.id.label("id"), Notification.event_type.label("type"), User.full_name.label("recipient"), ND.channel.label("channel"),
               ND.error.label("error"), ND.attempt_count.label("attempts"), ND.updated_at.label("failed_at"))
        .join(Notification, Notification.id == ND.notification_id)
        .join(User, User.id == Notification.user_id)
        .where(ND.status == "failed", Notification.event_type.in_(RECRUITMENT_EVENTS))
    )  # fmt: skip
    emails = (
        select(literal("email"), RM.id, literal(EMAIL_TYPE), func.coalesce(Candidate.name, CompanyContact.name), RM.channel, null(), RM.attempt_count, RM.updated_at)
        .outerjoin(Candidate, Candidate.id == RM.candidate_id)
        .outerjoin(CompanyContact, CompanyContact.id == RM.contact_id)
        .where(RM.channel == "email", RM.delivery_status == "failed", *_REACHABLE)
    )
    rows = union_all(deliveries, emails).subquery()
    wanted = [condition for condition in (rows.c.type == type_ if type_ else None, rows.c.channel == channel if channel else None) if condition is not None]
    total = await db.scalar(select(func.count()).select_from(rows).where(*wanted))
    found = await db.execute(select(rows).where(*wanted).order_by(rows.c.failed_at.desc(), rows.c.id).limit(limit).offset(offset))
    items = [{"source": r.source, "id": str(r.id), "type": r.type, "type_label": TYPES[r.type], "recipient": r.recipient, "channel": r.channel,
              "error": _safe_error(r.error), "attempts": r.attempts, "failed_at": r.failed_at} for r in found.all()]  # fmt: skip
    return {"items": items, "total": total, "limit": limit, "offset": offset, "types": [{"key": key, "label": label} for key, label in sorted(TYPES.items(), key=lambda kv: kv[1])]}


async def retry(db: AsyncSession, user: User, source: str, row_id: UUID) -> None:
    """N9: a fresh automatic cycle (`attempt_count` back to 0). Out of scope or missing: 404; no longer failed: 409, and the atomic UPDATE
    decides a race between two clicks."""
    if source == "delivery":
        moved = (await db.execute(
            update(ND).where(ND.id == row_id, ND.status == "failed", ND.notification_id.in_(_RECRUITMENT_NOTICE))
            .values(status="queued", attempt_count=0, error=None)
            .returning(literal(1))
        )).first()  # fmt: skip
        known = await db.scalar(select(ND.id).where(ND.id == row_id, ND.notification_id.in_(_RECRUITMENT_NOTICE)))
    else:
        moved = (await db.execute(
            update(RM).where(RM.id == row_id, RM.channel == "email", RM.delivery_status == "failed", *_REACHABLE)
            .values(delivery_status="queued", attempt_count=0)
            .returning(literal(1))
        )).first()  # fmt: skip
        known = await db.scalar(select(RM.id).where(RM.id == row_id, RM.channel == "email", *_REACHABLE))
    if known is None:
        raise HTTPException(404, NOT_FOUND)
    if moved is None:
        raise HTTPException(409, NOT_FAILED)
    db.add(AuditLog(user_id=user.id, action="notification.retry", entity_type=f"notification_{source}", entity_id=str(row_id), metadata_json={"source": source}))


def publish(source: str, row_id: UUID) -> None:
    """After the commit. A broker outage leaves the row queued for the stale sweepers."""
    if source == "delivery":
        publish_all([row_id], "exception_retry")
    else:
        enqueue_recruiter_email(row_id)
