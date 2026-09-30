"""ENH-014 Task 6 -- deliver(): claim, send per channel, record, retry (spec §6.5; AC07-AC10, AC12, AC14)."""

import asyncio

import pytest

from app.core.config import settings
from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications import delivery, twilio
from app.notifications.delivery import deliver
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user, set_prefs

SID = "SM" + "b" * 32


@pytest.fixture
def twilio_on(monkeypatch):
    for key, value in {"twilio_account_sid": "AC1", "twilio_auth_token": "t", "twilio_whatsapp_from": "+1415", "twilio_sms_from": "+1500", "twilio_whatsapp_content_sid": "HX1"}.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def sent(monkeypatch):
    """Records every outbound call; each channel answers 'sent' unless a test overrides it."""
    calls: list[tuple] = []

    async def whatsapp(to, title, body, action_url, **_):
        calls.append(("whatsapp", to, title))
        return twilio.SendResult("sent", provider_reference=SID)

    async def sms(to, title, body, action_url, **_):
        calls.append(("sms", to, title))
        return twilio.SendResult("sent", provider_reference=SID)

    async def webhook(channel, payload):
        calls.append((f"webhook:{channel}", payload.get("to"), payload.get("title")))
        return "not_configured", None

    async def smtp(**kwargs):
        calls.append(("smtp", kwargs["to_email"], kwargs["school_name"]))
        return "sent", None

    monkeypatch.setattr(twilio, "send_whatsapp", whatsapp)
    monkeypatch.setattr(twilio, "send_sms", sms)
    monkeypatch.setattr(delivery, "send_notification", webhook)
    monkeypatch.setattr(delivery, "send_parent_notification_email", smtp)
    return calls


async def _queued(db, user: User, *, context=None) -> dict[str, NotificationDelivery]:
    note = Notification(user_id=user.id, title="Result published", body="Maths is out.", action_url="/school/parent/dashboard")
    db.add(note)
    await db.flush()
    rows = await queue_deliveries(db, note, user, context=context)
    await db.commit()
    return {r.channel: r for r in rows}


async def _row(db, row_id) -> NotificationDelivery:
    return await db.get(NotificationDelivery, row_id, populate_existing=True)


@pytest.mark.asyncio
async def test_whatsapp_is_sent_with_the_normalised_number(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="98765 43210")
    await set_prefs(db_session, user, whatsapp=True)
    rows = await _queued(db_session, user)
    assert await deliver(rows["whatsapp"].id) == "sent"
    row = await _row(db_session, rows["whatsapp"].id)
    assert (row.status, row.attempt_count, row.provider_reference, row.error) == ("sent", 1, SID, None) and row.sent_at is not None
    assert ("whatsapp", "+919876543210", "Result published") in sent


@pytest.mark.asyncio
async def test_school_email_keeps_the_smtp_path_with_the_school_name(db_session, sent):
    user = await make_user(db_session)
    rows = await _queued(db_session, user, context={"kind": "school", "school_name": "Green Valley"})
    assert await deliver(rows["email"].id) == "sent"
    assert sent == [("smtp", user.email, "Green Valley")]


@pytest.mark.asyncio
async def test_school_email_falls_back_to_the_webhook_when_smtp_is_not_configured(db_session, sent, monkeypatch):
    async def smtp_off(**kwargs):
        return "not_configured", None

    monkeypatch.setattr(delivery, "send_parent_notification_email", smtp_off)
    user = await make_user(db_session)
    rows = await _queued(db_session, user, context={"kind": "school", "school_name": "Green Valley"})
    assert await deliver(rows["email"].id) == "not_configured"
    assert sent == [("webhook:email", user.email, "Result published")]


@pytest.mark.asyncio
async def test_inbound_email_payload_omits_the_phone_but_notify_user_keeps_it(db_session, monkeypatch):
    """AC12: the pre-ENH-014 inbound._notify_student webhook payload never carried the phone; _notify_user's did."""
    from types import SimpleNamespace

    from sqlalchemy import select

    from app.api.inbound import _notify_student

    payloads = []

    async def webhook(channel, payload):
        payloads.append(payload)
        return "not_configured", None

    monkeypatch.setattr(delivery, "send_notification", webhook)
    user = await make_user(db_session, role="overseas_student", phone="9876543210")
    await _notify_student(db_session, SimpleNamespace(subject="Offer letter"), SimpleNamespace(student_id=user.id))
    await db_session.commit()
    [inbound_row] = (await db_session.scalars(select(NotificationDelivery).join(Notification).where(Notification.user_id == user.id))).all()
    assert inbound_row.context == {"kind": "inbound"}
    await deliver(inbound_row.id)
    generic = await _queued(db_session, user)
    await deliver(generic["email"].id)
    assert "phone" not in payloads[0] and payloads[0]["title"] == "University update received"
    assert payloads[1]["phone"] == "9876543210"


@pytest.mark.asyncio
async def test_generic_email_uses_the_email_webhook(db_session, sent):
    user = await make_user(db_session, role="it_student", division="it")
    rows = await _queued(db_session, user)
    assert await deliver(rows["email"].id) == "not_configured"
    assert sent == [("webhook:email", user.email, "Result published")]


