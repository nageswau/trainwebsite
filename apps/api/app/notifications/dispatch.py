"""ENH-014 (spec §6.1): queue a notification's deliveries; publish them to Celery only after the business write commits.

`queue_deliveries` writes one `queued` NotificationDelivery per allowed channel (email always; WhatsApp/SMS only when the
recipient opted in -- D4) and remembers the ids on the session. The `after_commit` listener publishes them; a rollback
discards them, so a rolled-back write never sends anything and the worker never looks for an uncommitted row. Only the
ROOT transaction's end counts: a SAVEPOINT release or rollback leaves the pending list untouched, so an id queued inside
a rolled-back SAVEPOINT may still be published at the root commit; the worker's claim then finds no row and exits,
which is harmless."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
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
        publish_all(session.info.pop(PENDING_KEY, []), "after_commit")


def publish_all(delivery_ids: list, source: str) -> None:
    """Publish in order and stop at the first broker failure: this runs synchronously (for the after-commit path, inside
    `await db.commit()` on the event loop), so trying every id against a dead broker would stall the process once per
    delivery. The unpublished rows stay queued/retrying for the stale sweeper."""
    for index, delivery_id in enumerate(delivery_ids):
        if not enqueue(delivery_id):
            skipped = len(delivery_ids) - index - 1
            if skipped:
                logger.warning("notification_enqueue_skipped", extra={"extra_fields": {"source": source, "skipped": skipped}})
            return


@event.listens_for(Session, "after_rollback")
def _discard_when_root_rolls_back(session: Session) -> None:
    """Also dispatched per SAVEPOINT; a root rollback with a savepoint open dispatches once for the savepoint (still
    nested) and once more for the root, which is the one that discards."""
    if not session.in_nested_transaction():
        session.info.pop(PENDING_KEY, None)


# QAF-01: the socket timeouts below don't cover resolving the broker's hostname (~4-8 s when DNS for `redis` fails), and
# this runs on the event loop, so the wait itself is bounded. A publish still running after the wait is harmless: the
# worker's atomic claim dedupes it. After any failure, publishing is skipped for BROKER_BACKOFF_SECONDS so an outage
# costs one bounded wait per back-off window, not one per request; the stale sweeper delivers the skipped rows.
PUBLISH_WAIT_SECONDS = 1.5
BROKER_BACKOFF_SECONDS = 30
_publisher = ThreadPoolExecutor(max_workers=1, thread_name_prefix="enh014-publish")
_broker_unavailable_until: float = 0.0  # time.monotonic() deadline; 0.0 = broker assumed available


def enqueue(delivery_id: UUID | str, countdown: int = 0) -> bool:
    """Never raises: a broker outage must not fail the request that already committed. The row stays queued/retrying and
    the stale sweeper (delivery.sweep_stale_deliveries) publishes it again. Returns False when the publish failed, timed
    out, or was skipped because the broker failed within the last BROKER_BACKOFF_SECONDS."""
    # `_publish` is looked up at call time (tests replace it).
    return _submit(lambda: _publish(str(delivery_id), countdown), delivery_id)


def enqueue_lead_email(message_id: UUID | str, countdown: int = 0) -> bool:
    """tel-014 (DEC-SCOPE-104 E4): publish a queued lead email (a `lead_messages` row) with `enqueue`'s bounded wait and shared back-off. A
    failure leaves the row queued/retrying for `lead_email.sweep_stale_lead_emails`."""
    return _submit(lambda: _publish_lead_email(str(message_id), countdown), message_id)


def _submit(publish, ref) -> bool:
    global _broker_unavailable_until  # noqa: PLW0603 -- process-wide back-off state
    if time.monotonic() < _broker_unavailable_until:
        return False
    try:
        # A publisher thread busy with a hung publish times out too.
        _publisher.submit(publish).result(timeout=PUBLISH_WAIT_SECONDS)
    except Exception as exc:  # noqa: BLE001 -- see enqueue; includes the wait's TimeoutError
        _broker_unavailable_until = time.monotonic() + BROKER_BACKOFF_SECONDS
        logger.warning("notification_enqueue_failed", extra={"extra_fields": {"delivery_id": str(ref), "error_type": type(exc).__name__}})
        return False
    return True


# Applied only to the publish connection, so the worker's consumer connection keeps the global broker settings. Without
# socket_connect_timeout a dead Redis blocks each publish for ~6 s (refused) to ~21 s (unreachable host).
PUBLISH_TRANSPORT_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1, "max_retries": 0}


def _publish(delivery_id: str, countdown: int) -> None:
    from app.worker import celery, deliver_notification_task  # noqa: PLC0415 -- the worker module imports this package

    # retry=False: no publish-retry loop. ignore_result=True: nothing reads this task's result, and registering interest in
    # it first makes the Redis result backend reconnect (~19 s when refused, unbounded when the host is unreachable).
    with celery.connection_for_write(transport_options=PUBLISH_TRANSPORT_OPTIONS) as conn:
        deliver_notification_task.apply_async((delivery_id,), countdown=countdown, retry=False, ignore_result=True, connection=conn)


def _publish_lead_email(message_id: str, countdown: int) -> None:
    from app.worker import celery, deliver_lead_email_task  # noqa: PLC0415 -- the worker module imports this package

    with celery.connection_for_write(transport_options=PUBLISH_TRANSPORT_OPTIONS) as conn:
        deliver_lead_email_task.apply_async((message_id,), countdown=countdown, retry=False, ignore_result=True, connection=conn)
