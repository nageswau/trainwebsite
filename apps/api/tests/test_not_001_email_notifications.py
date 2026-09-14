"""NOT-001 -- Email notifications.

The main workflow (status-change events trigger email) already existed broadly across the
codebase via `_notify_user` (enrollment, assignments, certificates, placements, etc.). The
real gap was AC02: `send_notification` swallowed the actual failure reason
(`except Exception: return "failed"`), so `NotificationDelivery.error` was never populated
even though the column existed -- and `auth.forgot_password` discarded the send result
entirely, creating no delivery record at all. That is a literal silent drop. Fixed both;
added `NotificationDelivery.attempt_count` as the retry-eligible-state mechanism required by
DATA_MODEL.md #7.1. The retry *policy* itself (count/backoff) stays open
(`PRD_OPEN_ITEMS.md` item 13) and is not invented here -- no automatic retry job is added.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Notification, NotificationDelivery, User


async def _create_user(db_session) -> User:
    user = User(
        email=f"not001-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Notify Me",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_forgot_password_creates_a_notification_delivery_record(db_session, client, monkeypatch):
    import app.api.auth as auth_module

    async def fake_send(channel, payload):
        return "sent", None

    monkeypatch.setattr(auth_module, "send_notification", fake_send)
    user = await _create_user(db_session)

    response = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert response.status_code == 202

    notification = await db_session.scalar(select_notification_for(user.id))
    assert notification is not None
    delivery = await db_session.scalar(select_delivery_for(notification.id))
    assert delivery is not None
    assert delivery.status == "sent"
    assert delivery.error is None


@pytest.mark.asyncio
async def test_failed_send_captures_the_real_error_never_silently_dropped(db_session, client, monkeypatch):
    import app.api.auth as auth_module

    async def fake_send(channel, payload):
        return "failed", "Connection timed out after 10s"

    monkeypatch.setattr(auth_module, "send_notification", fake_send)
    user = await _create_user(db_session)

    response = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert response.status_code == 202

    notification = await db_session.scalar(select_notification_for(user.id))
    delivery = await db_session.scalar(select_delivery_for(notification.id))
    assert delivery.status == "failed"
    assert delivery.error == "Connection timed out after 10s"


@pytest.mark.asyncio
async def test_notification_delivery_attempt_count_defaults_to_one(db_session):
    user = await _create_user(db_session)
    notification = Notification(user_id=user.id, title="Test", body="Test body", read=False)
    db_session.add(notification)
    await db_session.flush()
    delivery = NotificationDelivery(notification_id=notification.id, channel="email", status="sent")
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.attempt_count == 1


@pytest.mark.asyncio
async def test_send_notification_returns_error_detail_on_webhook_failure(monkeypatch):
    from app.core.config import settings
    from app.services.integrations import send_notification

    monkeypatch.setattr(settings, "email_webhook_url", "http://127.0.0.1:1/unreachable")
    status, error = await send_notification("email", {"to": "a@b.com"})

    assert status == "failed"
    assert error is not None and len(error) > 0


@pytest.mark.asyncio
async def test_send_notification_reports_not_configured_without_raising(monkeypatch):
    from app.core.config import settings
    from app.services.integrations import send_notification

    monkeypatch.setattr(settings, "email_webhook_url", None)
    status, error = await send_notification("email", {"to": "a@b.com"})

    assert status == "not_configured"
    assert error is None


def select_notification_for(user_id):
    from sqlalchemy import select

    return select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())


def select_delivery_for(notification_id):
    from sqlalchemy import select

    return select(NotificationDelivery).where(NotificationDelivery.notification_id == notification_id)