@pytest.mark.asyncio
async def test_invalid_phone_fails_that_delivery_only_and_is_not_retried(db_session, twilio_on, sent, enqueued):
    bad = await make_user(db_session, phone="12345")
    good = await make_user(db_session, phone="9876543210")
    for u in (bad, good):
        await set_prefs(db_session, u, whatsapp=True)
    bad_rows, good_rows = await _queued(db_session, bad), await _queued(db_session, good)
    enqueued.clear()
    assert await deliver(bad_rows["whatsapp"].id) == "failed"
    assert await deliver(good_rows["whatsapp"].id) == "sent"
    row = await _row(db_session, bad_rows["whatsapp"].id)
    assert (row.status, row.error) == ("failed", "invalid_phone") and enqueued == []


@pytest.mark.asyncio
async def test_transient_failures_retry_at_60_300_1500_then_fail(db_session, twilio_on, monkeypatch, enqueued):
    async def flaky(*args, **kwargs):
        return twilio.SendResult("failed", error="twilio:503", transient=True)

    monkeypatch.setattr(twilio, "send_sms", flaky)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    row_id = (await _queued(db_session, user))["sms"].id
    enqueued.clear()
    for expected_countdown in (60, 300, 1500):
        assert await deliver(row_id) == "retrying"
        assert enqueued.pop() == (str(row_id), expected_countdown)
    assert await deliver(row_id) == "failed"
    row = await _row(db_session, row_id)
    assert (row.status, row.attempt_count, row.error) == ("failed", 4, "twilio:503") and enqueued == []


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried(db_session, twilio_on, monkeypatch, enqueued):
    async def rejected(*args, **kwargs):
        return twilio.SendResult("failed", error="twilio:21211 invalid", transient=False)

    monkeypatch.setattr(twilio, "send_whatsapp", rejected)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    row_id = (await _queued(db_session, user))["whatsapp"].id
    enqueued.clear()
    assert await deliver(row_id) == "failed" and enqueued == []


@pytest.mark.asyncio
async def test_a_duplicate_task_sends_once(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    row_id = (await _queued(db_session, user))["sms"].id
    results = await asyncio.gather(deliver(row_id), deliver(row_id))
    assert sorted(results, key=str) == sorted(["sent", None], key=str)
    assert [c for c in sent if c[0] == "sms"] == [("sms", "+919876543210", "Result published")]


@pytest.mark.asyncio
async def test_opting_out_after_queueing_skips(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    row_id = (await _queued(db_session, user))["whatsapp"].id
    pref = await db_session.get(NotificationPreference, user.id)
    pref.whatsapp_opt_in = False
    await db_session.commit()
    assert await deliver(row_id) == "skipped"
    assert (await _row(db_session, row_id)).error == "opted_out" and not [c for c in sent if c[0] == "whatsapp"]


@pytest.mark.asyncio
async def test_inactive_recipient_is_skipped(db_session, sent):
    # Review Focus 4.
    user = await make_user(db_session)
    row_id = (await _queued(db_session, user))["email"].id
    user.active = False
    await db_session.commit()
    assert await deliver(row_id) == "skipped" and sent == []


@pytest.mark.asyncio
async def test_without_twilio_the_legacy_webhook_is_used_else_not_configured(db_session, sent, monkeypatch):
    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "twilio_sms_from", "twilio_whatsapp_content_sid"):
        monkeypatch.setattr(settings, key, None)  # a developer's local .env may carry sandbox values
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    rows = await _queued(db_session, user)
    assert await deliver(rows["whatsapp"].id) == "not_configured"  # fake webhook answers not_configured
    assert ("webhook:whatsapp", user.email, "Result published") in sent


@pytest.mark.asyncio
async def test_a_claimed_or_finished_row_is_left_alone(db_session, sent):
    user = await make_user(db_session)
    row_id = (await _queued(db_session, user))["email"].id
    assert await deliver(row_id) is not None
    assert await deliver(row_id) is None  # already final: no second send
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_logs_never_carry_contact_details_or_text(db_session, twilio_on, sent, caplog):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    rows = await _queued(db_session, user)
    with caplog.at_level("INFO"):
        for row in rows.values():
            await deliver(row.id)
    text = caplog.text + " ".join(str(getattr(r, "extra_fields", "")) for r in caplog.records)
    assert "9876543210" not in text and user.email not in text and "Maths is out." not in text


@pytest.mark.asyncio
async def test_an_unexpected_sender_exception_fails_the_row_without_leaking(db_session, twilio_on, monkeypatch, enqueued, caplog):
    async def boom(*args, **kwargs):
        raise RuntimeError("boom +919876543210")

    monkeypatch.setattr(twilio, "send_sms", boom)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    row_id = (await _queued(db_session, user))["sms"].id
    enqueued.clear()
    with caplog.at_level("INFO"):
        assert await deliver(row_id) == "failed"
    row = await _row(db_session, row_id)
    assert (row.status, row.error) == ("failed", "unexpected RuntimeError") and enqueued == []
    assert "9876543210" not in caplog.text
