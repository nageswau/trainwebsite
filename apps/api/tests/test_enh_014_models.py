"""ENH-014 Task 1 -- the preference row and the delivery render context (spec §4)."""

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models import Notification, NotificationDelivery, NotificationPreference
from tests.enh014_helpers import make_user


@pytest.mark.asyncio
async def test_preference_row_defaults_off(db_session):
    user = await make_user(db_session)
    db_session.add(NotificationPreference(user_id=user.id))
    await db_session.commit()
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert (pref.whatsapp_opt_in, pref.sms_opt_in, pref.whatsapp_opted_in_at, pref.sms_opted_in_at) == (False, False, None, None)


@pytest.mark.asyncio
async def test_delivery_keeps_its_render_context(db_session):
    user = await make_user(db_session)
    note = Notification(user_id=user.id, title="t", body="b")
    db_session.add(note)
    await db_session.flush()
    row = NotificationDelivery(notification_id=note.id, channel="email", status="queued", attempt_count=0, context={"kind": "school", "school_name": "Green Valley"})
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.context == {"kind": "school", "school_name": "Green Valley"}


@pytest.mark.asyncio
async def test_sweeper_index_exists(db_session):
    names = await db_session.run_sync(lambda s: {i["name"] for i in sa_inspect(s.connection()).get_indexes("notification_deliveries")})
    assert "ix_notification_deliveries_status_updated_at" in names
