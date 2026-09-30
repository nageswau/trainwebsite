"""ENH-014 Task 4 -- queue_deliveries and the after-commit publish (spec §6.1; AC04, AC05)."""

import pytest
from sqlalchemy import select

from app.models import Notification, NotificationDelivery
from app.notifications import dispatch
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user, set_prefs


async def _notice(db, user) -> Notification:
    note = Notification(user_id=user.id, title="Result published", body="Term 1 Maths is available.", action_url="/school/parent/dashboard")
    db.add(note)
    await db.flush()
    return note


async def _rows(db, note) -> list[NotificationDelivery]:
    return list((await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id).order_by(NotificationDelivery.channel))).all())


@pytest.mark.asyncio
async def test_without_opt_in_only_email_is_queued(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user, context={"kind": "school", "school_name": "Green Valley"})
    await db_session.commit()
    [row] = await _rows(db_session, note)
    assert (row.channel, row.status, row.attempt_count, row.context) == ("email", "queued", 0, {"kind": "school", "school_name": "Green Valley"})
    assert enqueued == [(str(row.id), 0)]


@pytest.mark.asyncio
async def test_opted_in_channels_are_queued_alongside_email(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    await db_session.commit()
    assert [r.channel for r in await _rows(db_session, note)] == ["email", "sms", "whatsapp"]
    assert len(enqueued) == 3


@pytest.mark.asyncio
async def test_explicit_channels_never_bypass_opt_in(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user, channels=["email", "whatsapp", "sms", "fax"])
    await db_session.commit()
    assert [r.channel for r in await _rows(db_session, note)] == ["email", "sms"]


@pytest.mark.asyncio
async def test_publish_happens_only_after_commit(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    assert enqueued == []  # flushed, not committed: nothing published yet
    await db_session.commit()
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_a_rolled_back_write_queues_and_publishes_nothing(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    note_id = note.id
    await queue_deliveries(db_session, note, user)
    await db_session.rollback()
    await db_session.commit()  # a later, unrelated commit must not publish the discarded ids
    assert enqueued == []
    assert (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note_id))).all() == []


@pytest.mark.asyncio
async def test_a_broker_failure_never_fails_the_commit(db_session, enqueued, monkeypatch):
    def broken(delivery_id, countdown):
        raise ConnectionError("redis down")

    monkeypatch.setattr(dispatch, "_publish", broken)
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    await db_session.commit()  # must not raise
    [row] = await _rows(db_session, note)
    assert row.status == "queued"  # left for the sweeper (Task 7)
