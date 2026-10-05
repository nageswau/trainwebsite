"""ENH-014 Task 8 -- existing triggers deliver on opted-in channels (AC04-AC06, AC11). Reuses SCH-007's school builder."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Notification, NotificationDelivery
from tests.enh014_helpers import drain, login, make_user, set_prefs
from tests.test_sch_007_parent_portal import _login as sch_login
from tests.test_sch_007_parent_portal import _notifications_for, _school, _staff


async def _channels(db, notes) -> list[tuple[str, str]]:
    rows = (await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id.in_([n.id for n in notes])))).all()
    return sorted((r.channel, r.status) for r in rows)


async def _publish_result(client, db, ctx) -> None:
    uploader, approver = await _staff(db, ctx, "academic_team"), await _staff(db, ctx, "academic_team")
    await sch_login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student_a"].id), "academic_year": "2026-27", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 88})
    assert created.status_code == 201, created.text
    await sch_login(client, approver.email)
    assert (await client.post(f"/api/v1/school/academic-team/results/{created.json()['id']}/verify")).status_code == 200
    assert (await client.post(f"/api/v1/school/academic-team/results/{created.json()['id']}/publish")).status_code == 200


@pytest.mark.asyncio
async def test_result_publish_reaches_an_opted_in_parent_on_whatsapp(client, db_session, enqueued, monkeypatch):
    from app.notifications import twilio

    whatsapp_calls = []

    async def fake_whatsapp(to, title, body, action_url, **_):
        whatsapp_calls.append((to, title))
        return twilio.SendResult("sent", provider_reference="SM" + "c" * 32)

    monkeypatch.setattr(twilio, "send_whatsapp", fake_whatsapp)
    monkeypatch.setattr(twilio, "configured", lambda channel: True)
    ctx = await _school(db_session)
    ctx["parent_a"].phone = "9876543210"
    await db_session.commit()
    await set_prefs(db_session, ctx["parent_a"], whatsapp=True)

    await _publish_result(client, db_session, ctx)
    await drain(enqueued)

    notes = await _notifications_for(db_session, ctx["parent_a"])
    channels = await _channels(db_session, notes)
    assert ("whatsapp", "sent") in channels and [c for c, _ in channels] == ["email", "whatsapp"]
    assert whatsapp_calls == [("+919876543210", "Term 1 Mathematics result published for Child A")]
    assert await _notifications_for(db_session, ctx["parent_b"]) == []


@pytest.mark.asyncio
async def test_a_parent_who_did_not_opt_in_gets_email_only(client, db_session, enqueued):
    ctx = await _school(db_session)
    ctx["parent_a"].phone = "9876543210"
    await db_session.commit()
    await _publish_result(client, db_session, ctx)
    notes = await _notifications_for(db_session, ctx["parent_a"])
    assert [c for c, _ in await _channels(db_session, notes)] == ["email"]


@pytest.mark.asyncio
async def test_session_scheduling_queues_for_each_parent_and_returns_before_sending(client, db_session, enqueued):
    ctx = await _school(db_session)
    await set_prefs(db_session, ctx["parent_b"], sms=True)
    ctx["parent_b"].phone = "9876543211"
    await db_session.commit()
    await sch_login(client, ctx["coordinator"].email)
    when = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0).isoformat()
    response = await client.post("/api/v1/school/activities", json={"title": "Career Workshop", "scheduled_at": when})
    assert response.status_code == 201, response.text
    a = await _channels(db_session, await _notifications_for(db_session, ctx["parent_a"]))
    b = await _channels(db_session, await _notifications_for(db_session, ctx["parent_b"]))
    assert a == [("email", "queued")] and b == [("email", "queued"), ("sms", "queued")]  # AC05: sent later, by the worker


@pytest.mark.asyncio
async def test_it_triggers_follow_preferences_including_the_former_email_only_calls(db_session, enqueued):
    from app.api.workflows import _notify_user

    student = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, student, sms=True)
    await _notify_user(db_session, student, "Certificate issued", "Your certificate is ready.", "/it/student/certificates")
    await db_session.commit()
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == student.id))).all()
    assert [c for c, _ in await _channels(db_session, [note])] == ["email", "sms"]


@pytest.mark.asyncio
async def test_password_reset_stays_inline_and_email_only(client, db_session, enqueued, monkeypatch):
    import app.api.auth as auth_module

    async def fake_send(channel, payload):
        return "sent", None

    monkeypatch.setattr(auth_module, "send_notification", fake_send)
    user = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": user.email})).status_code == 202
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == user.id))).all()
    assert await _channels(db_session, [note]) == [("email", "sent")] and enqueued == []  # AC11


@pytest.mark.asyncio
async def test_admin_notify_queues_only_opted_in_channels(client, db_session, enqueued):
    admin = await make_user(db_session, role="overseas_admin")
    target = await make_user(db_session, role="overseas_student", phone="9876543210")
    await set_prefs(db_session, target, sms=True)
    await login(client, admin.email)
    response = await client.post("/api/v1/communications/notify", json={"user_id": str(target.id), "title": "Hello", "body": "Update", "channels": ["email", "whatsapp", "sms"]})
    assert response.status_code == 202, response.text
    assert response.json() == {"queued": True, "channels": {"email": "queued", "sms": "queued"}}
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == target.id))).all()
    assert [c for c, _ in await _channels(db_session, [note])] == ["email", "sms"]
