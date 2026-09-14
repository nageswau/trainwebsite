"""STU-006 -- Attendance and progress view (PRD-STU-006 + PRD-STU-007).

The read-only attendance list itself (`GET /workflows/it/student/attendance`) and its
RBAC already had coverage from TRN-008's test file. The real gap this feature closes:
PRD-STU-007 folds "module/course completion percentage and outstanding blockers (e.g.
unfinished assignments)" into this same feature, and the student-facing attendance
portal section (`GET /portal/it/student/attendance`) showed neither before this change
-- only the bare session list and correction requests. Covers the added progress %,
attendance %, and outstanding-blockers panel, plus STU-006-AC02 (no session marked yet
must never read as "absent") and STU-006-AC03 (resource-scope: self only).
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Assignment, Attendance, Batch, Enrollment, Program, Submission, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Progress Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session) -> User:
    student = User(
        email=f"progress-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Progress Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_batch(db_session, trainer: User) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"STU-006 Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_attendance_view_reports_progress_and_outstanding_blockers(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active", progress_percent=40))
    db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date.today() - datetime.timedelta(days=2), status="present"))
    db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date.today() - datetime.timedelta(days=1), status="absent"))
    due = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)
    unfinished = Assignment(batch_id=batch.id, title=f"Unfinished Assignment {uuid.uuid4().hex[:6]}", description="Do it", assignment_type="assignment", due_date=due, max_score=100, published=True)
    done = Assignment(batch_id=batch.id, title=f"Completed Assignment {uuid.uuid4().hex[:6]}", description="Do it", assignment_type="assignment", due_date=due, max_score=100, published=True)
    db_session.add_all([unfinished, done])
    await db_session.flush()
    db_session.add(Submission(assignment_id=done.id, student_id=student.id, answer="done", status="submitted"))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/student/attendance")
    assert response.status_code == 200
    body = response.json()

    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Attendance"] == "50%"
    assert metrics["Course progress"] == "40%"
    assert metrics["Outstanding blockers"] == 1

    blocker_panel = next(p for p in body["panels"] if p["title"] == "Outstanding blockers")
    assert any("Unfinished Assignment" in item for item in blocker_panel["items"])
    assert not any("Completed Assignment" in item for item in blocker_panel["items"])


@pytest.mark.asyncio
async def test_no_sessions_marked_yet_is_never_shown_as_absent(db_session, client):
    """STU-006-AC02: a session the trainer hasn't marked yet must read as
    not-yet-recorded, never be synthesized as an "absent" record."""
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active", progress_percent=0))
    await db_session.commit()

    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/student/attendance")
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert not any(row.get("status") == "absent" for row in body["rows"])
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Attendance"] == "No sessions recorded yet"


@pytest.mark.asyncio
async def test_attendance_view_is_self_scoped(db_session, client):
    trainer = await _create_trainer(db_session)
    student_a = await _create_student(db_session)
    student_b = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student_a.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    db_session.add(Enrollment(student_id=student_b.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    db_session.add(Attendance(student_id=student_a.id, batch_id=batch.id, session_date=datetime.date.today(), status="present"))
    await db_session.commit()

    await _login(client, student_b.email)
    response = await client.get("/api/v1/portal/it/student/attendance")
    assert response.status_code == 200
    assert response.json()["rows"] == []


@pytest.mark.asyncio
async def test_attendance_view_rejects_non_student_role(db_session, client):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)
    response = await client.get("/api/v1/portal/it/student/attendance")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_attendance_view_requires_authentication(client):
    assert (await client.get("/api/v1/portal/it/student/attendance")).status_code == 401
