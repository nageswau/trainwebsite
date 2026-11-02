"""itc-021 -- approved leave, the attendance % policy, marked_by, the session link and audited corrections (DEC-SCOPE-349).

AC1 the % follows `certificate_rules.leave_policy` everywhere (seat/eligibility, batch progress, reports, portal, management KPIs);
AC2 an overwrite and an approved correction are audited before/after and record who marked; AC3 another batch's trainer is refused;
AC4 the rules API carries the policy (additive, backward compatible); AC5 a date's single live session is linked."""

import datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Attendance, AttendanceCorrection, AuditLog, CertificateRule, LiveSession, User
from app.services import management_training, training_progress
from tests.test_nehn_023_attendance_corrections import _login, _user, _world

ATTENDANCE = "/api/v1/workflows/it/trainer/attendance"
RULES = "/api/v1/workflows/it/certificates/rules"
FIRST = datetime.date(2026, 9, 1)


@pytest_asyncio.fixture
async def policy(db_session):
    """Sets the global leave policy for one test and puts the previous rule row back afterwards (the row is shared)."""
    rule = await db_session.get(CertificateRule, "it")
    saved = (rule.min_progress_percent, rule.min_attendance_percent, rule.leave_policy) if rule else None

    async def set_policy(value: str) -> None:
        current = await db_session.get(CertificateRule, "it", populate_existing=True)  # the API commits through its own session
        if not current:
            current = CertificateRule(division="it")
            db_session.add(current)
        current.leave_policy = value
        await db_session.commit()

    yield set_policy
    current = await db_session.get(CertificateRule, "it", populate_existing=True)
    if saved is None:
        if current:
            await db_session.delete(current)
    else:
        current.min_progress_percent, current.min_attendance_percent, current.leave_policy = saved
    await db_session.commit()


async def _eight_present_two_leave(db_session, trainer: User | None = None):
    """The backlog's + case: 8 present, 2 approved leave, 0 absent (the _world's one 'absent' row is moved off to present)."""
    student, batch, existing = await _world(db_session, trainer=trainer)
    existing.status = "present"
    for i in range(9):
        db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=FIRST + datetime.timedelta(days=i), status="present" if i < 7 else "excused"))
    await db_session.commit()
    return student, batch


# --- AC1: one policy, every reader ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("value", "expected"), [("attended", 100), ("excluded", 100), ("absent", 80)])
async def test_seat_and_seats_follow_the_leave_policy(db_session, policy, value, expected):
    student, batch = await _eight_present_two_leave(db_session)
    await policy(value)
    seat = await training_progress.seat(db_session, student.id, batch.id)
    assert float(seat["attendance_percent"]) == expected
    seats = await training_progress.seats(db_session, batch.id, [student.id])
    assert float(seats[student.id]["attendance_percent"]) == expected
    assert seats[student.id]["attendance_marked"] == 10  # "classes marked" stays the rows marked


@pytest.mark.asyncio
async def test_excluded_policy_leaves_leave_out_of_the_denominator_not_the_marked_count(db_session, policy):
    student, batch = await _eight_present_two_leave(db_session)
    db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=FIRST + datetime.timedelta(days=20), status="absent"))
    await db_session.commit()
    await policy("excluded")
    att = training_progress.attendance(student_id=student.id, batch_id=batch.id)
    row = (await db_session.execute(select(att.c.marked, att.c.excused, att.c.attended, att.c.counted))).one()
    assert tuple(row) == (11, 2, 8, 9)


@pytest.mark.asyncio
async def test_excluded_policy_with_only_leave_marked_is_no_percentage(db_session, policy):
    student, batch, existing = await _world(db_session, trainer=None)
    existing.status = "excused"
    await db_session.commit()
    await policy("excluded")
    assert (await training_progress.seat(db_session, student.id, batch.id))["attendance_percent"] is None


@pytest.mark.asyncio
async def test_certificate_eligibility_reads_the_policy(client, db_session, policy):
    trainer = await _user(db_session, "trainer", "Policy Trainer")
    student, batch = await _eight_present_two_leave(db_session, trainer)
    await policy("absent")
    await _login(client, trainer)
    response = await client.get(f"/api/v1/workflows/it/batches/{batch.id}/progress")
    assert response.status_code == 200, response.text
    row = next(s for s in response.json()["students"] if s["student_id"] == str(student.id))
    assert row["attendance_percent"] == 80


