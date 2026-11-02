"""itc-002 (DEC-SCOPE-336): typed notifications that link to a record.

`EVENTS` is the catalogue: each dotted event type names the record it is about and carries FIXED, preview-safe text. `notify` takes
no free text, so an amount, score, note or HR comment can never reach an in-app preview, an email subject or a WhatsApp/SMS line
(source §7, last line); the recipient opens EduSphere for the detail. The catalogue rows other than `it.fee.payment_received` are
`NEEDS_CONFIRMATION` against the source's §7 table: the item that first emits each one (itc-009/016/023/025/026/027) confirms it.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications.dispatch import NOTIFIED_KEY, add_pending, allowed_channels

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    entity_type: str
    title: str
    body: str


EVENTS: dict[str, Event] = {
    "it.lead.assigned": Event("lead", "New lead assigned", "A lead was handed over to you. Open EduSphere to view it."),
    "it.followup.overdue": Event("lead_follow_up", "Follow-up overdue", "A follow-up is past its due time. Open EduSphere to act on it."),
    "it.fee.payment_received": Event("payment", "Payment received", "Your payment was received. Open EduSphere to view your receipt."),
    "it.fee.payment_due": Event("payment", "Fee payment due", "A fee payment is due. Open EduSphere for the details."),
    "it.batch.changed": Event("batch", "Course or batch updated", "Your course, batch or timetable was updated. Open EduSphere to see what changed."),
    "it.training.at_risk": Event("enrollment", "Attendance or progress alert", "Attendance or progress needs attention. Open EduSphere for the details."),
    "it.resume.uploaded": Event("resume", "Resume uploaded", "A resume was uploaded. Open EduSphere to review it."),
    "it.placement.updated": Event("student", "Placement status updated", "Your placement status was updated. Open EduSphere to see it."),
}


async def notify(db: AsyncSession, recipients: Iterable[User | None], event_type: str, entity_id: UUID | str, *, action_url: str | None = None) -> list[Notification]:
    """One in-app notice per recipient plus queued email and opted-in WhatsApp/SMS, published only when the caller's transaction
    commits (a rollback sends nothing). Missing and deactivated recipients are skipped, and a (recipient, event, record) already
    notified in this transaction is not notified again. Bulk: one insert per table and one preference query for the whole batch."""
    event = EVENTS.get(event_type)
    if event is None:
        raise ValueError(f"Unknown notification event: {event_type}")
    entity = str(entity_id)
    seen: set = db.sync_session.info.setdefault(NOTIFIED_KEY, set())
    targets: list[User] = []
    for user in recipients:
        if user is None or not user.active or (key := (user.id, event_type, entity)) in seen:
            continue
        seen.add(key)
        targets.append(user)
    if not targets:
        return []
    notes = [Notification(user_id=u.id, title=event.title, body=event.body, read=False, action_url=action_url, event_type=event_type, entity_type=event.entity_type, entity_id=entity) for u in targets]
    db.add_all(notes)
    await db.flush()
    prefs = {p.user_id: p for p in await db.scalars(select(NotificationPreference).where(NotificationPreference.user_id.in_([u.id for u in targets])))}
    await add_pending(db, [NotificationDelivery(notification_id=n.id, channel=c, status="queued", attempt_count=0) for n in notes for c in allowed_channels(prefs.get(n.user_id))])
    logger.info("notification_event_queued", extra={"extra_fields": {"event_type": event_type, "entity_type": event.entity_type, "recipients": len(notes)}})
    return notes
