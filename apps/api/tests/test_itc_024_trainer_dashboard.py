"""itc-024 -- the trainer dashboard's widgets (DEC-SCOPE-355): today's classes, attendance completion, assessment completion and
at-risk students, filterable by batch (spec docs/superpowers/specs/2026-11-03-itc-024-trainer-dashboard-widgets-design.md).

Classes "held" are those whose start time has passed: the tests place held classes at 00:00-00:05 IST and not-yet-held ones at 23:58,
so they are deterministic except in the few minutes around midnight IST."""

import datetime
import uuid
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import (
    Assessment,
    AssessmentAttempt,
    Attendance,
    BatchTimetableCancellation,
    BatchTimetableSlot,
    Enrollment,
    LiveSession,
    StudentRiskFlag,
)
from tests.test_nehn_023_attendance_corrections import _login, _user, _world

IST = ZoneInfo("Asia/Kolkata")
DASHBOARD = "/api/v1/portal/it/trainer/dashboard"
NEW_TILES = ("Today's classes", "Attendance completion", "Assessment completion", "At-risk students")


def today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).astimezone(IST).date()


def at(day: datetime.date, hh: int, mm: int) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hh, mm), IST)


def tiles(data: dict) -> dict:
    return {m["label"]: m["value"] for m in data["metrics"]}


def panel(data: dict) -> dict:
    [found] = [p for p in data["panels"] if p["title"] == "Today's classes"]
    return found


def slot(batch, hh: int, mm: int, *, day: datetime.date | None = None, topic: str | None = None) -> BatchTimetableSlot:
    end = (datetime.datetime.combine(datetime.date.min, datetime.time(hh, mm)) + datetime.timedelta(minutes=1)).time()
    return BatchTimetableSlot(batch_id=batch.id, weekday=(day or today()).weekday(), start_time=datetime.time(hh, mm), end_time=end, mode="online", topic=topic)


@pytest_asyncio.fixture
async def world(db_session):
    """A trainer with one batch (one active student) and another trainer with their own batch; the _world absence rows removed."""
    trainer = await _user(db_session, "trainer", "Dashboard Trainer")
    other = await _user(db_session, "trainer", "Other Trainer")
    student, batch, existing = await _world(db_session, trainer=trainer)
    stranger, foreign, other_existing = await _world(db_session, trainer=other)
    batch.start_date = foreign.start_date = today() - datetime.timedelta(days=30)
    await db_session.delete(existing)
    await db_session.delete(other_existing)
    await db_session.commit()
    return {"trainer": trainer, "other": other, "student": student, "batch": batch, "stranger": stranger, "foreign": foreign}


