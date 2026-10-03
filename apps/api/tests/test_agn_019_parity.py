"""AGN-019 AC5 (DEC-SCOPE-065 P5/P8): with no dates, each staff row's AGN-018 columns equal the dashboard's staff table, so the two
pages never disagree about the same figures."""

import pytest

from tests.agn001_helpers import client_for
from tests.agn018_helpers import DASHBOARD_API, dashboard_world
from tests.agn019_helpers import PERFORMANCE_API

SHARED = ("students", "applications", "offers", "enrollments")


@pytest.mark.asyncio
async def test_no_date_rows_equal_the_dashboard_staff_table(db_session):
    w = await dashboard_world(db_session)
    async with client_for(w["master"].email) as c:
        dashboard = (await c.get(DASHBOARD_API)).json()
        performance = (await c.get(PERFORMANCE_API)).json()
    expected = {r["code"]: {k: r[k] for k in SHARED} for r in dashboard["staff"]}
    actual = {r["code"]: {k: r[k] for k in SHARED} for r in performance["rows"]}
    assert actual == expected and len(actual) == 3
    assert performance["unassigned"]["students"] == dashboard["unassigned_students"]
