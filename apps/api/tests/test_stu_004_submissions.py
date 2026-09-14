"""STU-004 -- Assignment submission.

Covers: on-time vs. late submission is flagged (STU-004-AC02, DATA_MODEL.md §4.2), a
student can only submit against their own enrolled batch's assignment, and resubmission
re-evaluates lateness.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Assignment, Batch, Enrollment, Program, Submission, User


async def _create_student(db_session) -> User:
    student = User(
        email=f"sub-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Submission Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_enrolled_assignment(db_session, student: User, *, due_offset: datetime.timedelta) -> Assignment:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Submission Test Program {uuid.uuid4().hex[:6]}",
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
    assignment = Assignment(
        batch_id=batch.id,
        title=f"Week 1 Assignment {uuid.uuid4().hex[:6]}",
        description="Complete the exercise.",
        due_date=datetime.datetime.now(datetime.UTC) + due_offset,
        max_score=100,
        assignment_type="assignment",
        submission_type="text_or_file",
        published=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    return assignment


async def _login(client, email: str):
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_on_time_submission_is_not_flagged_late(client, db_session):
    student = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, student, due_offset=datetime.timedelta(days=5))
    await _login(client, student.email)

    response = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "My answer"})
    assert response.status_code == 201
    assert response.json()["is_late"] is False


@pytest.mark.asyncio
async def test_submission_after_due_date_is_flagged_late_not_rejected(client, db_session):
    """STU-004-AC02: flagged, not silently accepted as on-time -- and specifically NOT
    blocked either, since no global late-submission policy is confirmed anywhere."""
    student = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, student, due_offset=datetime.timedelta(days=-2))
    await _login(client, student.email)

    response = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "Late answer"})
    assert response.status_code == 201
    assert response.json()["is_late"] is True

    submission = await db_session.scalar(select(Submission).where(Submission.assignment_id == assignment.id, Submission.student_id == student.id))
    assert submission.is_late is True


@pytest.mark.asyncio
async def test_resubmission_re_evaluates_lateness(client, db_session):
    student = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, student, due_offset=datetime.timedelta(days=-1))
    await _login(client, student.email)

    first = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "v1"})
    assert first.json()["is_late"] is True

    second = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "v2"})
    assert second.status_code == 201
    assert second.json()["is_late"] is True  # still after the (unchanged) due date


@pytest.mark.asyncio
async def test_submission_requires_an_answer_or_file(client, db_session):
    student = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, student, due_offset=datetime.timedelta(days=5))
    await _login(client, student.email)

    response = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_student_cannot_submit_to_an_assignment_outside_their_enrollment(client, db_session):
    outsider = await _create_student(db_session)
    _enrolled_owner = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, _enrolled_owner, due_offset=datetime.timedelta(days=5))
    await _login(client, outsider.email)

    response = await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "Not my batch"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assignments_section_shows_the_late_flag(client, db_session):
    student = await _create_student(db_session)
    assignment = await _create_enrolled_assignment(db_session, student, due_offset=datetime.timedelta(days=-1))
    await _login(client, student.email)
    await client.post(f"/api/v1/workflows/it/assignments/{assignment.id}/submissions", json={"answer": "late"})

    response = await client.get("/api/v1/portal/it/student/assignments")
    assert response.status_code == 200
    row = next(r for r in response.json()["rows"] if r["id"] == str(assignment.id))
    assert "late" in row["submission"].lower()


@pytest.mark.asyncio
async def test_submission_endpoint_requires_authentication(client):
    response = await client.post(f"/api/v1/workflows/it/assignments/{uuid.uuid4()}/submissions", json={"answer": "x"})
    assert response.status_code == 401
