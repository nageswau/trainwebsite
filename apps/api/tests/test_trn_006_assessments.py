"""TRN-006 -- Assessment create and edit.

Create already existed (`POST /workflows/it/trainer/assessments`); the entire edit half
was missing -- same gap shape as `TRN-005` before its own fix -- no `PATCH` endpoint, no
edit UI. Added `PATCH /workflows/it/trainer/assessments/{id}` (own-batch RBAC), which also
carries the "Draft -> Scheduled" publish transition (no separate publish endpoint, same
precedent as `TRN-005`'s plain `published` boolean). Also found and fixed a real,
confirmed `TRN-006-AC02` violation: the student-facing "examinations" portal section had
no status filter at all -- a Draft assessment (not yet meant to exist for students) was
fully visible in the list, title/schedule and all, even though `POST
/it/assessments/{id}/attempts` already correctly blocked starting an attempt on one.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Assessment, Batch, Enrollment, Program, User


async def _create_trainer(db_session, *, email_prefix: str = "trn006-trainer") -> User:
    trainer = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Assessment Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session) -> User:
    student = User(
        email=f"trn006-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Assessment Student",
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
        title=f"TRN-006 Test Program {uuid.uuid4().hex[:6]}",
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
async def test_trainer_creates_and_edits_an_assessment(db_session, client):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)
    await _login(client, trainer.email)

    create = await client.post(
        "/api/v1/workflows/it/trainer/assessments",
        json={"batch_id": str(batch.id), "title": "Module 1 Quiz", "scheduled_at": "2027-01-10T10:00:00Z", "status": "draft"},
    )
    assert create.status_code == 201
    assert create.json()["status"] == "draft"
    assessment_id = create.json()["id"]

    edit = await client.patch(f"/api/v1/workflows/it/trainer/assessments/{assessment_id}", json={"title": "Module 1 Quiz (Revised)", "status": "scheduled"})
    assert edit.status_code == 200
    assert edit.json()["title"] == "Module 1 Quiz (Revised)"
    assert edit.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_trainer_cannot_edit_an_assessment_outside_their_own_batch(db_session, client):
    owner = await _create_trainer(db_session, email_prefix="trn006-owner")
    outsider = await _create_trainer(db_session, email_prefix="trn006-outsider")
    batch = await _create_batch(db_session, owner)
    assessment = Assessment(batch_id=batch.id, title=f"Owner's Assessment {uuid.uuid4().hex[:6]}", scheduled_at=datetime.datetime.now(datetime.UTC), status="draft")
    db_session.add(assessment)
    await db_session.commit()
    await db_session.refresh(assessment)

    await _login(client, outsider.email)
    response = await client.patch(f"/api/v1/workflows/it/trainer/assessments/{assessment.id}", json={"title": "Hijacked"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_editing_an_unknown_assessment_is_404(db_session, client):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)
    response = await client.patch(f"/api/v1/workflows/it/trainer/assessments/{uuid.uuid4()}", json={"title": "Nope"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_draft_assessment_is_never_visible_to_students(db_session, client):
    """TRN-006-AC02: a Draft assessment must not appear in the student's own list at
    all, even though they're enrolled in its batch."""
    trainer = await _create_trainer(db_session)
    student = await _create_student(db_session)
    batch = await _create_batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    draft_title = f"Secret Draft Assessment {uuid.uuid4().hex[:6]}"
    scheduled_title = f"Visible Scheduled Assessment {uuid.uuid4().hex[:6]}"
    draft = Assessment(batch_id=batch.id, title=draft_title, scheduled_at=datetime.datetime.now(datetime.UTC), status="draft")
    scheduled = Assessment(batch_id=batch.id, title=scheduled_title, scheduled_at=datetime.datetime.now(datetime.UTC), status="scheduled")
    db_session.add_all([draft, scheduled])
    await db_session.commit()

    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/student/examinations")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()["rows"]}
    assert draft_title not in titles
    assert scheduled_title in titles


@pytest.mark.asyncio
async def test_assessment_edit_requires_authentication(client):
    response = await client.patch(f"/api/v1/workflows/it/trainer/assessments/{uuid.uuid4()}", json={"title": "Nope"})
    assert response.status_code == 401
