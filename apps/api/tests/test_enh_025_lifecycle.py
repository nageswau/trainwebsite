"""ENH-025 -- year moves clear roll numbers but history keeps them; transfers clear section/roll (AC10)."""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_school
from sqlalchemy import delete, or_, update

from app.models import AcademicYear, SchoolStudent, SchoolStudentGradeHistory

PROMOTE = "/api/v1/school/students/promotions"
APPROVE = "/api/v1/overseas-admin/school-transfer-requests/{rid}/approve"


@pytest_asyncio.fixture
async def future_year(db_session):
    """An ACTIVE academic year dated far in the future, so it wins the current-year lookup without touching real
    years (same technique as test_enh_004's `future_years`), removed afterwards."""
    year = AcademicYear(label=f"enh025-{uuid.uuid4().hex[:8]}", start_date=date(9999, 4, 1), end_date=date(9999, 12, 30), status="active")
    db_session.add(year)
    await db_session.commit()
    year_id = year.id  # read before the teardown rollback expires the instance
    yield year
    await db_session.rollback()
    await db_session.execute(delete(SchoolStudentGradeHistory).where(or_(SchoolStudentGradeHistory.to_academic_year_id == year_id, SchoolStudentGradeHistory.from_academic_year_id == year_id)))
    await db_session.execute(update(SchoolStudent).where(SchoolStudent.academic_year_id == year_id).values(academic_year_id=None))
    await db_session.execute(delete(AcademicYear).where(AcademicYear.id == year_id))
    await db_session.commit()


@pytest_asyncio.fixture
async def world(db_session):
    w = await mk_school(db_session, label="L", students=3)
    for i, s in enumerate(w["students"]):
        s.section, s.roll_number = "A", str(i + 1)
    await db_session.commit()
    return w


@pytest.mark.asyncio
async def test_promote_and_hold_back_clear_roll_and_history_keeps_it(client, world, db_session, future_year):
    await login(client, world["coordinator"].email)
    a, b, _ = world["students"]
    r = await client.post(PROMOTE, json={"items": [{"student_id": str(a.id), "action": "promote"}, {"student_id": str(b.id), "action": "hold_back"}]})
    assert r.status_code == 200, r.text
    assert {x["status"] for x in r.json()["results"]} == {"promoted", "held_back"}
    for s in (a, b):
        fresh = await db_session.get(SchoolStudent, s.id, populate_existing=True)
        assert fresh.roll_number is None and fresh.section == "A"
    history = (await client.get(f"/api/v1/school/students/{a.id}/grade-history")).json()["history"][0]
    assert history["from"]["section"] == "A" and history["from"]["roll_number"] == "1"
    assert history["to"]["section"] == "A" and history["to"]["roll_number"] is None
    held = (await client.get(f"/api/v1/school/students/{b.id}/grade-history")).json()["history"][0]
    assert held["from"]["roll_number"] == "2"


@pytest.mark.asyncio
async def test_untouched_students_keep_their_roll(client, world, db_session, future_year):
    await login(client, world["coordinator"].email)
    await client.post(PROMOTE, json={"items": [{"student_id": str(world["students"][0].id), "action": "promote"}]})
    third = await db_session.get(SchoolStudent, world["students"][2].id, populate_existing=True)
    assert third.roll_number == "3"


@pytest.mark.asyncio
async def test_transfer_approval_clears_section_and_roll(client, db_session, world):
    b = await mk_school(db_session, label="LB", students=0)
    kid = world["students"][0]
    request = await mk_request(db_session, kid, from_school=world["school"], to_school=b["school"], filed_by_school=world["school"], requester=world["coordinator"])
    await login(client, world["admin"].email)
    r = await client.post(APPROVE.format(rid=request.id))
    assert r.status_code == 200, r.text
    fresh = await db_session.get(SchoolStudent, kid.id, populate_existing=True)
    assert fresh.school_id == b["school"].id
    assert fresh.section is None and fresh.roll_number is None