@pytest.mark.asyncio
async def test_student_portal_attendance_follows_the_policy_and_says_approved_leave(client, db_session, policy):
    student, _ = await _eight_present_two_leave(db_session)
    await policy("absent")
    await _login(client, student)
    body = (await client.get("/api/v1/portal/it/student/attendance")).json()
    assert {"label": "Attendance", "value": "80%"} in body["metrics"]
    assert "approved leave" in {row["status"] for row in body["rows"]}
    assert "excused" not in {row["status"] for row in body["rows"]}


@pytest.mark.asyncio
async def test_management_training_attendance_follows_the_policy(db_session, policy):
    trainer = await _user(db_session, "trainer", "KPI Trainer")
    student, batch = await _eight_present_two_leave(db_session, trainer)
    batch.start_date, batch.end_date = FIRST, FIRST + datetime.timedelta(days=60)
    await db_session.commit()
    await policy("absent")
    body = await management_training.dashboard(db_session, FIRST, FIRST + datetime.timedelta(days=60), datetime.datetime.now(datetime.UTC))
    row = next(t for t in body["trainers"] if t["id"] == trainer.id)
    assert row["attendance_pct"] == 80.0


# --- AC2/AC5: who marked, the session link, audited corrections -----------------------------------------------------------------
async def _attendance(db_session, student, batch, day):
    db_session.expunge_all()
    return await db_session.scalar(select(Attendance).where(Attendance.student_id == student.id, Attendance.batch_id == batch.id, Attendance.session_date == day))


@pytest.mark.asyncio
async def test_marking_records_who_marked_and_links_the_days_single_live_session(client, db_session):
    trainer = await _user(db_session, "trainer", "Mark Trainer")
    student, batch, _ = await _world(db_session, trainer=trainer)
    day = datetime.date(2026, 10, 21)
    starts = datetime.datetime.combine(day, datetime.time(19), ZoneInfo("Asia/Kolkata"))
    live = LiveSession(batch_id=batch.id, trainer_id=trainer.id, title="Class", starts_at=starts, status="scheduled")
    db_session.add(live)
    await db_session.commit()
    await _login(client, trainer)
    response = await client.post(ATTENDANCE, json={"batch_id": str(batch.id), "session_date": day.isoformat(), "records": [{"student_id": str(student.id), "status": "excused"}]})
    assert response.status_code == 201, response.text
    row = await _attendance(db_session, student, batch, day)
    assert (row.status, row.marked_by_id, row.session_id) == ("excused", trainer.id, live.id)


@pytest.mark.asyncio
async def test_a_day_without_one_live_session_has_no_link_and_an_overwrite_records_the_new_marker(client, db_session):
    trainer = await _user(db_session, "trainer", "Overwrite Trainer")
    admin = await _user(db_session, "it_admin", "Overwrite Admin")
    student, batch, existing = await _world(db_session, trainer=trainer)
    await _login(client, admin)
    response = await client.post(ATTENDANCE, json={"batch_id": str(batch.id), "session_date": "2026-10-20", "records": [{"student_id": str(student.id), "status": "excused"}]})
    assert response.status_code == 201, response.text
    row = await _attendance(db_session, student, batch, datetime.date(2026, 10, 20))
    assert (row.status, row.marked_by_id, row.session_id) == ("excused", admin.id, None)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "attendance.update", AuditLog.entity_id == str(existing.id)))
    assert audit.metadata_json["changes"] == {"status": ["absent", "excused"]}


@pytest.mark.asyncio
async def test_an_approved_correction_is_audited_before_and_after_and_records_the_reviewer(client, db_session):
    trainer = await _user(db_session, "trainer", "Review Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    correction = AttendanceCorrection(attendance_id=attendance.id, student_id=student.id, reason="I was on approved leave.", requested_status="excused")
    db_session.add(correction)
    await db_session.commit()
    await _login(client, trainer)
    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction.id}", json={"status": "approved"})
    assert response.status_code == 200, response.text
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "attendance.update", AuditLog.entity_id == str(attendance.id)))
    assert audit.user_id == trainer.id
    assert audit.metadata_json["changes"] == {"status": ["absent", "excused"]}
    assert audit.metadata_json["correction_id"] == str(correction.id)
    row = await _attendance(db_session, student, batch, attendance.session_date)
    assert (row.status, row.marked_by_id) == ("excused", trainer.id)


