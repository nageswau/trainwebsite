"""itc-023 -- at-risk thresholds per programme, the daily flag sweep and its alerts (DEC-SCOPE-352).

AC1 a flag is raised and cleared on threshold crossings (history kept); AC2 one alert per transition; AC3 thresholds are per programme;
AC4 too few sessions never flags on attendance; AC5 the assessment-average and consecutive-absence criteria; AC6 the API (admin-only
thresholds, scoped flag reads)."""

import datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models import Assessment, AssessmentAttempt, Attendance, AuditLog, ItRiskThreshold, ItStudentCounselor, Notification, StudentRiskFlag, User
from app.services import it_at_risk
from tests.test_nehn_023_attendance_corrections import _login, _user, _world

NOW = datetime.datetime(2026, 11, 2, 1, 30, tzinfo=datetime.UTC)
FIRST = datetime.date(2026, 9, 1)
THRESHOLDS = "/api/v1/admin/it/risk-thresholds"
FLAGS = "/api/v1/it/at-risk"


@pytest_asyncio.fixture
async def world(db_session):
    """A student in an active batch with a trainer and a linked counselor; the _world's lone 'absent' row is removed."""
    trainer = await _user(db_session, "trainer", "Risk Trainer")
    counselor = await _user(db_session, "counselor", "Risk Counselor")
    admin = await _user(db_session, "it_admin", "Risk Admin")
    student, batch, existing = await _world(db_session, trainer=trainer)
    await db_session.delete(existing)
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    await db_session.commit()
    return {"student": student, "batch": batch, "trainer": trainer, "counselor": counselor, "admin": admin}


async def mark(db, w, statuses: str, start: int = 0) -> None:
    """One attendance row per character from FIRST+start: P present, A absent, L late, E approved leave."""
    names = {"P": "present", "A": "absent", "L": "late", "E": "excused"}
    for i, ch in enumerate(statuses):
        day = FIRST + datetime.timedelta(days=start + i)
        await db.execute(delete(Attendance).where(Attendance.student_id == w["student"].id, Attendance.batch_id == w["batch"].id, Attendance.session_date == day))
        db.add(Attendance(student_id=w["student"].id, batch_id=w["batch"].id, session_date=day, status=names[ch]))
    await db.commit()


async def thresholds(db, w, **values) -> None:
    row = await db.get(ItRiskThreshold, w["batch"].program_id, populate_existing=True)
    if row is None:
        row = ItRiskThreshold(program_id=w["batch"].program_id)
        db.add(row)
    for key, value in {"min_attendance_percent": None, "min_assessment_percent": None, "max_consecutive_absences": None, "min_sessions": 3, **values}.items():
        setattr(row, key, value)
    await db.commit()


async def flags(db, w) -> list[StudentRiskFlag]:
    return list(await db.scalars(select(StudentRiskFlag).where(StudentRiskFlag.student_id == w["student"].id).order_by(StudentRiskFlag.raised_at).execution_options(populate_existing=True)))


async def notices(db, user: User) -> list[str]:
    return list(await db.scalars(select(Notification.event_type).where(Notification.user_id == user.id).order_by(Notification.created_at)))


async def sweep(db, now=NOW) -> dict:
    return await it_at_risk.sweep(db, now=now)


# --- AC1/AC2: raise once, clear once ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_attendance_below_the_minimum_raises_one_flag_and_alerts_student_trainer_and_counselor_once(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)  # 17/25 = 68 %, the absences first (no trailing run)
    await sweep(db_session)
    [flag] = await flags(db_session, world)
    assert flag.cleared_at is None and flag.reasons == ["attendance"] and float(flag.attendance_percent) == 68
    assert await notices(db_session, world["student"]) == ["it.training.check_in"]
    assert await notices(db_session, world["trainer"]) == ["it.training.at_risk"]
    assert await notices(db_session, world["counselor"]) == ["it.training.at_risk"]

    await sweep(db_session, NOW + datetime.timedelta(days=1))  # still below: no new flag, no new alert (AC2)
    assert len(await flags(db_session, world)) == 1
    assert await notices(db_session, world["counselor"]) == ["it.training.at_risk"]


