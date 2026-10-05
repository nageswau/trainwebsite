"""bdm-009 -- AC9: the organization lock serializes log vs archive; the activity lock lets one of two deletes win."""

import asyncio
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm009_helpers import ACTIVITIES, activity_body, bdm_with_org


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_deletes_one_wins(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        results = await asyncio.gather(a.delete(f"{ACTIVITIES}/{created['id']}"), b.delete(f"{ACTIVITIES}/{created['id']}"))
    assert sorted(r.status_code for r in results) == [204, 404]


@pytest.mark.asyncio
async def test_log_and_archive_race_never_leaves_a_log_after_the_archive(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        logged, archived = await asyncio.gather(
            a.post(ACTIVITIES, json=activity_body(org["id"])), b.post(f"/api/v1/bdm/organizations/{org['id']}/archive"))
    assert archived.status_code == 200
    assert logged.status_code in (201, 422)
    if logged.status_code == 201:  # logged first: created before the archive committed
        created_at = datetime.fromisoformat(logged.json()["created_at"].replace("Z", "+00:00"))
        archived_at = datetime.fromisoformat(archived.json()["organization"]["archived_at"].replace("Z", "+00:00"))
        assert created_at <= archived_at
    else:
        assert logged.json()["detail"] == "This organization is archived"
