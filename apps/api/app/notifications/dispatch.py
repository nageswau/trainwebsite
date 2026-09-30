"""ENH-014 (spec §6.1): queue a notification's deliveries; publish them to Celery only after the business write commits.

`queue_deliveries` writes one `queued` NotificationDelivery per allowed channel (email always; WhatsApp/SMS only when the
recipient opted in -- D4) and remembers the ids on the session. The `after_commit` listener publishes them; a rollback
discards them, so a rolled-back write never sends anything and the worker never looks for an uncommitted row. Only the
ROOT transaction's end counts: a SAVEPOINT release or rollback leaves the pending list untouched, so an id queued inside
a rolled-back SAVEPOINT may still be published at the root commit; the worker's claim then finds no row and exits,
which is harmless."""

import logging
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Notification, NotificationDelivery, NotificationPreference, User

logger = logging.getLogger(__name__)

PENDING_KEY = "enh014_pending_deliveries"


async def queue_deliveries(db: AsyncSession, notification: Notification, recipient: User, *, context: dict | None = None, channels: list[str] | None = None) -> list[NotificationDelivery]:
    """`channels` (admin /communications/notify only) narrows the allowed set; it can never add an un-opted-in channel."""
    await db.flush()  # the notification needs its id
    pref = await db.get(NotificationPreference, recipient.id)
    allowed = ["email"] + [c for c, on in (("whatsapp", pref and pref.whatsapp_opt_in), ("sms", pref and pref.sms_opt_in)) if on]
    chosen = allowed if channels is None else [c for c in allowed if c in channels]
    rows = [NotificationDelivery(notification_id=notification.id, channel=c, status="queued", attempt_count=0, context=context) for c in chosen]
    db.add_all(rows)
    await db.flush()
    db.sync_session.info.setdefault(PENDING_KEY, []).extend(r.id for r in rows)
    return rows


@event.listens_for(Session, "after_commit")
def _publish_when_root_commits(session: Session) -> None:
    """SQLAlchemy also dispatches this for a SAVEPOINT release, when the session is still inside the savepoint."""
    if not session.in_nested_transaction():
        for delivery_id in session.info.pop(PENDING_KEY, []):
            enqueue(delivery_id)


@event.listens_for(Session, "after_rollback")
def _discard_when_root_rolls_back(session: Session) -> None:
    """Also dispatched per SAVEPOINT; a root rollback with a savepoint open dispatches once for the savepoint (still
    nested) and once more for the root, which is the one that discards."""
    if not session.in_nested_transaction():
        session.info.pop(PENDING_KEY, None)


def enqueue(delivery_id: UUID | str, countdown: int = 0) -> None:
    """Never raises: a broker outage must not fail the request that already committed. The row stays queued/retrying and
    the stale sweeper (delivery.sweep_stale_deliveries) publishes it again."""
    try:
        _publish(str(delivery_id), countdown)
    except Exception as exc:  # noqa: BLE001 -- see docstring
        logger.warning("notification_enqueue_failed", extra={"extra_fields": {"delivery_id": str(delivery_id), "error_type": type(exc).__name__}})


def _publish(delivery_id: str, countdown: int) -> None:
    from app.worker import deliver_notification_task  # noqa: PLC0415 -- the worker module imports this package

    # retry=False: fail fast instead of blocking the request in Celery's publish-retry loop when Redis is down.
    deliver_notification_task.apply_async((delivery_id,), countdown=countdown, retry=False)
