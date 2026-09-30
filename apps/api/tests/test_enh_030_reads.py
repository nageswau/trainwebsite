"""ENH-030 -- where a mark is read (spec §5.3, AC08-AC11)."""

from datetime import date, timedelta

import pytest
from enh005_helpers import login, mk_school, mk_staff, mk_student, move_student_directly
from sqlalchemy import select

from app.models import SchoolAttendanceRecord

URL = "/api/v1/school/attendance"
ZERO = {"present": 0, "absent": 0, "late": 0, "excused": 0}


async def _marked_world(client, db):
    """Student 0 (assigned to the teacher, linked to the parent) marked on two days by the real endpoint."""
    w = await mk_school(db, label="AttRead", students=2)
    await login(client, w["teacher"].email)
    sid = str(w["students"][0].id)
    for day, status in (("2026-09-01", "present"), ("2026-09-02", "late")):
        assert (await client.put(URL, json={"session_date": day, "records": [{"student_id": sid, "status": status}]})).status_code == 200
    return w


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["parent", "teacher", "coordinator", "principal"])
async def test_overview_carries_daily_attendance_for_every_reader(client, db_session, role):  # AC08
    w = await _marked_world(client, db_session)
    await login(client, w[role].email)
    body = (await client.get(f"/api/v1/school/students/{w['students'][0].id}/overview")).json()
    assert body["daily_attendance"] == {
        "counts": {"present": 1, "absent": 0, "late": 1, "excused": 0},
        "recent": [{"session_date": "2026-09-02", "status": "late"}, {"session_date": "2026-09-01", "status": "present"}],
    }


@pytest.mark.asyncio
async def test_unmarked_student_has_zero_counts(client, db_session):  # AC08
    w = await _marked_world(client, db_session)
    await login(client, w["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{w['students'][1].id}/overview")).json()
    assert body["daily_attendance"] == {"counts": ZERO, "recent": []}


@pytest.mark.asyncio
async def test_recent_is_capped_at_30_newest_first(client, db_session):  # C3
    w = await mk_school(db_session, label="AttCap")
    s = w["students"][0]
    for d in range(35):
        db_session.add(SchoolAttendanceRecord(school_student_id=s.id, school_id=w["school"].id, session_date=date(2026, 9, 1) - timedelta(days=d), status="present", marked_by_user_id=w["teacher"].id))
    await db_session.commit()
    await login(client, w["coordinator"].email)
    daily = (await client.get(f"/api/v1/school/students/{s.id}/overview")).json()["daily_attendance"]
    assert len(daily["recent"]) == 30 and daily["counts"]["present"] == 30
    dates = [r["session_date"] for r in daily["recent"]]
    assert dates[0] == "2026-09-01" and dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_360_attendance_tab_shows_daily_and_drops_the_enh030_note(client, db_session):  # AC09
    w = await _marked_world(client, db_session)
    await login(client, w["teacher"].email)
    tab = (await client.get(f"/api/v1/school/students/{w['students'][0].id}/360-view")).json()["tabs"]["attendance"]
    assert tab["status"] == "has_data" and tab["count"] == 2 and tab["not_tracked"] == []
    assert [r["status"] for r in tab["data"]["daily"]["recent"]] == ["late", "present"]
    assert tab["data"]["activities"] == [] and tab["data"]["skill_sessions"] == []


@pytest.mark.asyncio
async def test_360_fresh_student_attendance_stays_empty_and_service_roles_restricted(client, db_session):  # AC09
    w = await mk_school(db_session, label="AttFresh")
    fresh = await mk_student(db_session, w["school"], w["coordinator"], "Fresh")
    await db_session.commit()
    await login(client, w["coordinator"].email)
    tab = (await client.get(f"/api/v1/school/students/{fresh.id}/360-view")).json()["tabs"]["attendance"]
    assert tab["status"] == "empty" and tab["count"] == 0 and tab["not_tracked"] == []
    staff = await mk_staff(db_session, w["school"], w["admin"], role="academic_team")
    await login(client, staff.email)
    tab = (await client.get(f"/api/v1/school/students/{fresh.id}/360-view")).json()["tabs"]["attendance"]
    assert tab == {"status": "restricted", "count": None, "not_tracked": [], "data": {}}


@pytest.mark.asyncio
async def test_after_transfer_new_school_does_not_see_old_records(client, db_session):  # AC10
    w = await _marked_world(client, db_session)
    new = await mk_school(db_session, admin=w["admin"], label="AttNew")
    student = w["students"][0]
    await move_student_directly(db_session, student, new["school"])
    await login(client, new["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{student.id}/overview")).json()
    assert body["daily_attendance"] == {"counts": ZERO, "recent": []}
    kept = (await db_session.scalars(select(SchoolAttendanceRecord).where(SchoolAttendanceRecord.school_student_id == student.id))).all()
    assert len(kept) == 2  # data preserved


@pytest.mark.asyncio
async def test_dashboard_and_reports_attendance_are_unchanged(client, db_session):  # AC11
    w = await _marked_world(client, db_session)
    await login(client, w["coordinator"].email)
    for path in ("/api/v1/school/dashboard", "/api/v1/school/reports"):
        body = (await client.get(path)).json()
        assert body["attendance"] == {"present": 0, "total": 0}, path  # activity attendance only
