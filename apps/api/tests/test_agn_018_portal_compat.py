"""AGN-018 AC08 -- the portal dashboard keeps its labels, order and commission strings, and its counts now equal the AGN-018
endpoint (Students includes students with no login: the deliberate DEC-SCOPE-061 fix)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn018_helpers import DASHBOARD_API, PORTAL_DASHBOARD, dashboard_world


@pytest_asyncio.fixture
async def world(db_session):
    return await dashboard_world(db_session)


async def _both(email):
    async with client_for(email) as c:
        portal = (await c.get(PORTAL_DASHBOARD)).json()
        api = (await c.get(DASHBOARD_API)).json()
    return {m["label"]: m["value"] for m in portal["metrics"]}, [m["label"] for m in portal["metrics"]], api


@pytest.mark.asyncio
async def test_master_portal_metrics(world):
    metrics, labels, api = await _both(world["master"].email)
    assert labels == ["Students", "Applications", "Pending actions", "Claimable commission", "Claims", "Revenue", "Offers", "Your code"]
    assert metrics["Students"] == api["students"] == 4  # was 1: only the student with a login was counted
    assert (metrics["Applications"], metrics["Offers"], metrics["Pending actions"]) == (api["applications"], api["offers"], api["pending_actions"])
    # Unchanged strings (D4: "Claimable commission" still sums every currency under an INR label).
    assert metrics["Claimable commission"] == "INR 1,200" and metrics["Claims"] == 1 and metrics["Revenue"] == "INR 12,000 · USD 500"


@pytest.mark.asyncio
async def test_staff_portal_metrics(world):
    metrics, labels, api = await _both(world["s1"]["user"].email)
    assert labels == ["Students", "Applications", "Pending actions", "Offers", "Your code"]
    assert (metrics["Students"], metrics["Applications"], metrics["Offers"]) == (api["students"], api["applications"], api["offers"]) == (2, 5, 3)
