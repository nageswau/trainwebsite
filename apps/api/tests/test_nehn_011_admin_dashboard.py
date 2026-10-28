"""nehn-011 (DEC-SCOPE-311) -- the admin dashboard's training tiles: enrolments (active, completed, dropped), average progress, at-risk
students, course fees collected / pending and a course-wise mini table, each computed from the nehn-010 report it links to (AC1).
Overseas admin gets no training block (AC2); the fee figures need `field.financial.view` (AC3). The shared test DB holds other rows,
so each tile is compared with the linked report read by the same user at the same moment, and the hand-counted figures are checked
through a course filter on the nehn-010 fixture."""

import pytest

from app.models import UserPermissionOverride
from app.services.reports import registry
from app.services.reports.training import dashboard_tiles
from tests.bdm001_helpers import login, make_user
from tests.test_nehn_010_training_reports import _fixture, _read

pytestmark = pytest.mark.asyncio
DASHBOARD = "/api/v1/admin/dashboard"
EXISTING = {"users", "enquiries", "revenue", "programs", "universities", "overseas_applications", "expired_welcome_links"}


async def _all(client, report, **params) -> list[dict]:
    """Every row of a report (paged through)."""
    rows, page = [], 1
    while True:
        body = await _read(client, report, page=page, **params)
        rows += body["items"]
        if len(rows) >= body["total"] or not body["items"]:
            return rows
        page += 1


async def _training(client) -> dict:
    response = await client.get(DASHBOARD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert EXISTING <= set(body)
    return body["training"]


async def test_the_tiles_equal_the_totals_of_their_linked_reports(client, db_session):
    await _fixture(db_session)
    await login(client, await make_user(db_session, "super_admin", "global"))
    tiles = await _training(client)
    courses = await _all(client, "courses")
    for key in ("enrolments", "active", "completed", "dropped"):
        assert tiles[key] == sum(row[key] for row in courses), key
    assert tiles["completed"] == (await _read(client, "completions"))["total"]
    assert tiles["fees_collected"] == pytest.approx(sum(float(row["revenue"] or 0) for row in courses))
    assert tiles["fees_pending"] == pytest.approx(sum(float(row["pending_fees"] or 0) for row in courses))
    assert tiles["at_risk_threshold"] == 75
    assert tiles["at_risk"] == (await _read(client, "attendance", attendance_below="75"))["total"]
    counted = [r for r in await _all(client, "student-courses") if r["status"] not in ("pending_consent", "rejected", "withdrawn", "dropped")]
    assert tiles["average_progress"] == pytest.approx(round(sum(r["progress"] for r in counted) / len(counted), 1), abs=0.051)
    table = tiles["courses"]
    assert table["total"] == len(courses) and table["items"] == courses[:5]  # QA-02: a five-row mini table
    assert [c["key"] for c in table["columns"]] == [c.key for c in registry.REPORTS["courses"].columns]


async def test_at_risk_counts_seats_on_the_course_below_the_threshold(client, db_session):
    """nehn-010 fixture: s1 has 66.67 % over 6 classes (at risk under 75, not under 60); s2 has none marked; s3 is dropped."""
    f = await _fixture(db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    course = str(f["program"].id)
    rows = (await _read(client, "attendance", course_id=course, attendance_below="75"))["items"]
    assert [(r["student"], r["batch"]) for r in rows] == [("Aaron N010", f["b1"].name)]
    assert (await _read(client, "attendance", course_id=course, attendance_below="60"))["items"] == []


@pytest.mark.parametrize("value", ["0", "101", "x", "7.5"])
async def test_attendance_below_must_be_a_whole_percent(client, db_session, value):
    await login(client, await make_user(db_session, "it_admin", "it"))
    response = await client.get("/api/v1/reports/attendance", params={"attendance_below": value})
    assert response.status_code == 422
    assert response.json()["detail"] == "Attendance below % must be a whole number from 1 to 100"


async def test_only_the_attendance_report_takes_attendance_below(client, db_session):
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get("/api/v1/reports/courses", params={"attendance_below": "75"})).status_code == 422


async def test_the_course_report_carries_pending_fees_as_financial(client, db_session):
    f = await _fixture(db_session)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert registry.REPORTS["courses"].classes == {"revenue": "financial", "pending_fees": "financial"}
    row = (await _read(client, "courses", course_id=str(f["program"].id)))["items"][0]
    assert float(row["revenue"]) == 1500 and float(row["pending_fees"]) == 1000


async def test_it_admin_sees_the_tiles_without_fee_figures_by_default(client, db_session):
    await _fixture(db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    tiles = await _training(client)
    assert "fees_collected" not in tiles and "fees_pending" not in tiles
    keys = [c["key"] for c in tiles["courses"]["columns"]]
    assert "revenue" not in keys and "pending_fees" not in keys
    assert all("revenue" not in r and "pending_fees" not in r for r in tiles["courses"]["items"])


async def test_a_financial_grant_brings_the_fee_figures_back(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    db_session.add(UserPermissionOverride(user_id=admin.id, resource="field.financial", action="view", effect="allow", reason="nehn-011 test"))
    await db_session.commit()
    await login(client, admin)
    tiles = await _training(client)
    assert {"fees_collected", "fees_pending"} <= set(tiles)


async def test_overseas_admin_gets_no_training_block(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    response = await client.get(DASHBOARD)
    assert response.status_code == 200
    assert "training" not in response.json() and EXISTING <= set(response.json())


@pytest.mark.parametrize("role", ["trainer", "it_student", "hr_team"])
async def test_a_role_without_dashboard_access_gets_403(client, db_session, role):
    await login(client, await make_user(db_session, role, "it"))
    assert (await client.get(DASHBOARD)).status_code == 403


async def test_a_trainer_less_scope_gives_zeros_and_no_average(db_session):
    """An empty scope (no rows at all) shows zeros and a missing average, never an error."""
    nobody = await make_user(db_session, "overseas_admin", "overseas")
    tiles = await dashboard_tiles(db_session, nobody, threshold=75)
    assert {k: tiles[k] for k in ("enrolments", "active", "completed", "dropped", "at_risk")} == dict.fromkeys(("enrolments", "active", "completed", "dropped", "at_risk"), 0)
    assert tiles["average_progress"] is None and tiles["courses"]["items"] == [] and tiles["courses"]["total"] == 0
