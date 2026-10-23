"""ccrm-012 (DEC-SCOPE-246 QS7): stage / priority / lead-date filters on the counselor's leads (GET /counselor/leads)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.ccrm012_helpers import LEADS, search_world


@pytest_asyncio.fixture
async def world(db_session):
    return await search_world(db_session)


async def _ids(c, **params):
    r = await c.get(LEADS, params=params)
    assert r.status_code == 200, r.text
    return r.json(), {str(item["id"]) for item in r.json()["items"]}


@pytest.mark.asyncio
async def test_lead_filters_narrow_the_counselors_leads(world):
    one, two = str(world["lead1"].id), str(world["lead2"].id)
    async with client_for(world["a"].email) as c:
        assert (await _ids(c))[1] == {one, two}
        assert (await _ids(c, priority="hot"))[1] == {one}
        assert (await _ids(c, stage="follow_up"))[1] == {two}
        assert (await _ids(c, **{"from": "2026-01-01", "to": "2026-01-31"}))[1] == {two}
        data, ids = await _ids(c, priority="hot", stage="follow_up")
    assert ids == set() and data["total"] == 0
    assert str(world["lead_b"].id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "detail"), [
    ({"priority": "lukewarm"}, "Unknown filter value"),
    ({"stage": "nowhere"}, "Unknown filter value"),
    ({"from": "soon"}, "Unknown filter value"),
    ({"from": "2026-03-01", "to": "2026-02-01"}, "The start date must be on or before the end date"),
])
async def test_bad_lead_filters_are_refused(world, params, detail):
    async with client_for(world["a"].email) as c:
        r = await c.get(LEADS, params=params)
    assert r.status_code == 422 and r.json()["detail"] == detail
