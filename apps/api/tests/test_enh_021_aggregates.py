"""ENH-021 -- internships in the dashboard, entitlements and 360° view (spec §5.3, I7, I8, AC21-5)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school

from app.api.schools import internship_progress
from app.models import PortfolioEntry


@pytest.mark.parametrize("statuses,expected", [
    ([], "not_started"), ([None], "not_started"), (["discontinued"], "not_started"), (["not_started", "in_progress"], "in_progress"),
    (["in_progress", "completed"], "completed"), ([None, "completed"], "completed"),
])
def test_best_progress_wins(statuses, expected):
    assert internship_progress(statuses) == expected


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E21-Agg", students=3)
    c, s = ctx["coordinator"], ctx["students"]
    for student, status in ((s[0], "completed"), (s[0], "in_progress"), (s[1], None)):
        db_session.add(PortfolioEntry(school_student_id=student.id, section="internship", title="I", organization="A", completion_status=status, created_by_user_id=c.id, updated_by_user_id=c.id))
    await db_session.commit()
    return ctx


@pytest.mark.asyncio
async def test_kpi_and_chart(client, world):
    await login(client, world["coordinator"].email)
    data = (await client.get("/api/v1/school/dashboard")).json()
    kpi = {k["key"]: k for k in data["school_crm_kpis"]}["internships"]
    assert kpi["tracked"] is True and kpi["value"] == 2
    assert data["internship_status"] == [
        {"status": "not_started", "count": 0}, {"status": "in_progress", "count": 1}, {"status": "completed", "count": 1},
        {"status": "discontinued", "count": 0}, {"status": "no_status", "count": 1},
    ]
    assert "internships" not in {c["key"] for c in data["untracked_charts"]}


@pytest.mark.asyncio
async def test_entitlement_usage_is_distinct_students(client, world):
    await login(client, world["coordinator"].email)
    services = {s["key"]: s for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert services["internships"]["used"] == 2


@pytest.mark.asyncio
async def test_360_programme_status(client, world):
    await login(client, world["coordinator"].email)
    for i, expected in ((0, "completed"), (1, "not_started"), (2, "not_started")):
        body = (await client.get(f"/api/v1/school/students/{world['students'][i].id}/360-view")).json()
        programmes = {p["key"]: p["status"] for p in body["tabs"]["edusphere_programs"]["data"]["programmes"]}
        assert programmes["internship"] == expected, i