@pytest.mark.asyncio
async def test_recovering_clears_the_flag_alerts_once_and_keeps_history(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    await mark(db_session, world, "P" * 15, start=25)  # 32/40 = 80 %
    await sweep(db_session, NOW + datetime.timedelta(days=1))
    [flag] = await flags(db_session, world)
    assert flag.cleared_at is not None and flag.clear_reason == "recovered" and flag.reasons == ["attendance"]  # history keeps why
    for who in ("student", "trainer", "counselor"):
        assert (await notices(db_session, world[who]))[-1] == "it.training.back_on_track"
    await sweep(db_session, NOW + datetime.timedelta(days=2))
    assert await notices(db_session, world["student"]) == ["it.training.check_in", "it.training.back_on_track"]

    await mark(db_session, world, "A" * 20, start=40)  # falls again: a second flag, the first kept as history
    await sweep(db_session, NOW + datetime.timedelta(days=3))
    assert [f.cleared_at is None for f in await flags(db_session, world)] == [False, True]


@pytest.mark.asyncio
async def test_notices_carry_no_figures(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    bodies = list(await db_session.scalars(select(Notification.body).where(Notification.user_id.in_([world["student"].id, world["counselor"].id]))))
    assert bodies and not any(ch.isdigit() for body in bodies for ch in body)


# --- AC3/AC4/AC5 -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_programme_without_thresholds_is_not_monitored(db_session, world):
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    assert await flags(db_session, world) == []
    await thresholds(db_session, world)  # a row with every criterion off is "not monitored" too
    await sweep(db_session)
    assert await flags(db_session, world) == []


@pytest.mark.asyncio
async def test_too_few_sessions_never_flags_on_attendance(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75, min_sessions=3)
    await mark(db_session, world, "AP")
    await sweep(db_session)
    assert await flags(db_session, world) == []
    await mark(db_session, world, "P", start=2)  # 3 sessions, 67 %
    await sweep(db_session)
    assert [f.reasons for f in await flags(db_session, world)] == [["attendance"]]


@pytest.mark.asyncio
async def test_the_leave_policy_applies_to_the_attendance_criterion(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "PPPEE")  # leave counts as attended under the default policy -> 100 %
    await sweep(db_session)
    assert await flags(db_session, world) == []


@pytest.mark.asyncio
async def test_a_low_assessment_average_raises_its_own_reason(db_session, world):
    await thresholds(db_session, world, min_assessment_percent=60)
    for best, other in ((40, 30), (50, None)):
        test = Assessment(batch_id=world["batch"].id, title="Quiz", scheduled_at=NOW, status="published")
        db_session.add(test)
        await db_session.flush()
        for no, pct in enumerate(p for p in (best, other) if p is not None):
            db_session.add(AssessmentAttempt(assessment_id=test.id, student_id=world["student"].id, attempt_no=no + 1, status="graded", percentage=pct))
    await db_session.commit()
    await sweep(db_session)
    [flag] = await flags(db_session, world)
    assert flag.reasons == ["assessment"] and float(flag.assessment_percent) == 45  # mean of the best attempts (40, 50)


@pytest.mark.asyncio
async def test_consecutive_absences_raise_their_own_reason_and_late_breaks_the_run(db_session, world):
    await thresholds(db_session, world, max_consecutive_absences=3)
    await mark(db_session, world, "PPPAALAA")
    await sweep(db_session)
    assert await flags(db_session, world) == []
    await mark(db_session, world, "A", start=8)
    await sweep(db_session)
    [flag] = await flags(db_session, world)
    assert flag.reasons == ["absences"] and flag.consecutive_absences == 3


@pytest.mark.asyncio
async def test_reason_changes_update_the_open_flag_silently(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75, max_consecutive_absences=3)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    await mark(db_session, world, "AAA", start=25)  # 17/28 = 61 % and 3 in a row
    await sweep(db_session, NOW + datetime.timedelta(days=1))
    [flag] = await flags(db_session, world)
    assert flag.reasons == ["attendance", "absences"]
    assert await notices(db_session, world["counselor"]) == ["it.training.at_risk"]


@pytest.mark.asyncio
async def test_switching_thresholds_off_closes_open_flags_without_alerts(db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    await thresholds(db_session, world)
    await sweep(db_session, NOW + datetime.timedelta(days=1))
    [flag] = await flags(db_session, world)
    assert flag.cleared_at is not None and flag.clear_reason == "stopped"
    assert await notices(db_session, world["student"]) == ["it.training.check_in"]


def test_beat_runs_the_sweep_daily_at_seven_ist():
    from app.worker import celery

    entry = celery.conf.beat_schedule["itc023-at-risk"]
    assert entry["task"] == "app.worker.flag_at_risk_students_task"
    assert (entry["schedule"].hour, entry["schedule"].minute) == ({1}, {30})


# --- AC6: the API -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_thresholds_api_is_admin_only_validated_and_audited(client, db_session, world):
    program_id = str(world["batch"].program_id)
    await _login(client, world["trainer"])
    assert (await client.get(THRESHOLDS)).status_code == 403
    assert (await client.put(f"{THRESHOLDS}/{program_id}", json={"min_attendance_percent": 75, "min_sessions": 3})).status_code == 403

    await _login(client, world["admin"])
    body = {"min_attendance_percent": 75, "min_assessment_percent": None, "max_consecutive_absences": 3, "min_sessions": 4}
    response = await client.put(f"{THRESHOLDS}/{program_id}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["min_attendance_percent"] == 75 and response.json()["min_sessions"] == 4
    listed = {row["program_id"]: row for row in (await client.get(THRESHOLDS)).json()}
    assert listed[program_id]["max_consecutive_absences"] == 3 and listed[program_id]["monitored"] is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.risk_thresholds.update", AuditLog.entity_id == program_id))
    assert audit.metadata_json["changes"]["min_attendance_percent"] == [None, 75]

    assert (await client.put(f"{THRESHOLDS}/{program_id}", json={**body, "min_attendance_percent": 101})).status_code == 422
    assert (await client.put(f"{THRESHOLDS}/{program_id}", json={**body, "min_sessions": 0})).status_code == 422
    assert (await client.put(f"{THRESHOLDS}/{program_id}", json={**body, "extra": 1})).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.put(f"{THRESHOLDS}/{missing}", json=body)).status_code == 404


@pytest.mark.asyncio
async def test_flag_reads_are_scoped(client, db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    sid = str(world["student"].id)

    for who in ("admin", "counselor", "trainer"):
        await _login(client, world[who])
        response = await client.get(FLAGS, params={"student_id": sid})
        assert response.status_code == 200, (who, response.text)
        [item] = response.json()
        assert item["student"]["id"] == sid and item["reasons"] == ["attendance"] and item["cleared_at"] is None

    stranger_counselor, stranger_trainer = await _user(db_session, "counselor", "Other Counselor"), await _user(db_session, "trainer", "Other Trainer")
    for other in (stranger_counselor, stranger_trainer):
        await _login(client, other)
        assert (await client.get(FLAGS, params={"student_id": sid})).json() == []
    await _login(client, world["student"])
    assert (await client.get(FLAGS)).status_code == 403


@pytest.mark.asyncio
async def test_history_includes_cleared_flags_only_when_asked(client, db_session, world):
    await thresholds(db_session, world, min_attendance_percent=75)
    await mark(db_session, world, "AAAAAAAA" + "P" * 17)
    await sweep(db_session)
    await thresholds(db_session, world)
    await sweep(db_session)
    await _login(client, world["admin"])
    sid = str(world["student"].id)
    assert (await client.get(FLAGS, params={"student_id": sid})).json() == []
    [item] = (await client.get(FLAGS, params={"student_id": sid, "history": "true"})).json()
    assert item["clear_reason"] == "stopped"


@pytest.mark.asyncio
async def test_portal_headers_for_the_admin_at_risk_page_and_trainer_notifications(client, world):
    await _login(client, world["admin"])
    assert (await client.get("/api/v1/portal/it/admin/at-risk")).status_code == 200
    await _login(client, world["trainer"])
    assert (await client.get("/api/v1/portal/it/trainer/notifications")).status_code == 200
