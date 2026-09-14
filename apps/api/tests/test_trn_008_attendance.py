"""TRN-008 -- Attendance marking.

`POST /workflows/it/trainer/attendance` already existed and already had solid behavior:
own-batch RBAC, upsert-by-(student, batch, session_date) semantics (so re-marking the same
session updates rather than duplicates), rejection of duplicate student ids within one
submission, and rejection of a student outside the batch's active roster -- untested until
now. Covers all of that plus the student-facing visibility half (STU-006's own
`GET /student/attendance`) and RBAC.
"""

import datetime
import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import Attendance, Batch, Enrollment, Program, User


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Attendance Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch_with_students(db_session, trainer: User, *, student_count: int = 2) -> tuple[Batch, list[User]]:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"TRN-008 Test Program {uuid.uuid4().hex[:6]}",
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
    students = []
    for i in range(student_count):
        student = User(
            email=f"student-{uuid.uuid4().hex[:8]}@example.local",
            password_hash=hash_password("Sup3r-Secret-Pass!"),
            full_name=f"Attendance Student {i}",
            role="it_student",
            division="it",
            active=True,
        )
        db_session.add(student)
        await db_session.flush()
        db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
        students.append(student)
    await db_session.commit()
    return batch, students


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_trainer_marks_attendance_and_student_sees_it(client, db_session):
    trainer = await _create_trainer(db_session)
    batch, students = await _create_batch_with_students(db_session, trainer, student_count=2)
    await _login(client, trainer.email)

    session_date = datetime.date.today().isoformat()
    response = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={
            "batch_id": str(batch.id),
            "session_date": session_date,
            "records": [
                {"student_id": str(students[0].id), "status": "present"},
                {"student_id": str(students[1].id), "status": "absent", "notes": "Informed sick leave."},
            ],
        },
    )
    assert response.status_code == 201
    assert response.json() == {"ok": True, "records": 2}

    await _login(client, students[1].email)
    seen = await client.get("/api/v1/workflows/it/student/attendance")
    assert seen.status_code == 200
    row = next(r for r in seen.json() if r["batch"] == batch.name)
    assert row["status"] == "absent"
    assert row["notes"] == "Informed sick leave."


@pytest.mark.asyncio
async def test_remarking_the_same_session_updates_in_place_not_a_duplicate(client, db_session):
    trainer = await _create_trainer(db_session)
    batch, students = await _create_batch_with_students(db_session, trainer, student_count=1)
    await _login(client, trainer.email)
    session_date = datetime.date.today().isoformat()

    first = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(batch.id), "session_date": session_date, "records": [{"student_id": str(students[0].id), "status": "absent"}]},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(batch.id), "session_date": session_date, "records": [{"student_id": str(students[0].id), "status": "present", "notes": "Corrected."}]},
    )
    assert second.status_code == 201

    count = await db_session.scalar(select(func.count()).select_from(Attendance).where(Attendance.student_id == students[0].id, Attendance.batch_id == batch.id, Attendance.session_date == datetime.date.today()))
    assert count == 1
    record = await db_session.scalar(select(Attendance).where(Attendance.student_id == students[0].id, Attendance.batch_id == batch.id, Attendance.session_date == datetime.date.today()))
    assert record.status == "present"
    assert record.notes == "Corrected."


@pytest.mark.asyncio
async def test_marking_attendance_for_a_non_enrolled_student_is_rejected(client, db_session):
    trainer = await _create_trainer(db_session)
    batch, _students = await _create_batch_with_students(db_session, trainer, student_count=1)
    outsider = User(
        email=f"outsider-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Not Enrolled",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(outsider)
    await db_session.commit()
    await _login(client, trainer.email)

    response = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(batch.id), "session_date": datetime.date.today().isoformat(), "records": [{"student_id": str(outsider.id), "status": "present"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_student_in_the_same_submission_is_rejected(client, db_session):
    trainer = await _create_trainer(db_session)
    batch, students = await _create_batch_with_students(db_session, trainer, student_count=1)
    await _login(client, trainer.email)

    response = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={
            "batch_id": str(batch.id),
            "session_date": datetime.date.today().isoformat(),
            "records": [
                {"student_id": str(students[0].id), "status": "present"},
                {"student_id": str(students[0].id), "status": "absent"},
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trainer_cannot_mark_attendance_outside_their_batch(client, db_session):
    owner = await _create_trainer(db_session)
    outsider = await _create_trainer(db_session)
    batch, students = await _create_batch_with_students(db_session, owner, student_count=1)
    await _login(client, outsider.email)

    response = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(batch.id), "session_date": datetime.date.today().isoformat(), "records": [{"student_id": str(students[0].id), "status": "present"}]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_attendance_marking_requires_authentication(client):
    response = await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(uuid.uuid4()), "session_date": datetime.date.today().isoformat(), "records": [{"student_id": str(uuid.uuid4()), "status": "present"}]},
    )
    assert response.status_code == 401
