"""ENH-030 -- GET/PUT /school/attendance (spec §5.1-5.2, AC01-AC07). Each test builds its own throwaway school."""

import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from enh005_helpers import login, mk_school, move_student_directly
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api.schools import TIER_DENIED, _today_ist
from app.models import AuditLog, SchoolAttendanceRecord, SchoolStudent, SchoolStudentTransferRequest

URL = "/api/v1/school/attendance"
DAY = "2026-09-01"
ENROLLED = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Alembic's env.py calls `logging.config.fileConfig`, which DISABLES loggers that already exist; an earlier test that migrates
    in-process (ENH-001's downgrade/upgrade cycle) would silence `app.school.attendance` and `caplog` would see nothing -- the
    order-dependence ENH-004/005 found. Production is unaffected (Alembic runs in its own process)."""
    logging.getLogger("app.school.attendance").disabled = False
    yield


async def _world(db, *, students: int = 3, **over) -> dict:
    """mk_school assigns only the first student to the teacher; here every student but the last is assigned (the last is the
    same-school, unassigned control)."""
    w = await mk_school(db, label="Att", students=students, **over)
    for s in w["students"][:-1]:
        s.assigned_teacher_user_id = w["teacher"].id
    for s in w["students"]:  # enrolled well before the past dates these tests mark (review I-3 enrolment rule)
        s.created_at = ENROLLED
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
async def test_new_school_mark_keeps_the_previous_schools_record(client, db_session):  # Review Focus 2; spec C1/AC10 (final review I1)
    """After a transfer each school keeps its own register for a day: the new school's mark never overwrites or re-stamps the old
    school's row, and its audit compares against its own register (so a first mark reads from None)."""
    w = await _world(db_session)
    old = await mk_school(db_session, admin=w["admin"], label="AttOld")
    student = w["mine"][0]
    db_session.add(SchoolAttendanceRecord(school_student_id=student.id, school_id=old["school"].id, session_date=date(2026, 9, 1), status="absent", marked_by_user_id=old["teacher"].id))
    await db_session.commit()
    await login(client, w["teacher"].email)
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks([student])})).status_code == 200
    rows = await _rows(db_session, school_student_id=student.id)
    assert sorted((str(r.school_id), r.status, r.marked_by_user_id) for r in rows) == sorted([(str(old["school"].id), "absent", old["teacher"].id), (str(w["school"].id), "present", w["teacher"].id)])
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(w["school"].id)))).one()
    assert audit.metadata_json["changes"] == [{"student_id": str(student.id), "from": None, "to": "present"}]


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
    # Spec §11 S6 (final review, logs): the DB error text carries the bound parameters -- student ids and their statuses -- so the
    # log line keeps only the error class and sqlstate, never the traceback or the statement.
    assert failed[0].exc_info is None
    fields = failed[0].__dict__["extra_fields"]
    assert fields["error"] == "DBAPIError" and fields["sqlstate"] == "22001"  # string_data_right_truncation (the 121-char action)
    assert not any(str(s.id) in repr(failed[0].__dict__) for s in w["mine"])


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


# --- Review I-3 (DEC-SCOPE-038, user-approved 2026-09-30): a past day lists and accepts only students enrolled at this school on
# that day. Enrolment at the current school begins at the latest approved transfer into it, else when the student was created there
# (both read on the school calendar, Asia/Kolkata). ------------------------------------------------------------------------------


async def _joined(db, student, when: datetime) -> None:
    student.created_at = when
    await db.commit()


@pytest.mark.asyncio
async def test_past_roster_lists_only_students_enrolled_that_day(client, db_session):
    w = await _world(db_session)
    late_joiner = w["mine"][1]
    await _joined(db_session, late_joiner, datetime(2026, 9, 10, 4, 0, tzinfo=UTC))  # 10 Sep 09:30 IST
    await login(client, w["teacher"].email)
    before = (await client.get(URL, params={"date": "2026-09-09"})).json()["students"]
    assert [s["id"] for s in before] == [str(w["mine"][0].id)]
    on_the_day = (await client.get(URL, params={"date": "2026-09-10"})).json()["students"]  # the joining day itself counts
    assert {s["id"] for s in on_the_day} == {str(w["mine"][0].id), str(late_joiner.id)}


@pytest.mark.asyncio
async def test_enrolment_day_uses_the_school_calendar(client, db_session):
    w = await _world(db_session)
    student = w["mine"][1]
    await _joined(db_session, student, datetime(2026, 9, 9, 20, 0, tzinfo=UTC))  # 10 Sep 01:30 IST: not enrolled on 9 Sep
    await login(client, w["teacher"].email)
    ids = [s["id"] for s in (await client.get(URL, params={"date": "2026-09-09"})).json()["students"]]
    assert str(student.id) not in ids


@pytest.mark.asyncio
async def test_past_save_refuses_a_student_not_yet_enrolled_and_writes_nothing(client, db_session):
    w = await _world(db_session)
    late_joiner = w["mine"][1]
    await _joined(db_session, late_joiner, datetime(2026, 9, 10, 4, 0, tzinfo=UTC))
    await login(client, w["teacher"].email)
    response = await client.put(URL, json={"session_date": "2026-09-05", "records": _marks(w["mine"])})
    assert response.status_code == 422
    assert response.json()["detail"] == "One or more students were not enrolled at your school on 05 Sep 2026"
    assert await _rows(db_session, school_id=w["school"].id) == []
    assert await _mark_audits(db_session, w["school"].id) == 0
    assert (await client.put(URL, json={"session_date": "2026-09-10", "records": _marks(w["mine"])})).status_code == 200


@pytest.mark.asyncio
async def test_a_transferred_in_student_counts_from_the_transfer_approval(client, db_session):
    w = await _world(db_session)
    old = await mk_school(db_session, admin=w["admin"], label="AttFrom")
    student = w["mine"][1]  # created (at the old school) on ENROLLED; moved in by a transfer approved on 20 Sep
    db_session.add(
        SchoolStudentTransferRequest(
            school_student_id=student.id,
            from_school_id=old["school"].id,
            to_school_id=w["school"].id,
            requested_by_user_id=w["coordinator"].id,
            filed_by_school_id=w["school"].id,
            status="approved",
            decided_by_user_id=w["admin"].id,
            decided_at=datetime(2026, 9, 20, 5, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()
    await login(client, w["teacher"].email)
    before = [s["id"] for s in (await client.get(URL, params={"date": "2026-09-19"})).json()["students"]]
    after = [s["id"] for s in (await client.get(URL, params={"date": "2026-09-20"})).json()["students"]]
    assert str(student.id) not in before and str(student.id) in after
    refused = await client.put(URL, json={"session_date": "2026-09-19", "records": _marks([student])})
    assert refused.status_code == 422
