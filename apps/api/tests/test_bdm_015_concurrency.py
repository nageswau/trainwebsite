"""bdm-015 -- the day lock: two submits of one day, one wins; a log racing a submit is either in the snapshot or refused."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import bdm_daily_reports as reports
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import login
from tests.bdm009_helpers import ACTIVITIES, activity_body, bdm_with_org
from tests.bdm015_helpers import by_key, submit_url


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_submits_of_one_day_one_wins(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        results = await asyncio.gather(a.post(submit_url(india_today()), json={}), b.post(submit_url(india_today()), json={}))
    assert sorted(r.status_code for r in results) == [201, 409]


@pytest.mark.asyncio
async def test_a_log_racing_the_submit_is_in_the_snapshot_or_refused(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        logged, submitted = await asyncio.gather(a.post(ACTIVITIES, json=activity_body(org["id"])), b.post(submit_url(india_today()), json={}))
    assert submitted.status_code == 201
    calls = by_key(submitted.json()["counts"])["calls_made"]
    if logged.status_code == 201:
        assert calls == 1
    else:
        assert (logged.status_code, logged.json()["detail"], calls) == (409, reports.DAY_LOCKED, 0)
