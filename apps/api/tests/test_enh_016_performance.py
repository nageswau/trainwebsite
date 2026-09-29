"""ENH-016 AC17: an endpoint's query count does not grow with the number of schools or students (spec §10), and its log line
carries ids and counts only, never a student's name (spec §12)."""

import logging
from contextlib import contextmanager

import pytest
from enh016_helpers import login, make_school, make_student
from sqlalchemy import event

from app.core.database import engine
from app.models import SchoolPsychometricRecord


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Same order-proofing as test_enh_003: an in-process Alembic run disables existing `app.*` loggers."""
    logging.getLogger("app.school.analytics").disabled = False
    yield


@contextmanager
def count_queries():
    counter = {"n": 0}

    def _count(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)


async def _seed(db, ctx, n):
    for i in range(n):
        s = await make_student(db, ctx, name=f"Kid Secretname {i}", grade_level=8 + i % 5)
        db.add(SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A", status="completed"))


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"])
async def test_admin_query_count_is_independent_of_school_count(client, db_session, path):
    first = await make_school(db_session)
    await _seed(db_session, first, 3)
    await db_session.commit()
    await login(client, first["super_admin"])
    with count_queries() as one:
        assert (await client.get(path)).status_code == 200
    for _ in range(4):
        await _seed(db_session, await make_school(db_session), 5)
    await db_session.commit()
    with count_queries() as five:
        assert (await client.get(path)).status_code == 200
    assert five["n"] == one["n"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/school/analytics/grade-performance", "/api/v1/school/analytics/student-development", "/api/v1/school/analytics/scorecards", "/api/v1/school/dashboard", "/api/v1/school/entitlements"],
)
async def test_school_query_count_is_independent_of_student_count(client, db_session, path, caplog):
    ctx = await make_school(db_session)
    await _seed(db_session, ctx, 1)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    with count_queries() as few:
        assert (await client.get(path)).status_code == 200
    await _seed(db_session, ctx, 20)
    await db_session.commit()
    with caplog.at_level(logging.INFO), count_queries() as many:
        assert (await client.get(path)).status_code == 200
    assert many["n"] == few["n"]
    assert "Secretname" not in caplog.text
    if "/analytics/" in path:
        assert "school_analytics_view" in caplog.text
