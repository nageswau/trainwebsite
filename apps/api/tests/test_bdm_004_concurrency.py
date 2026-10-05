"""bdm-004 -- AC7: the organization row lock serializes two moves from the same stage; exactly one wins."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm002_helpers import create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import events, move


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_moves_from_the_same_stage_one_wins(client, db_session):
    bdm = await bdm_of(db_session, "college")
    await login(client, bdm)
    org = await create_org(client)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        results = await asyncio.gather(move(a, org, "contacted"), move(b, org, "meeting"))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(await events(db_session, org["id"])) == 1
