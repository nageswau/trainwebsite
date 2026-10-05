"""ENH-014 Task 7 -- the stale-delivery sweeper (spec §6.5). The test DB is shared, so assert on this test's rows only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import Notification, NotificationDelivery
from app.notifications.delivery import sweep_stale_deliveries
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user


async def _row(db, *, status: str, age: timedelta) -> NotificationDelivery:
    user = await make_user(db)
    note = Notification(user_id=user.id, title="t", body="b")
    db.add(note)
    await db.flush()
    [row] = await queue_deliveries(db, note, user)
    await db.commit()
    await db.execute(update(NotificationDelivery).where(NotificationDelivery.id == row.id).values(status=status, updated_at=datetime.now(UTC) - age))
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_stale_queued_and_retrying_rows_are_published_again(db_session, enqueued):
    queued = await _row(db_session, status="queued", age=timedelta(minutes=31))
    retrying = await _row(db_session, status="retrying", age=timedelta(minutes=45))
    fresh = await _row(db_session, status="queued", age=timedelta(minutes=5))
    enqueued.clear()
    await sweep_stale_deliveries()
    published = {d for d, _ in enqueued}
    assert {str(queued.id), str(retrying.id)} <= published and str(fresh.id) not in published
    row = await db_session.get(NotificationDelivery, queued.id, populate_existing=True)
    assert row.status == "queued" and row.updated_at > datetime.now(UTC) - timedelta(minutes=1)  # touched: not re-published every sweep


@pytest.mark.asyncio
async def test_a_stuck_sending_row_is_failed_never_resent(db_session, enqueued):
    stuck = await _row(db_session, status="sending", age=timedelta(minutes=16))
    recent = await _row(db_session, status="sending", age=timedelta(minutes=2))
    enqueued.clear()
    await sweep_stale_deliveries()
    assert (await db_session.get(NotificationDelivery, stuck.id, populate_existing=True)).status == "failed"
    assert (await db_session.get(NotificationDelivery, stuck.id)).error == "worker interrupted"
    assert (await db_session.get(NotificationDelivery, recent.id, populate_existing=True)).status == "sending"
    assert str(stuck.id) not in {d for d, _ in enqueued}


@pytest.mark.asyncio
async def test_the_sweeper_stops_publishing_at_the_first_broker_failure(db_session, monkeypatch):
    from app.notifications import dispatch

    first = await _row(db_session, status="queued", age=timedelta(minutes=31))
    second = await _row(db_session, status="queued", age=timedelta(minutes=31))
    calls = []

    def broken(delivery_id, countdown):
        calls.append(delivery_id)
        raise ConnectionError("redis down")

    monkeypatch.setattr(dispatch, "_publish", broken)
    counts = await sweep_stale_deliveries()
    assert counts["requeued"] >= 2 and len(calls) == 1
    for row in (first, second):
        assert (await db_session.get(NotificationDelivery, row.id, populate_existing=True)).status == "queued"  # the next sweep retries
