"""ENH-014 Task 4 -- queue_deliveries and the after-commit publish (spec §6.1; AC04, AC05)."""

import threading
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
    # `apply_async` acquires a producer from `amqp.producer_pool`, which is built lazily from `connection_for_write()`
    # (patched above) and then cached on the shared app for good. Start from empty caches so the dead-broker pools are
    # built here, and let monkeypatch restore the originals so no later test publishes through them.
    monkeypatch.setattr(worker.celery.amqp, "_producer_pool", None)
    monkeypatch.setattr(worker.celery, "_pool", None)
    started = time.monotonic()
    try:
        assert dispatch.enqueue("abc") is False
        assert time.monotonic() - started < 3
    finally:
        for pool in (worker.celery.amqp._producer_pool, worker.celery._pool):
            if pool is not None:
                pool.force_close_all()


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


def _counting_stub(behaviour):
    calls = []

    def stub(delivery_id, countdown):
        calls.append(delivery_id)
        behaviour()

    return stub, calls


def test_a_hung_publish_is_abandoned_within_the_bounded_wait(monkeypatch):
    """QAF-01: DNS resolution of a dead broker host is not covered by the socket timeouts, so the wait itself is bounded."""
    release = threading.Event()
    stub, calls = _counting_stub(lambda: release.wait(5))
    monkeypatch.setattr(dispatch, "_publish", stub)
    try:
        started = time.monotonic()
        assert dispatch.enqueue("abc") is False
        assert time.monotonic() - started < 2.5
        # The back-off is now open: the next enqueue fails at once without touching the broker.
        started = time.monotonic()
        assert dispatch.enqueue("def") is False
        assert time.monotonic() - started < 0.1
        assert calls == ["abc"]
    finally:
        release.set()
        dispatch._publisher.submit(lambda: None).result(timeout=5)  # free the single publisher thread for later tests


def test_a_raising_publish_opens_the_back_off(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    stub, calls = _counting_stub(boom)
    monkeypatch.setattr(dispatch, "_publish", stub)
    assert dispatch.enqueue("abc") is False
    assert dispatch.enqueue("def") is False
    assert calls == ["abc"]


def test_publishing_resumes_once_the_back_off_expires(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    stub, calls = _counting_stub(boom)
    monkeypatch.setattr(dispatch, "_publish", stub)
    assert dispatch.enqueue("abc") is False
    now = time.monotonic()
    monkeypatch.setattr(dispatch.time, "monotonic", lambda: now + dispatch.BROKER_BACKOFF_SECONDS + 1)
    ok, calls = _counting_stub(lambda: None)
    monkeypatch.setattr(dispatch, "_publish", ok)
    assert dispatch.enqueue("def") is True
    assert calls == ["def"]