async def dashboard(client, user, **params) -> dict:
    await _login(client, user)
    response = await client.get(DASHBOARD, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- the four widgets ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_trainer_with_no_classes_today_sees_no_classes_today_and_empty_figures(client, world):
    data = await dashboard(client, world["trainer"])
    assert data["metrics"][0]["label"] == "Assigned batches"  # trn-001 order kept
    t = tiles(data)
    assert all(label in t for label in NEW_TILES)
    assert t["Today's classes"] == 0 and t["Attendance completion"] == "—" and t["Assessment completion"] == "—" and t["At-risk students"] == 0
    assert panel(data) == {"title": "Today's classes", "items": [], "empty": "No classes today"}


@pytest.mark.asyncio
async def test_todays_classes_lists_timetable_classes_and_live_sessions_of_today_only(client, db_session, world):
    batch = world["batch"]
    early, late, cancelled = slot(batch, 0, 0, topic="Loops"), slot(batch, 23, 58), slot(batch, 10, 0)
    db_session.add_all([early, late, cancelled, slot(batch, 9, 0, day=today() + datetime.timedelta(days=1)), slot(world["foreign"], 0, 0)])
    await db_session.flush()
    db_session.add(BatchTimetableCancellation(slot_id=cancelled.id, occurs_on=today(), reason="Trainer unwell", cancelled_by_user_id=world["trainer"].id))
    db_session.add(LiveSession(batch_id=batch.id, trainer_id=world["trainer"].id, title="Doubt clearing", starts_at=at(today(), 0, 5), ends_at=at(today(), 0, 35), status="scheduled"))
    await db_session.commit()

    data = await dashboard(client, world["trainer"])
    assert tiles(data)["Today's classes"] == 3
    assert panel(data)["items"] == [
        f"00:00–00:01 · {batch.name} · Loops · Attendance not marked",
        f"00:05–00:35 · {batch.name} · Doubt clearing · Attendance not marked",
        f"23:58–23:59 · {batch.name} · Not started",
    ]


@pytest.mark.asyncio
async def test_attendance_completion_counts_held_classes_whose_batch_marked_today(client, db_session, world):
    second, _ = await _second_batch(db_session, world)
    db_session.add_all([slot(world["batch"], 0, 0), slot(world["batch"], 23, 58), slot(second, 0, 1)])
    await db_session.commit()
    assert tiles(await dashboard(client, world["trainer"]))["Attendance completion"] == "0% (0/2)"

    db_session.add(Attendance(student_id=world["student"].id, batch_id=world["batch"].id, session_date=today(), status="present"))
    await db_session.commit()
    data = await dashboard(client, world["trainer"])
    assert tiles(data)["Attendance completion"] == "50% (1/2)"  # the 23:58 class is not held yet
    assert panel(data)["items"][0].endswith("· Attendance marked")


@pytest.mark.asyncio
async def test_assessment_completion_counts_active_students_attempts_on_due_counted_assessments(client, db_session, world):
    batch, student = world["batch"], world["student"]
    peer = await _user(db_session, "it_student", "Peer")
    gone = await _user(db_session, "it_student", "Dropped")
    db_session.add_all([
        Enrollment(student_id=peer.id, batch_id=batch.id, enrollment_code=f"I024-{uuid.uuid4().hex[:10]}", status="active", progress_percent=0),
        Enrollment(student_id=gone.id, batch_id=batch.id, enrollment_code=f"I024-{uuid.uuid4().hex[:10]}", status="dropped", progress_percent=0),
    ])  # fmt: skip
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    due = Assessment(batch_id=batch.id, title="Quiz 1", scheduled_at=past, status="published")
    later = Assessment(batch_id=batch.id, title="Quiz 2", scheduled_at=past + datetime.timedelta(days=5), status="scheduled")
    draft = Assessment(batch_id=batch.id, title="Draft quiz", scheduled_at=past, status="draft")
    db_session.add_all([due, later, draft])
    await db_session.flush()
    db_session.add_all([
        AssessmentAttempt(assessment_id=due.id, student_id=student.id, status="graded", attempt_no=1),
        AssessmentAttempt(assessment_id=due.id, student_id=student.id, status="submitted", attempt_no=2),  # one pair, counted once
        AssessmentAttempt(assessment_id=due.id, student_id=peer.id, status="in_progress"),
        AssessmentAttempt(assessment_id=due.id, student_id=gone.id, status="graded"),
        AssessmentAttempt(assessment_id=draft.id, student_id=peer.id, status="graded"),
    ])  # fmt: skip
    await db_session.commit()
    assert tiles(await dashboard(client, world["trainer"]))["Assessment completion"] == "50% (1/2)"


@pytest.mark.asyncio
async def test_at_risk_counts_open_flags_of_own_batches_only(client, db_session, world):
    now = datetime.datetime.now(datetime.UTC)

    async def flag(student, batch, cleared=None):
        enrollment = await db_session.scalar(select(Enrollment.id).where(Enrollment.student_id == student.id, Enrollment.batch_id == batch.id))
        db_session.add(
            StudentRiskFlag(
                enrollment_id=enrollment, student_id=student.id, batch_id=batch.id, reasons=["attendance"], raised_at=now, cleared_at=cleared, clear_reason="recovered" if cleared else None
            )
        )

    await flag(world["student"], world["batch"])
    await flag(world["student"], world["batch"], cleared=now)
    await flag(world["stranger"], world["foreign"])
    await db_session.commit()
    assert tiles(await dashboard(client, world["trainer"]))["At-risk students"] == 1


# --- the batch filter ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_batch_filter_narrows_every_figure_and_the_table(client, db_session, world):
    second, _ = await _second_batch(db_session, world)
    db_session.add_all([slot(world["batch"], 0, 0), slot(second, 0, 1)])
    await db_session.commit()

    data = await dashboard(client, world["trainer"])
    assert tiles(data)["Assigned batches"] == 2 and tiles(data)["Today's classes"] == 2
    assert data["batch_filter"]["value"] is None
    assert sorted(o["label"] for o in data["batch_filter"]["options"]) == sorted([world["batch"].name, second.name])

    data = await dashboard(client, world["trainer"], batch=str(second.id))
    assert [r["batch"] for r in data["rows"]] == [second.name]
    assert tiles(data)["Assigned batches"] == 1 and tiles(data)["Today's classes"] == 1
    assert data["batch_filter"]["value"] == str(second.id) and len(data["batch_filter"]["options"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["not-a-uuid", "foreign", str(uuid.uuid4())])
async def test_a_batch_that_is_not_the_trainers_own_is_refused(client, world, value):
    await _login(client, world["trainer"])
    response = await client.get(DASHBOARD, params={"batch": str(world["foreign"].id) if value == "foreign" else value})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose one of your batches"


@pytest.mark.asyncio
async def test_the_batch_filter_is_refused_outside_the_trainer_dashboard(client, world):
    await _login(client, world["trainer"])
    response = await client.get("/api/v1/portal/it/trainer/assignments", params={"batch": str(world["batch"].id)})
    assert response.status_code == 422
    await _login(client, world["student"])
    response = await client.get("/api/v1/portal/it/student/dashboard", params={"batch": str(world["batch"].id)})
    assert response.status_code == 422
    assert response.json()["detail"] == "The batch filter applies to the trainer dashboard only"


@pytest.mark.asyncio
async def test_a_student_still_cannot_open_the_trainer_dashboard(client, world):
    await _login(client, world["student"])
    assert (await client.get(DASHBOARD)).status_code == 403


async def _second_batch(db_session, world):
    student, batch, existing = await _world(db_session, trainer=world["trainer"])
    batch.start_date = world["batch"].start_date
    await db_session.delete(existing)
    await db_session.commit()
    return batch, student
