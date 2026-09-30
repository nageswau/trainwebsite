"""ENH-030 -- GET/PUT /school/attendance (spec §5.1-5.2, AC01-AC07). Each test builds its own throwaway school."""

import json
import uuid
from datetime import date, timedelta

import pytest
from enh005_helpers import login, mk_school, move_student_directly
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api.schools import TIER_DENIED, _today_ist
from app.models import AuditLog, SchoolAttendanceRecord, SchoolStudent

URL = "/api/v1/school/attendance"
DAY = "2026-09-01"


async def _world(db, *, students: int = 3, **over) -> dict:
    """mk_school assigns only the first student to the teacher; here every student but the last is assigned (the last is the
    same-school, unassigned control)."""
    w = await mk_school(db, label="Att", students=students, **over)
    for s in w["students"][:-1]:
        s.assigned_teacher_user_id = w["teacher"].id
    await db.commit()
    w["mine"] = w["students"][:-1]
    w["unassigned"] = w["students"][-1]
    return w


def _marks(students, status="present"):
    return [{"student_id": str(s.id), "status": status} for s in students]


async def _rows(db, **where):
    stmt = select(SchoolAttendanceRecord)
    for key, value in where.items():
        stmt = stmt.where(getattr(SchoolAttendanceRecord, key) == value)
    return (await db.scalars(stmt.execution_options(populate_existing=True))).all()


async def _mark_audits(db, school_id):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(school_id)))


@pytest.mark.asyncio
async def test_teacher_marks_whole_class_in_one_call(client, db_session):  # AC01
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(w["mine"][1].id), "status": "late"}]
    response = await client.put(URL, json={"session_date": DAY, "records": records})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_date"] == DAY
    assert {s["id"]: s["status"] for s in body["students"]} == {str(w["mine"][0].id): "present", str(w["mine"][1].id): "late"}
    rows = await _rows(db_session, school_id=w["school"].id, session_date=date(2026, 9, 1))
    assert {(r.school_student_id, r.status) for r in rows} == {(w["mine"][0].id, "present"), (w["mine"][1].id, "late")}
    assert {r.marked_by_user_id for r in rows} == {w["teacher"].id}
    assert {r.school_id for r in rows} == {w["school"].id}


@pytest.mark.asyncio
async def test_remark_updates_never_duplicates_and_retry_is_harmless(client, db_session):  # AC02
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})).status_code == 200
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "absent")})).status_code == 200
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "absent")})).status_code == 200
    rows = {r.school_student_id: r.status for r in await _rows(db_session, school_id=w["school"].id, session_date=date(2026, 9, 1))}
    assert rows == {w["mine"][0].id: "absent", w["mine"][1].id: "present"}  # partial roster: the second student is untouched
    assert await _mark_audits(db_session, w["school"].id) == 3
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(w["school"].id)).order_by(AuditLog.created_at))).all()
    assert [a.metadata_json["changes"] for a in audits[1:]] == [[{"student_id": str(w["mine"][0].id), "from": "present", "to": "absent"}], []]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["unassigned", "other_school", "unknown", "moved_away"])
async def test_any_student_outside_the_class_rejects_the_whole_call(client, db_session, case):  # AC03
    w = await _world(db_session)
    other = await mk_school(db_session, admin=w["admin"], label="AttOther")
    if case == "moved_away":
        await move_student_directly(db_session, w["mine"][1], other["school"])
    outsider = {
        "unassigned": w["unassigned"].id,
        "other_school": other["students"][0].id,
        "unknown": uuid.uuid4(),
        "moved_away": w["mine"][1].id,
    }[case]
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(outsider), "status": "present"}]
    response = await client.put(URL, json={"session_date": DAY, "records": records})
    assert response.status_code == 403
    assert response.json()["detail"] == "One or more students are not assigned to you"
    assert await _rows(db_session, school_student_id=w["mine"][0].id) == []
    assert await _mark_audits(db_session, w["school"].id) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["coordinator", "principal", "parent"])
async def test_only_teachers_may_read_or_mark(client, db_session, role):  # AC04
    w = await _world(db_session)
    await login(client, w[role].email)
    assert (await client.get(URL)).status_code == 403
    response = await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    assert response.status_code == 403 and response.json()["detail"] == "Teacher role required"
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_future_date_is_refused(client, db_session):  # AC05
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    tomorrow = (_today_ist() + timedelta(days=1)).isoformat()
    put = await client.put(URL, json={"session_date": tomorrow, "records": _marks(w["mine"])})
    assert put.status_code == 422 and put.json()["detail"] == "Attendance cannot be marked for a future date"
    get = await client.get(URL, params={"date": tomorrow})
    assert get.status_code == 422
    assert (await client.put(URL, json={"session_date": _today_ist().isoformat(), "records": _marks(w["mine"])})).status_code == 200


