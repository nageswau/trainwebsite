"""bdm-005 -- Expired is derived on read (M2, M7, M9; AC3; Review Focus 4)."""

from datetime import UTC, date, datetime

import pytest

from app.services import bdm_mous as svc
from tests.bdm005_helpers import change, events, mou_url, started, world

TODAY = date(2026, 10, 6)
WINDOW = {"signed_on": "2025-10-01", "valid_from": "2025-10-01"}


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(svc, "today", lambda: TODAY)


def test_today_is_the_india_calendar_date(monkeypatch):
    """20:00 UTC on 5 October is 01:30 on 6 October in India."""

    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 5, 20, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(svc, "datetime", Fixed)
    assert svc.today() == date(2026, 10, 6)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", "signed"])
async def test_signed_and_active_past_valid_until_read_expired(client, db_session, frozen, status):
    w = await world(client, db_session)
    mou = await started(client, w["org"], status=status, valid_until="2026-10-05", **WINDOW)
    assert (mou["status"], mou["status_label"], mou["expired_on"]) == ("expired", "Expired", "2026-10-06")
    assert mou["permissions"]["can_renew"] is True
    body = (await client.get(mou_url(w["org"]["id"]))).json()
    assert body["current"]["status"] == "expired" and body["can_start"] is True


@pytest.mark.asyncio
async def test_valid_until_today_is_still_active(client, db_session, frozen):
    w = await world(client, db_session)
    mou = await started(client, w["org"], status="active", valid_until=TODAY.isoformat(), **WINDOW)
    assert (mou["status"], mou["expired_on"], mou["permissions"]["can_renew"]) == ("active", None, False)


@pytest.mark.asyncio
async def test_other_statuses_never_expire(client, db_session, frozen):
    w = await world(client, db_session)
    mou = await started(client, w["org"], status="under_negotiation", valid_until="2026-01-01", valid_from="2025-01-01")
    assert mou["status"] == "under_negotiation"


@pytest.mark.asyncio
async def test_an_expired_mou_refuses_a_status_change(client, db_session, frozen):
    w = await world(client, db_session)
    await started(client, w["org"], status="active", valid_until="2026-10-05", **WINDOW)
    response = await change(client, w["org"], status="under_negotiation", from_status="expired")
    assert response.status_code == 409
    assert response.json()["detail"] == {"message": "This MoU has expired. Start a renewal.", "code": "mou_expired"}
    stale = await change(client, w["org"], status="rejected", from_status="active")  # the stored value is not what the form shows
    assert stale.status_code == 409 and stale.json()["detail"]["current_status"] == "expired"


@pytest.mark.asyncio
async def test_correcting_valid_until_is_recorded_as_expired_to_active(client, db_session, frozen):
    w = await world(client, db_session)
    mou = await started(client, w["org"], status="active", valid_until="2026-10-05", **WINDOW)
    response = await change(client, w["org"], valid_until="2027-09-30")
    assert response.status_code == 200 and response.json()["mou"]["status"] == "active"
    last = (await events(db_session, mou["id"]))[-1]
    assert (last.kind, last.from_status, last.to_status, last.changed) == ("updated", "expired", "active", ["valid_until"])
