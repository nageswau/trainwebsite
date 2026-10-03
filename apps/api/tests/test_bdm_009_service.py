"""bdm-009 -- service rules (spec §4.2, §5.2; AC2, AC3, AC4)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import BdmActivity
from app.services import bdm_activities as svc
from app.services.bdm_travel import INDIA
from tests.bdm009_helpers import add_activity, bdm_with_org

NOW = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)  # 11:30 IST on 3 Oct


def test_day_range_is_the_ist_calendar_day():
    start, end = svc.day_range(date(2026, 10, 3))
    assert start == datetime(2026, 10, 2, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 10, 3, 18, 30, tzinfo=UTC)


def test_check_time_clamps_small_skew_refuses_future_and_more_than_seven_ist_days_back():
    assert svc.check_time(NOW, NOW) == NOW
    assert svc.check_time(NOW + timedelta(minutes=5), NOW) == NOW  # V9: within tolerance -> saved as now
    with pytest.raises(HTTPException) as exc:
        svc.check_time(NOW + timedelta(minutes=5, seconds=1), NOW)
    assert (exc.value.status_code, exc.value.detail) == (422, svc.FUTURE)
    seven_back = datetime(2026, 9, 26, 0, 0, tzinfo=INDIA)  # first instant of IST today - 7
    assert svc.check_time(seven_back, NOW) == seven_back
    with pytest.raises(HTTPException) as exc:
        svc.check_time(seven_back - timedelta(seconds=1), NOW)
    assert (exc.value.status_code, exc.value.detail) == (422, svc.TOO_OLD)


def test_editable_is_true_only_on_the_activitys_ist_day():
    today = BdmActivity(occurred_at=datetime(2026, 10, 2, 18, 30, tzinfo=UTC))  # 00:00 IST on 3 Oct
    yesterday = BdmActivity(occurred_at=datetime(2026, 10, 2, 18, 29, 59, tzinfo=UTC))
    assert svc.editable(today, NOW) is True
    assert svc.editable(yesterday, NOW) is False


def test_check_direction_uses_the_shared_rule():
    svc.check_direction("call", "inbound")
    svc.check_direction("visit", None)
    for channel, direction in (("call", None), ("visit", "outbound")):
        with pytest.raises(HTTPException) as exc:
            svc.check_direction(channel, direction)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_day_counts_are_exact_per_channel_and_ignore_other_bdms_and_days(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    _, other_bdm, other_org = await bdm_with_org(client, db_session)
    org_id, other_id = uuid.UUID(org["id"]), uuid.UUID(other_org["id"])
    day = date(2026, 9, 20)
    start, end = svc.day_range(day)
    for channel, direction, moment in (
        ("call", "outbound", start),                         # first instant of the day
        ("call", "outbound", start + timedelta(hours=3)),
        ("call", "inbound", start + timedelta(hours=4)),
        ("whatsapp", "outbound", start + timedelta(hours=5)),
        ("visit", None, end - timedelta(seconds=1)),          # last second of the day
    ):
        await add_activity(db_session, bdm.id, org_id, moment, channel, direction)
    await add_activity(db_session, bdm.id, other_id, start + timedelta(hours=6), "email", "outbound")
    await add_activity(db_session, bdm.id, org_id, end, "meeting", None)                    # the next IST day
    await add_activity(db_session, bdm.id, org_id, start - timedelta(seconds=1), "call", "outbound")  # the day before
    await add_activity(db_session, other_bdm.id, other_id, start + timedelta(hours=1), "call", "outbound")  # someone else
    counts = await svc.day_counts(db_session, [BdmActivity.bdm_user_id == bdm.id], day)
    assert counts == {
        "day": day,
        "by_channel": {"call": 3, "whatsapp": 1, "email": 1, "visit": 1, "meeting": 0, "other": 0},
        "calls_made": 2,
        "organizations_contacted": 2,
    }


@pytest.mark.asyncio
async def test_day_counts_use_ist_days_not_utc_days(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    late_utc = datetime(2026, 9, 21, 20, 0, tzinfo=UTC)  # 01:30 IST on 22 Sep
    await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), late_utc, "email", "outbound")
    mine = [BdmActivity.bdm_user_id == bdm.id]
    assert (await svc.day_counts(db_session, mine, date(2026, 9, 22)))["by_channel"]["email"] == 1
    assert (await svc.day_counts(db_session, mine, date(2026, 9, 21)))["by_channel"]["email"] == 0


@pytest.mark.asyncio
async def test_page_is_newest_first_with_logger_and_contact_flags(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    org_id = uuid.UUID(org["id"])
    older = await add_activity(db_session, bdm.id, org_id, datetime(2026, 9, 20, 5, tzinfo=UTC), contact_name="Dr Rao")
    newer = await add_activity(db_session, bdm.id, org_id, datetime(2026, 9, 20, 6, tzinfo=UTC), "visit", None)
    result = await svc.page(db_session, [BdmActivity.organization_id == org_id], 50, 0, bdm, NOW)
    assert [i["id"] for i in result["items"]] == [newer.id, older.id]
    assert result["total"] == 2
    first, second = result["items"]
    assert first["bdm"] == {"id": bdm.id, "full_name": bdm.full_name}
    assert first["organization"]["code"] == org["code"]
    assert second["contact_removed"] is True  # a name with no contact row: bdm-002 deleted the contact
    assert first["contact_removed"] is False
    assert first["permissions"] == {"can_change": False}  # not today


@pytest.mark.asyncio
async def test_daily_cap_counts_only_that_bdms_ist_day(client, db_session, monkeypatch):
    _, bdm, org = await bdm_with_org(client, db_session)
    monkeypatch.setattr(svc, "DAILY_CAP", 2)  # the rule, not the number, is under test
    day = date(2026, 9, 18)
    start, _ = svc.day_range(day)
    await svc.check_daily_cap(db_session, bdm.id, day)
    for minutes in (1, 2):
        await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(minutes=minutes))
    with pytest.raises(HTTPException) as exc:
        await svc.check_daily_cap(db_session, bdm.id, day)
    assert exc.value.status_code == 409
    await svc.check_daily_cap(db_session, bdm.id, day + timedelta(days=1))  # another day is free
