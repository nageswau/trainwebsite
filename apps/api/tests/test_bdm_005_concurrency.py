"""bdm-005 -- races (spec §6.5): the organization row lock serializes MoU writes with each other and with stage moves."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm004_helpers import move
from tests.bdm005_helpers import change, mou_rows, start, started, world


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_creates_one_wins(client, db_session):
    w = await world(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, w["owner"])
        await login(b, w["owner"])
        results = await asyncio.gather(start(a, w["org"]), start(b, w["org"]))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert [r.is_current for r in await mou_rows(db_session, w["org"]["id"])] == [True]


@pytest.mark.asyncio
async def test_two_status_changes_from_the_same_status_one_wins(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    async with _client() as a, _client() as b:
        await login(a, w["owner"])
        await login(b, w["owner"])
        results = await asyncio.gather(
            change(a, w["org"], status="discussion_started", from_status="prospect"),
            change(b, w["org"], status="rejected", from_status="prospect"),
        )
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.asyncio
async def test_signing_while_the_stage_moves_does_not_deadlock(client, db_session):
    w = await world(client, db_session, "college")
    await started(client, w["org"])
    async with _client() as a, _client() as b:
        await login(a, w["owner"])
        await login(b, w["owner"])
        signed, moved = await asyncio.wait_for(
            asyncio.gather(change(a, w["org"], status="signed", from_status="prospect", signed_on="2026-01-10"), move(b, w["org"], "contacted")),
            timeout=30,
        )
    assert signed.status_code == 200
    assert moved.status_code in (200, 409)  # 409 `stage_changed` when the sign advanced it first
    stage = (await client.get(f"/api/v1/bdm/organizations/{w['org']['id']}")).json()["organization"]["pipeline"]["stage"]
    assert stage in ("mou_signed", "contacted")
