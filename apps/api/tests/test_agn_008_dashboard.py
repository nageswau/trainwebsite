"""AGN-008 browser QA8-10 -- the agent dashboard leaves withdrawn applications out and shows readable stage labels."""

import pytest
import pytest_asyncio

from app.services.agent_applications import stage_label
from tests.agn001_helpers import client_for
from tests.agn008_helpers import agency_world, mk_application

DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    m, u, r = w["master"], w["university"], w["record"]
    await mk_application(db_session, agent=m, university=u, record=r, status="university_selection", intake="D1")
    await mk_application(db_session, agent=m, university=u, record=r, status="withdrawn", intake="D2")
    await mk_application(db_session, agent=m, university=u, record=r, status="university_review", intake="D3")  # legacy value
    return w


@pytest.mark.parametrize(
    ("raw", "label"),
    [("university_selection", "University selection"), ("withdrawn", "Withdrawn"), ("university_review", "University review"), ("enquiry", "Enquiry"), ("visa_documentation", "Visa documentation")],
)
def test_stage_label(raw, label):
    assert stage_label(raw) == label


@pytest.mark.asyncio
async def test_dashboard_excludes_withdrawn_and_shows_readable_status(world):
    async with client_for(world["master"].email) as c:
        body = (await c.get(DASHBOARD)).json()
    assert {m["label"]: m["value"] for m in body["metrics"]}["Applications"] == 2
    assert sorted(r["status"] for r in body["rows"]) == ["University review", "University selection"]


@pytest.mark.asyncio
async def test_dashboard_for_staff_applies_the_same_rule(world):
    async with client_for(world["staff"]["user"].email) as c:
        body = (await c.get(DASHBOARD)).json()
    assert {m["label"]: m["value"] for m in body["metrics"]}["Applications"] == 2
    assert sorted(r["status"] for r in body["rows"]) == ["University review", "University selection"]
