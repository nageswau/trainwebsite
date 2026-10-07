"""bdm-012 (DEC-SCOPE-098 R9, AC5) -- the BDM reminder email: SMTP only (never the webhook), absolute deep links without tokens, every
value escaped, and every outcome (not configured, sent, failed then retried) recorded on the delivery row."""

import pytest

from app.core.config import settings
from app.models import Notification, NotificationDelivery
from app.notifications import delivery
from app.notifications.delivery import deliver
from app.notifications.dispatch import queue_deliveries
from app.services import mailer
from tests.enh014_helpers import make_user

LINKS = [{"label": "Confirmed", "path": "/bdm/appointments/abc?action=confirm"}, {"label": "Cancel", "path": "/bdm/appointments/abc?action=cancel"}]


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.local/")


@pytest.fixture
def outbox(monkeypatch):
    sent: list = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    return sent


async def _send(**over):
    args = {"to_email": "bdm@example.local", "recipient_name": "Asha", "title": "Appointment reminder", "body": "Tomorrow at 10:00 AM.", "links": LINKS}
    return await mailer.send_bdm_reminder_email(**{**args, **over})


@pytest.mark.asyncio
async def test_unconfigured_smtp_is_not_configured(monkeypatch, outbox):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert await _send() == ("not_configured", None)
    assert outbox == []


@pytest.mark.asyncio
async def test_the_email_carries_absolute_token_free_buttons(smtp_on, outbox):
    assert await _send() == ("sent", None)
    msg = outbox[0]
    assert msg["To"] == "bdm@example.local" and msg["Subject"] == "Appointment reminder -- EduSphere"
    text = msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    for body in (text, html):
        assert "https://app.example.local/bdm/appointments/abc?action=confirm" in body.replace("&amp;", "&")
        assert "Tomorrow at 10:00 AM." in body and "token" not in body.lower()
    assert "Confirmed" in html and "Cancel" in html


@pytest.mark.asyncio
async def test_html_escapes_every_value(smtp_on, outbox):
    await _send(title="<b>x</b>", body="<script>alert(1)</script>", recipient_name="<i>n</i>", links=[{"label": "<x>", "path": '/a?b="c"'}])
    html = outbox[0].get_body(preferencelist=("html",)).get_content()
    assert "<script>" not in html and "<b>x</b>" not in html and "<i>n</i>" not in html and "<x>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.asyncio
async def test_an_smtp_error_is_failed_with_the_reason(smtp_on, monkeypatch):
    def boom(msg):
        raise OSError("connection refused")

    monkeypatch.setattr(mailer, "_send_sync", boom)
    status, error = await _send()
    assert status == "failed" and "connection refused" in error


async def _queued(db, user, links=LINKS) -> NotificationDelivery:
    note = Notification(user_id=user.id, title="Appointment reminder", body="Tomorrow at 10:00 AM.", action_url="/bdm/appointments/abc")
    db.add(note)
    await db.flush()
    (row,) = await queue_deliveries(db, note, user, context={"kind": "bdm_reminder", "links": links}, channels=["email"])
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_delivery_sends_a_bdm_reminder_by_smtp_never_the_webhook(db_session, smtp_on, outbox, monkeypatch):
    async def webhook(channel, payload):
        raise AssertionError("the BDM reminder must not use the webhook")

    monkeypatch.setattr(delivery, "send_notification", webhook)
    user = await make_user(db_session, role="bdm", division="it")
    row = await _queued(db_session, user)
    assert await deliver(row.id) == "sent"
    assert outbox[0]["To"] == user.email


@pytest.mark.asyncio
async def test_delivery_records_not_configured_when_smtp_is_unset(db_session, monkeypatch, outbox):
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(delivery, "send_notification", lambda *a: (_ for _ in ()).throw(AssertionError("no webhook fallback")))
    user = await make_user(db_session, role="bdm", division="it")
    row = await _queued(db_session, user)
    assert await deliver(row.id) == "not_configured"
    stored = await db_session.get(NotificationDelivery, row.id, populate_existing=True)
    assert stored.status == "not_configured" and await db_session.get(Notification, row.notification_id) is not None


@pytest.mark.asyncio
async def test_delivery_retries_an_smtp_failure_and_keeps_the_error(db_session, smtp_on, monkeypatch, enqueued):
    def boom(msg):
        raise OSError("smtp down")

    monkeypatch.setattr(mailer, "_send_sync", boom)
    user = await make_user(db_session, role="bdm", division="it")
    row = await _queued(db_session, user)
    enqueued.clear()
    assert await deliver(row.id) == "retrying"
    stored = await db_session.get(NotificationDelivery, row.id, populate_existing=True)
    assert stored.status == "retrying" and "smtp down" in stored.error
    assert enqueued and enqueued[-1][0] == str(row.id)