@pytest.mark.asyncio
async def test_a_rejected_correction_changes_nothing_and_writes_no_change_row(client, db_session):
    trainer = await _user(db_session, "trainer", "Reject Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    correction = AttendanceCorrection(attendance_id=attendance.id, student_id=student.id, reason="I was on approved leave.", requested_status="excused")
    db_session.add(correction)
    await db_session.commit()
    await _login(client, trainer)
    assert (await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction.id}", json={"status": "rejected"})).status_code == 200
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "attendance.update", AuditLog.entity_id == str(attendance.id))) is None
    row = await _attendance(db_session, student, batch, attendance.session_date)
    assert (row.status, row.marked_by_id) == ("absent", None)


@pytest.mark.asyncio
async def test_a_trainer_marking_another_batch_is_refused(client, db_session):
    owner = await _user(db_session, "trainer", "Owner Trainer")
    other = await _user(db_session, "trainer", "Other Trainer")
    student, batch, _ = await _world(db_session, trainer=owner)
    await _login(client, other)
    response = await client.post(ATTENDANCE, json={"batch_id": str(batch.id), "session_date": "2026-10-22", "records": [{"student_id": str(student.id), "status": "excused"}]})
    assert response.status_code == 403


# --- AC4: the rules API ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rules_carry_the_leave_policy_and_a_put_without_it_keeps_it(client, db_session, policy):
    admin = await _user(db_session, "it_admin", "Rules Admin")
    await policy("excluded")
    await _login(client, admin)
    assert (await client.get(RULES)).json()["leave_policy"] == "excluded"
    response = await client.put(RULES, json={"min_progress_percent": 90, "min_attendance_percent": 70})
    assert response.status_code == 200, response.text
    assert response.json() == {"min_progress_percent": 90, "min_attendance_percent": 70, "leave_policy": "excluded"}
    response = await client.put(RULES, json={"min_progress_percent": 90, "min_attendance_percent": 70, "leave_policy": "absent"})
    assert response.json()["leave_policy"] == "absent"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "certificate_rules.update", AuditLog.user_id == admin.id).order_by(AuditLog.created_at.desc()).limit(1))
    assert (audit.metadata_json["before"]["leave_policy"], audit.metadata_json["after"]["leave_policy"]) == ("excluded", "absent")


@pytest.mark.asyncio
async def test_an_unknown_policy_is_422_and_a_trainer_cannot_change_it(client, db_session, policy):
    await policy("attended")
    admin = await _user(db_session, "it_admin", "Rules Admin")
    await _login(client, admin)
    assert (await client.put(RULES, json={"min_progress_percent": 90, "min_attendance_percent": 70, "leave_policy": "ignore"})).status_code == 422
    trainer = await _user(db_session, "trainer", "Rules Trainer")
    await _login(client, trainer)
    assert (await client.put(RULES, json={"min_progress_percent": 90, "min_attendance_percent": 70, "leave_policy": "absent"})).status_code == 403
    assert (await client.get(RULES)).json()["leave_policy"] == "attended"


@pytest.mark.asyncio
async def test_trainer_portal_attendance_says_approved_leave(client, db_session):
    """Browser QA21-01: the trainer's Student Attendance table and pending-corrections panel showed the raw "excused"."""
    trainer = await _user(db_session, "trainer", "Portal Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    attendance.status = "excused"
    db_session.add(AttendanceCorrection(attendance_id=attendance.id, student_id=student.id, reason="Marked leave by mistake.", requested_status="present"))
    await db_session.commit()
    await _login(client, trainer)
    body = (await client.get("/api/v1/portal/it/trainer/attendance")).json()
    assert {row["status"] for row in body["rows"]} == {"approved leave"}
    assert "approved leave → present" in body["panels"][0]["items"][0]
    assert "excused" not in str(body)
