"""AGN-010 AC05 -- the agent Offers count (O5): stage `offer` or later (legacy values included) OR an offer recorded, on the
dashboard (new KPI, after Pending actions) and the Reports row (the §0 defect: it counted only offer_received/accepted)."""

from datetime import date

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn008_helpers import agency_world, mk_application

DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"
REPORTS = "/api/v1/portal/overseas/agent/reports"
OFFERED = {"offer_type": "unconditional", "offer_date": date(2026, 9, 1)}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    for status, fields in [
        ("offer", {}),
        ("visa_documentation", {}),
        ("enrolled", {}),
        ("offer_received", {}),  # legacy free text
        ("withdrawn", OFFERED),  # withdrawn after its offer: still an offer received
        ("withdrawn", {}),
        ("enquiry", {}),
        ("university_selection", {}),
    ]:
        await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status=status, **fields)
    return w


async def _get(email, url) -> dict:
    async with client_for(email) as c:
        response = await c.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def _metric(payload) -> int:
    return {m["label"]: m["value"] for m in payload["metrics"]}["Offers"]


def _report(payload) -> int:
    return next(r["value"] for r in payload["rows"] if r["metric"] == "Offers")


@pytest.mark.asyncio
async def test_master_dashboard_and_reports_count_offers_by_stage_or_offer_record(world):
    dashboard = await _get(world["master"].email, DASHBOARD)
    assert [m["label"] for m in dashboard["metrics"]][:4] == ["Students", "Applications", "Pending actions", "Offers"]
    assert _metric(dashboard) == 5
    assert _report(await _get(world["master"].email, REPORTS)) == 5


@pytest.mark.asyncio
async def test_staff_count_only_their_students_offers(world):
    assert _metric(await _get(world["staff"]["user"].email, DASHBOARD)) == 5
    assert _metric(await _get(world["other_staff"]["user"].email, DASHBOARD)) == 0
