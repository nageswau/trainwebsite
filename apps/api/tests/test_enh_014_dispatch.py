"""ENH-014 Task 4 -- queue_deliveries and the after-commit publish (spec §6.1; AC04, AC05)."""

import time

import pytest
from sqlalchemy import select

from app.models import Notification, NotificationDelivery
from app.notifications import dispatch
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user, set_prefs

_REAL_PUBLISH = dispatch._publish  # captured at import, before the autouse fixture patches it


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


@pytest.mark.asyncio
async def test_savepoint_release_does_not_publish_early(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    async with db_session.begin_nested():
        pass
    assert enqueued == []
    await db_session.commit()
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_savepoint_rollback_keeps_outer_pending_ids(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    sp = await db_session.begin_nested()
    await sp.rollback()
    await db_session.commit()
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_root_rollback_with_open_savepoint_discards_everything(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await db_session.begin_nested()
    await queue_deliveries(db_session, note, user)
    await db_session.rollback()
    await db_session.commit()
    assert enqueued == []


@pytest.mark.asyncio
async def test_publish_calls_celery_with_fail_fast_options(db_session, monkeypatch):
    from app import worker

    calls = []
    monkeypatch.setattr(worker.deliver_notification_task, "apply_async", lambda *a, **kw: calls.append((a, kw)))
    _REAL_PUBLISH("abc", 60)
    [(args, kwargs)] = calls
    connection = kwargs.pop("connection")
    assert (args, kwargs) == ((("abc",),), {"countdown": 60, "retry": False, "ignore_result": True})
    assert {k: connection.transport_options.get(k) for k in ("socket_connect_timeout", "max_retries")} == {"socket_connect_timeout": 1, "max_retries": 0}
    assert worker.celery.conf.broker_transport_options.get("socket_connect_timeout") is None  # the worker's own settings are untouched


@pytest.mark.parametrize("broker_url", ["redis://10.255.255.1:6379/0", "redis://127.0.0.1:6390/0"], ids=["unreachable", "refused"])
def test_a_dead_broker_fails_the_real_publish_within_a_bounded_time(monkeypatch, broker_url):
    """The real `_publish` against a dead broker AND a dead result backend (both are Redis in production)."""
    from celery.backends.redis import RedisBackend

    from app import worker

    real_connection_for_write = worker.celery.connection_for_write
    monkeypatch.setattr(worker.celery, "connection_for_write", lambda **kw: real_connection_for_write(broker_url, **kw))
    monkeypatch.setattr(worker.celery._local, "backend", RedisBackend(app=worker.celery, url=broker_url), raising=False)
    monkeypatch.setattr(dispatch, "_publish", _REAL_PUBLISH)
    started = time.monotonic()
    assert dispatch.enqueue("abc") is False
    assert time.monotonic() - started < 3


@pytest.mark.asyncio
async def test_after_commit_stops_publishing_at_the_first_broker_failure(db_session, monkeypatch):
    calls = []

    def broken(delivery_id, countdown):
        calls.append(delivery_id)
        raise ConnectionError("redis down")

    monkeypatch.setattr(dispatch, "_publish", broken)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    await db_session.commit()  # must not raise
    rows = await _rows(db_session, note)
    assert len(calls) == 1
    assert [r.status for r in rows] == ["queued", "queued", "queued"]  # left for the sweeper


@pytest.mark.asyncio
async def test_enqueue_reports_success(db_session, enqueued):
    assert dispatch.enqueue("abc", countdown=5) is True and enqueued == [("abc", 5)]
