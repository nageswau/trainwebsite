"""bdm-015 R5 / bdm-009 AC4 -- a submitted day's activities can't be logged (backdated), edited or deleted."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import bdm_daily_reports as reports
from app.services.bdm_travel import india_today
from tests.bdm009_helpers import ACTIVITIES, activity_body, bdm_with_org, org_activities
from tests.bdm015_helpers import inside, submit_url


@pytest.mark.asyncio
async def test_todays_activities_lock_once_todays_report_is_submitted(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    logged = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    assert logged["permissions"]["can_change"] is True
    assert (await client.post(submit_url(india_today()), json={})).status_code == 201

    day = (await client.get(ACTIVITIES)).json()
    assert [a["permissions"]["can_change"] for a in day["items"]] == [False]
    timeline = (await client.get(org_activities(org["id"]))).json()
    assert [a["permissions"]["can_change"] for a in timeline["items"]] == [False]

    for response in (
        await client.post(ACTIVITIES, json=activity_body(org["id"])),
        await client.patch(f"{ACTIVITIES}/{logged['id']}", json={"note": "changed"}),
        await client.delete(f"{ACTIVITIES}/{logged['id']}"),
    ):
        assert (response.status_code, response.json()["detail"]) == (409, reports.DAY_LOCKED)


@pytest.mark.asyncio
async def test_a_backdated_log_is_refused_only_on_a_submitted_day(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    two_days_ago, three_days_ago = india_today() - timedelta(days=2), india_today() - timedelta(days=3)
    assert (await client.post(submit_url(two_days_ago), json={})).status_code == 201
    refused = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=inside(two_days_ago).isoformat()))
    assert (refused.status_code, refused.json()["detail"]) == (409, reports.DAY_LOCKED)
    allowed = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=inside(three_days_ago).isoformat()))
    assert allowed.status_code == 201
    today = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat()))
    assert today.status_code == 201 and today.json()["permissions"]["can_change"] is True
