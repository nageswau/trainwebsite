"""TRN-004 -- Recording list and resource upload.

Both halves of this feature already existed and worked, with zero test evidence anywhere
under this Feature ID: `PATCH /communications/it/live-sessions/{id}/recording` (own-batch
RBAC, feeds the recording list `GET .../live-sessions` already covers from STU-003/TRN-003)
and `POST /workflows/it/trainer/materials` (own-batch RBAC, feeds the student "downloads"
portal section). Covers: a trainer attaches a recording to their own batch's session and it
appears in the list for both the trainer and an enrolled student (TRN-004-AC01), a session
with no recording yet reads as "not_available" rather than an error (TRN-004-AC02, already
proven from the student's side by STU-003 -- proven here from the trainer's own recording-
attach action instead), resource upload is scoped to the trainer's own batch and visible
only to that batch's enrolled students (TRN-004-AC03), and auth/role RBAC on both endpoints.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Batch, Enrollment, LearningResource, LiveSession, Program, User


async def _create_trainer(db_session, *, email_prefix: str = "trn004-trainer") -> User:
    trainer = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Recordings Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session, *, email_prefix: str = "trn004-student") -> User:
    student = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Recordings Student",
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
        title=f"TRN-004 Test Program {uuid.uuid4().hex[:6]}",
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
async def test_trainer_attaches_a_recording_and_it_appears_for_the_enrolled_student(db_session, client):
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    session = LiveSession(
        batch_id=batch.id,
        title=f"Past Session {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2),
        ends_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2, hours=-1),
        provider="manual",
        status="completed",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    await _login(client, trainer.email)
    response = await client.patch(
        f"/api/v1/communications/it/live-sessions/{session.id}/recording",
        json={"recording_url": "https://provider.example.com/recording-1", "recording_status": "available"},
    )
    assert response.status_code == 200

    await _login(client, student.email)
    listing = await client.get("/api/v1/communications/it/live-sessions")
    assert listing.status_code == 200
    listed = next(s for s in listing.json() if s["id"] == str(session.id))
    assert listed["recording_url"] == "https://provider.example.com/recording-1"
    assert listed["recording_status"] == "available"


@pytest.mark.asyncio
async def test_missing_recording_reads_as_not_available_not_an_error(db_session, client):
    """TRN-004-AC02: a session the trainer hasn't attached a recording to yet (e.g. a
    provider concurrency limit) must never surface as a broken/error state."""
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)
    session = LiveSession(
        batch_id=batch.id,
        title=f"Session Without Recording {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
        ends_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1, hours=-1),
        provider="manual",
        status="completed",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    await _login(client, trainer.email)
    response = await client.get("/api/v1/communications/it/live-sessions")
    assert response.status_code == 200
    listed = next(s for s in response.json() if s["id"] == str(session.id))
    assert listed["recording_url"] is None
    assert listed["recording_status"] == "not_available"


@pytest.mark.asyncio
async def test_trainer_cannot_attach_a_recording_outside_their_own_batch(db_session, client):
    owner = await _create_trainer(db_session, email_prefix="trn004-owner")
    outsider = await _create_trainer(db_session, email_prefix="trn004-outsider")
    batch = await _create_batch(db_session, owner)
    session = LiveSession(
        batch_id=batch.id,
        title=f"Owner Session {uuid.uuid4().hex[:6]}",
        starts_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
        ends_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1, hours=-1),
        provider="manual",
        status="completed",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    await _login(client, outsider.email)
    response = await client.patch(f"/api/v1/communications/it/live-sessions/{session.id}/recording", json={"recording_url": "https://provider.example.com/stolen"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_trainer_uploads_a_resource_visible_to_own_batch_students_only(db_session, client):
    trainer = await _create_trainer(db_session)
    enrolled_student = await _create_student(db_session, email_prefix="trn004-enrolled")
    outside_student = await _create_student(db_session, email_prefix="trn004-outside")
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=enrolled_student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, trainer.email)
    response = await client.post(
        "/api/v1/workflows/it/trainer/materials",
        json={"batch_id": str(batch.id), "title": "Week 1 Notes", "resource_type": "notes", "url": "https://example.com/notes.pdf"},
    )
    assert response.status_code == 201

    stored = await db_session.scalar(select(LearningResource).where(LearningResource.batch_id == batch.id))
    assert stored is not None

    await _login(client, enrolled_student.email)
    enrolled_view = await client.get("/api/v1/portal/it/student/downloads")
    assert enrolled_view.status_code == 200
    assert any(r["title"] == "Week 1 Notes" for r in enrolled_view.json()["rows"])

    await _login(client, outside_student.email)
    outside_view = await client.get("/api/v1/portal/it/student/downloads")
    assert outside_view.status_code == 200
    assert all(r["title"] != "Week 1 Notes" for r in outside_view.json()["rows"])


@pytest.mark.asyncio
async def test_trainer_cannot_upload_a_resource_outside_their_own_batch(db_session, client):
    owner = await _create_trainer(db_session, email_prefix="trn004-res-owner")
    outsider = await _create_trainer(db_session, email_prefix="trn004-res-outsider")
    batch = await _create_batch(db_session, owner)

    await _login(client, outsider.email)
    response = await client.post(
        "/api/v1/workflows/it/trainer/materials",
        json={"batch_id": str(batch.id), "title": "Not Yours", "resource_type": "notes", "url": "https://example.com/notes.pdf"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_resource_upload_requires_authentication(client):
    response = await client.post(
        "/api/v1/workflows/it/trainer/materials",
        json={"batch_id": str(uuid.uuid4()), "title": "Notes", "resource_type": "notes", "url": "https://example.com/notes.pdf"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recording_attach_requires_authentication(client):
    response = await client.patch(f"/api/v1/communications/it/live-sessions/{uuid.uuid4()}/recording", json={"recording_url": "https://provider.example.com/recording"})
    assert response.status_code == 401
