"""TRN-007 -- Submission review and grading.

`PATCH /workflows/it/trainer/submissions/{id}` already existed, already correctly scoped
grading to the trainer's own batch, and already wrote an AuditLog entry on every call --
untested until now. Covers: a trainer can grade a submission and the student sees the
result (STU-004's own portal payload already surfaces score/feedback), re-grading
overwrites the same row and adds a new audit entry rather than a duplicate record
(TRN-007-AC02), a score above the assignment's max is rejected, and RBAC.
"""

import datetime
import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import AuditLog, Batch, Enrollment, Program, Submission, User
from app.models import Assignment as AssignmentModel


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Grading Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch_assignment_submission(db_session, trainer: User) -> tuple[Batch, AssignmentModel, Submission, User]:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"TRN-007 Test Program {uuid.uuid4().hex[:6]}",
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
    await db_session.flush()
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Graded Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    assignment = AssignmentModel(
        batch_id=batch.id,
        title=f"Gradeable Assignment {uuid.uuid4().hex[:6]}",
        description="Do the thing.",
        due_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=5),
        max_score=100,
        assignment_type="assignment",
        submission_type="text_or_file",
        published=True,
    )
    db_session.add(assignment)
    await db_session.flush()
    submission = Submission(assignment_id=assignment.id, student_id=student.id, answer="My answer", status="submitted", is_late=False)
    db_session.add(submission)
    await db_session.commit()
    return batch, assignment, submission, student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_trainer_grades_a_submission_and_student_sees_the_result(client, db_session):
    trainer = await _create_trainer(db_session)
    _batch, assignment, submission, student = await _create_batch_assignment_submission(db_session, trainer)
    await _login(client, trainer.email)

    grade = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 85, "feedback": "Good work.", "status": "graded"})
    assert grade.status_code == 200
    assert grade.json() == {"id": str(submission.id), "status": "graded", "score": 85}

    await _login(client, student.email)
    portal = await client.get("/api/v1/portal/it/student/assignments")
    assert portal.status_code == 200
    row = next(r for r in portal.json()["rows"] if r["id"] == str(assignment.id))
    assert row["score"] == "85/100"
    assert row["feedback"] == "Good work."


@pytest.mark.asyncio
async def test_regrading_overwrites_the_same_submission_and_adds_a_new_audit_entry(client, db_session):
    """TRN-007-AC02: overwrites the prior grade with an audit trail, not a duplicate record."""
    trainer = await _create_trainer(db_session)
    _batch, _assignment, submission, _student = await _create_batch_assignment_submission(db_session, trainer)
    await _login(client, trainer.email)

    first = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 60, "feedback": "Needs work.", "status": "revision_required"})
    assert first.status_code == 200
    second = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 90, "feedback": "Much better.", "status": "graded"})
    assert second.status_code == 200

    total_submissions = await db_session.scalar(select(func.count()).select_from(Submission).where(Submission.id == submission.id))
    assert total_submissions == 1  # same row, not a duplicate

    await db_session.refresh(submission)  # this session's identity map still holds the pre-grade object
    assert submission.score == 90
    assert submission.feedback == "Much better."
    assert submission.status == "graded"

    audit_entries = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(submission.id), AuditLog.action == "assignment.grade"))
    assert audit_entries == 2  # one per grading call -- the trail, not the working record


@pytest.mark.asyncio
async def test_score_above_the_assignment_maximum_is_rejected(client, db_session):
    trainer = await _create_trainer(db_session)
    _batch, _assignment, submission, _student = await _create_batch_assignment_submission(db_session, trainer)
    await _login(client, trainer.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 150, "status": "graded"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trainer_cannot_grade_a_submission_outside_their_batch(client, db_session):
    owner = await _create_trainer(db_session)
    outsider = await _create_trainer(db_session)
    _batch, _assignment, submission, _student = await _create_batch_assignment_submission(db_session, owner)
    await _login(client, outsider.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 50, "status": "graded"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_grading_a_nonexistent_submission_404s(client, db_session):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{uuid.uuid4()}", json={"score": 50, "status": "graded"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_grading_requires_authentication(client):
    response = await client.patch(f"/api/v1/workflows/it/trainer/submissions/{uuid.uuid4()}", json={"score": 50, "status": "graded"})
    assert response.status_code == 401