@pytest.mark.asyncio
async def test_invalid_bodies_are_422_and_write_nothing(client, db_session):  # AC05
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    sid = str(w["mine"][0].id)
    for body in (
        {"session_date": DAY, "records": [{"student_id": sid, "status": "sick"}]},
        {"session_date": DAY, "records": []},
        {"session_date": DAY, "records": [{"student_id": sid, "status": "present"}, {"student_id": sid, "status": "absent"}]},
        {"session_date": DAY, "records": _marks(w["mine"]), "school_id": str(w["school"].id)},
    ):
        assert (await client.put(URL, json=body)).status_code == 422
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_expired_partnership_is_denied_with_its_audit_row(client, db_session):  # AC06
    w = await _world(db_session, tier_valid_until=_today_ist() - timedelta(days=1))
    await login(client, w["teacher"].email)
    response = await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    assert response.status_code == 403 and "expired" in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(w["school"].id))) == 1
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_each_mark_writes_one_audit_row_with_a_tally(client, db_session):  # AC07
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(w["mine"][1].id), "status": "absent"}]
    assert (await client.put(URL, json={"session_date": DAY, "records": records})).status_code == 200
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(w["school"].id)))).one()
    assert audit.user_id == w["teacher"].id and audit.entity_type == "school"
    changes = sorted(
        [{"student_id": str(w["mine"][0].id), "from": None, "to": "present"}, {"student_id": str(w["mine"][1].id), "from": None, "to": "absent"}],
        key=lambda c: c["student_id"],
    )
    assert audit.metadata_json == {"session_date": DAY, "count": 2, "statuses": {"present": 1, "absent": 1}, "changes": changes}


@pytest.mark.asyncio
async def test_non_json_body_is_refused(client, db_session):  # spec §11 S4 (CSRF): a cross-site form can only send text/plain
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    body = json.dumps({"session_date": DAY, "records": _marks(w["mine"][:1])})
    response = await client.put(URL, content=body, headers={"Content-Type": "text/plain"})
    assert response.status_code == 422
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_roster_lists_only_assigned_students_with_saved_status(client, db_session):  # AC01 (read side)
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "excused")})
    body = (await client.get(URL, params={"date": DAY})).json()
    assert body["today"] == _today_ist().isoformat()
    assert {s["id"]: s["status"] for s in body["students"]} == {str(w["mine"][0].id): "excused", str(w["mine"][1].id): None}
    default = (await client.get(URL)).json()
    assert default["session_date"] == _today_ist().isoformat()


@pytest.mark.asyncio
async def test_roster_empty_for_teacher_without_students(client, db_session):  # Review Focus 3
    w = await mk_school(db_session, label="AttEmpty", students=0)
    await login(client, w["teacher"].email)
    response = await client.get(URL)
    assert response.status_code == 200 and response.json()["students"] == []


@pytest.mark.asyncio
async def test_mark_after_transfer_restamps_school(client, db_session):  # Review Focus 2
    w = await _world(db_session)
    old = await mk_school(db_session, admin=w["admin"], label="AttOld")
    student = w["mine"][0]
    db_session.add(SchoolAttendanceRecord(school_student_id=student.id, school_id=old["school"].id, session_date=date(2026, 9, 1), status="absent", marked_by_user_id=old["teacher"].id))
    await db_session.commit()
    await login(client, w["teacher"].email)
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks([student])})).status_code == 200
    rows = await _rows(db_session, school_student_id=student.id)
    assert [(r.school_id, r.status) for r in rows] == [(w["school"].id, "present")]


# --- Hardening (the ENH-004 promotion precedent, schools.py:1680-1705): scope inside the locking query, a bounded lock wait, and an
# audit row for a refused save. -----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refused_save_is_audited_with_counts_only(client, db_session):
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    response = await client.put(URL, json={"session_date": DAY, "records": _marks([w["mine"][0], w["unassigned"]])})
    assert response.status_code == 403
    denied = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.daily_attendance_denied", AuditLog.entity_id == str(w["school"].id)))).one()
    assert denied.outcome == "denied" and denied.user_id == w["teacher"].id
    assert denied.metadata_json == {"session_date": DAY, "requested": 2, "outside": 1}  # counts only: no student ids or names


@pytest.mark.asyncio
async def test_a_class_row_locked_elsewhere_is_a_409_and_writes_nothing(client, db_session, monkeypatch):
    w = await _world(db_session)
    school_id = w["school"].id  # read before the rollback below expires the loaded objects
    await login(client, w["teacher"].email)
    monkeypatch.setattr("app.api.school_attendance.ATTENDANCE_LOCK_TIMEOUT", "200ms")
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == w["mine"][0].id).with_for_update())  # e.g. a transfer approval
    try:
        response = await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    finally:
        await db_session.rollback()
    assert response.status_code == 409
    assert response.json()["detail"] == "This class's attendance is being changed elsewhere. Try again."
    assert await _rows(db_session, school_id=school_id) == []


@pytest.mark.asyncio
async def test_a_failed_commit_writes_nothing_and_is_logged(client, db_session, monkeypatch, caplog):
    """The marks and their audit row are one transaction: if the audit row cannot be written, no mark is kept either."""
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    monkeypatch.setattr("app.api.school_attendance.MARK_ACTION", "x" * 121)  # AuditLog.action is String(120): the commit fails
    with pytest.raises(DBAPIError):
        await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    assert await _rows(db_session, school_id=w["school"].id) == []
    failed = [r for r in caplog.records if r.getMessage() == "school_attendance_mark_failed"]
    assert len(failed) == 1 and failed[0].levelname == "ERROR"


@pytest.mark.asyncio
async def test_another_schools_locked_student_is_refused_at_once(client, db_session, monkeypatch):
    """Lock griefing: naming a student the teacher does not teach must never make the save wait on (or lock) that student's row."""
    w = await _world(db_session)
    other = await mk_school(db_session, admin=w["admin"], label="AttLocked")
    await login(client, w["teacher"].email)
    monkeypatch.setattr("app.api.school_attendance.ATTENDANCE_LOCK_TIMEOUT", "200ms")
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == other["students"][0].id).with_for_update())
    try:
        response = await client.put(URL, json={"session_date": DAY, "records": _marks([w["mine"][0], other["students"][0]])})
    finally:
        await db_session.rollback()
    assert response.status_code == 403 and response.json()["detail"] == "One or more students are not assigned to you"
