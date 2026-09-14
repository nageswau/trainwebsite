"""TRN-005 -- Assignment create and edit.

Create (`POST /workflows/it/trainer/assignments`) already existed. This covers the
previously-entirely-missing edit half: `PATCH /workflows/it/trainer/assignments/{id}`
(partial update, own-batch RBAC), `GET /workflows/it/trainer/assignments` (own assignments,
used to populate the edit picker), and TRN-005-AC02 -- editing a due date after a
submission already exists must never retroactively change that submission's stored
`is_late` flag (STU-004's own value is computed once, at submission time, never
recomputed from the assignment's current due_date).
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Assignment, Batch, Enrollment, Program, Submission, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Assignment Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch(db_session, trainer: User) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"TRN-005 Test Program {uuid.uuid4().hex[:6]}",
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


async def _create_assignment(db_session, batch: Batch, *, due_offset: datetime.timedelta) -> Assignment:
    assignment = Assignment(
        batch_id=batch.id,
        title=f"Original Title {uuid.uuid4().hex[:6]}",
        description="Original description.",
        due_date=datetime.datetime.now(datetime.UTC) + due_offset,
        max_score=100,
        assignment_type="assignment",
        submission_type="text_or_file",
        published=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    return assignment


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_trainer_can_edit_their_own_assignment(client, db_session):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)
    assignment = await _create_assignment(db_session, batch, due_offset=datetime.timedelta(days=5))
    await _login(client, trainer.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/assignments/{assignment.id}", json={"title": "Updated Title", "max_score": 150})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"

    await db_session.refresh(assignment)
    assert assignment.title == "Updated Title"
    assert assignment.max_score == 150
    assert assignment.description == "Original description."  # untouched by the partial update


@pytest.mark.asyncio
async def test_editing_due_date_does_not_retroactively_change_an_existing_submissions_late_flag(client, db_session):
    """TRN-005-AC02: editing after submissions exist does not invalidate work already submitted."""
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)
    assignment = await _create_assignment(db_session, batch, due_offset=datetime.timedelta(days=-1))
    student = User(
        email=f"student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Submitting Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    submission = Submission(assignment_id=assignment.id, student_id=student.id, answer="Late work", status="submitted", is_late=True)
    db_session.add(submission)
    await db_session.commit()

    await _login(client, trainer.email)
    response = await client.patch(f"/api/v1/workflows/it/trainer/assignments/{assignment.id}", json={"due_date": (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=10)).isoformat()})
    assert response.status_code == 200

    refreshed = await db_session.scalar(select(Submission).where(Submission.id == submission.id))
    assert refreshed.is_late is True  # unchanged, even though the new due_date is now in the future


@pytest.mark.asyncio
async def test_trainer_cannot_edit_another_trainers_assignment(client, db_session):
    owner = await _create_trainer(db_session)
    outsider = await _create_trainer(db_session)
    batch = await _create_batch(db_session, owner)
    assignment = await _create_assignment(db_session, batch, due_offset=datetime.timedelta(days=5))
    await _login(client, outsider.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/assignments/{assignment.id}", json={"title": "Hijacked"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_editing_a_nonexistent_assignment_404s(client, db_session):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)

    response = await client.patch(f"/api/v1/workflows/it/trainer/assignments/{uuid.uuid4()}", json={"title": "Ghost"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trainer_assignments_list_is_scoped_to_their_own_batches(client, db_session):
    owner = await _create_trainer(db_session)
    other = await _create_trainer(db_session)
    own_batch = await _create_batch(db_session, owner)
    other_batch = await _create_batch(db_session, other)
    own_assignment = await _create_assignment(db_session, own_batch, due_offset=datetime.timedelta(days=5))
    other_assignment = await _create_assignment(db_session, other_batch, due_offset=datetime.timedelta(days=5))
    await _login(client, owner.email)

    response = await client.get("/api/v1/workflows/it/trainer/assignments")
    assert response.status_code == 200
    ids = {a["id"] for a in response.json()}
    assert str(own_assignment.id) in ids
    assert str(other_assignment.id) not in ids


@pytest.mark.asyncio
async def test_assignment_edit_and_list_require_authentication(client):
    assert (await client.get("/api/v1/workflows/it/trainer/assignments")).status_code == 401
    assert (await client.patch(f"/api/v1/workflows/it/trainer/assignments/{uuid.uuid4()}", json={"title": "x"})).status_code == 401
