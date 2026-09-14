"""STU-003 -- Live class access.

Covers: a student sees only live sessions for their own enrolled batches, host_url is
never exposed to a student, and a session with no recording yet is represented cleanly
(not an error) -- STU-003-AC02's "accepted limitation, not a fault."
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, LiveSession, Program, User


async def _create_student(db_session) -> User:
    student = User(
        email=f"live-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Live Class Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_enrolled_batch_with_session(db_session, student: User, *, with_recording: bool) -> LiveSession:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Live Session Test Program {uuid.uuid4().hex[:6]}",
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
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    session = LiveSession(
        batch_id=batch.id,
        title=f"Week 1 Live Class {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        ends_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1, hours=1),
        provider="manual",
        meeting_url="https://meet.example.com/session-1",
        host_url="https://meet.example.com/host/session-1",
        recording_url="https://meet.example.com/recording-1" if with_recording else None,
        recording_status="available" if with_recording else "not_available",
        status="scheduled",
    )
    db_session.add(session)
    await db_session.commit()
    return session


async def _login(client, email: str):
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_sees_join_link_for_own_batch_session(client, db_session):
    student = await _create_student(db_session)
    session = await _create_enrolled_batch_with_session(db_session, student, with_recording=False)
    await _login(client, student.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    listed = next((s for s in response.json() if s["id"] == str(session.id)), None)
    assert listed is not None
    assert listed["meeting_url"] == "https://meet.example.com/session-1"


@pytest.mark.asyncio
async def test_host_url_is_never_exposed_to_a_student(client, db_session):
    student = await _create_student(db_session)
    session = await _create_enrolled_batch_with_session(db_session, student, with_recording=False)
    await _login(client, student.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    listed = next(s for s in response.json() if s["id"] == str(session.id))
    assert listed["host_url"] is None


@pytest.mark.asyncio
async def test_session_without_a_recording_is_represented_cleanly_not_an_error(client, db_session):
    student = await _create_student(db_session)
    session = await _create_enrolled_batch_with_session(db_session, student, with_recording=False)
    await _login(client, student.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    listed = next(s for s in response.json() if s["id"] == str(session.id))
    assert listed["recording_url"] is None
    assert listed["recording_status"] == "not_available"


@pytest.mark.asyncio
async def test_student_never_sees_another_students_batch_session(client, db_session):
    other_student = await _create_student(db_session)
    other_session = await _create_enrolled_batch_with_session(db_session, other_student, with_recording=False)

    unrelated_student = await _create_student(db_session)
    await _login(client, unrelated_student.email)

    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    assert all(s["id"] != str(other_session.id) for s in response.json())


@pytest.mark.asyncio
async def test_student_with_no_enrollment_sees_empty_list_not_an_error(client, db_session):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_live_sessions_endpoint_requires_authentication(client):
    assert (await client.get("/api/v1/communications/it/live-sessions")).status_code == 401
