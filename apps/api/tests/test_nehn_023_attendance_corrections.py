"""nehn-023 -- attendance correction usability and notifications.

AC1 the student never needs a UUID (row flag + portal columns), AC2 the trainer is told about a new request (in-app +
queued email; no active trainer -> the IT admins), AC3 a decision updates the attendance and tells the student, AC4 a
malformed review body is a 422. Plus: a decided request cannot be reviewed again (409), another batch's trainer is
refused (403).
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Attendance, AttendanceCorrection, Batch, Enrollment, Notification, NotificationDelivery, Program, User

PASSWORD = "Sup3r-Secret-Pass!"


async def _user(db_session, role: str, name: str, active: bool = True) -> User:
    user = User(email=f"n023-{uuid.uuid4().hex[:10]}@example.local", password_hash=hash_password(PASSWORD), full_name=name, role=role, division="it", active=active)
    db_session.add(user)
    await db_session.commit()
    return user


async def _world(db_session, *, trainer: User | None):
    student = await _user(db_session, "it_student", "Correction Student")
    program = Program(
        slug=f"n023-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"nehn-023 Program {uuid.uuid4().hex[:6]}",
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
        trainer_id=trainer.id if trainer else None,
        name=f"N023-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N023-{uuid.uuid4().hex[:10]}", status="active", progress_percent=0))
    attendance = Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2026, 10, 20), status="absent")
    db_session.add(attendance)
    await db_session.commit()
    return student, batch, attendance


async def _login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": "it"})
    assert response.status_code == 200


async def _request(client, student: User, attendance: Attendance):
    await _login(client, student)
    return await client.post(
        "/api/v1/workflows/it/student/attendance-corrections",
        json={"attendance_id": str(attendance.id), "requested_status": "present", "reason": "I was in class, marked absent by mistake."},
    )


async def _notes(db_session, user: User) -> list[Notification]:
    user_id = user.id
    db_session.expunge_all()
    return list((await db_session.scalars(select(Notification).where(Notification.user_id == user_id))).all())


async def _emails(db_session, note: Notification) -> list[NotificationDelivery]:
    return list((await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id, NotificationDelivery.channel == "email"))).all())


@pytest.mark.asyncio
async def test_new_request_notifies_the_batch_trainer_in_app_and_by_email(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Queue Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)

    response = await _request(client, student, attendance)

    assert response.status_code == 201
    notes = await _notes(db_session, trainer)
    assert len(notes) == 1
    assert notes[0].title == "Attendance correction requested"
    assert "Correction Student" in notes[0].body and batch.name in notes[0].body and "20 Oct 2026" in notes[0].body
    assert notes[0].action_url == "/it/trainer/attendance"
    emails = await _emails(db_session, notes[0])
    assert len(emails) == 1
    assert str(emails[0].id) in {delivery_id for delivery_id, _ in enqueued}
    assert await _notes(db_session, student) == []


@pytest.mark.asyncio
async def test_batch_without_an_active_trainer_routes_to_the_it_admins(db_session, client, enqueued):
    admin = await _user(db_session, "it_admin", "Routing Admin")
    inactive_admin = await _user(db_session, "it_admin", "Gone Admin", active=False)
    student, batch, attendance = await _world(db_session, trainer=None)

    assert (await _request(client, student, attendance)).status_code == 201

    notes = await _notes(db_session, admin)
    assert len(notes) == 1
    assert notes[0].action_url == "/it/admin/batches"
    assert "no trainer" in notes[0].body.lower()
    assert await _notes(db_session, inactive_admin) == []


@pytest.mark.asyncio
async def test_inactive_trainer_also_routes_to_the_it_admins(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Left Trainer", active=False)
    admin = await _user(db_session, "it_admin", "Fallback Admin")
    student, _, attendance = await _world(db_session, trainer=trainer)

    assert (await _request(client, student, attendance)).status_code == 201

    assert await _notes(db_session, trainer) == []
    assert len(await _notes(db_session, admin)) == 1


@pytest.mark.asyncio
async def test_second_pending_request_is_refused_and_notifies_nobody_again(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Dup Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    assert (await _request(client, student, attendance)).status_code == 201

    assert (await _request(client, student, attendance)).status_code == 409
    assert len(await _notes(db_session, trainer)) == 1


@pytest.mark.asyncio
async def test_student_attendance_rows_flag_a_pending_correction(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Flag Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    await _login(client, student)

    before = (await client.get("/api/v1/workflows/it/student/attendance")).json()
    assert [row["correction_pending"] for row in before] == [False]

    assert (await _request(client, student, attendance)).status_code == 201
    after = (await client.get("/api/v1/workflows/it/student/attendance")).json()
    assert after[0]["id"] == str(attendance.id)
    assert after[0]["correction_pending"] is True


@pytest.mark.asyncio
async def test_portal_attendance_shows_no_record_reference(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Portal Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    assert (await _request(client, student, attendance)).status_code == 201

    body = (await client.get("/api/v1/portal/it/student/attendance")).json()

    assert "id" not in [column["key"] for column in body["columns"]]
    items = next(panel["items"] for panel in body["panels"] if panel["title"] == "Correction requests")
    assert items == [f"20 Oct 2026 · {batch.name}: present — pending"]
    pending = await db_session.scalar(select(AttendanceCorrection).where(AttendanceCorrection.attendance_id == attendance.id))
    assert str(pending.id) not in items[0]


@pytest.mark.asyncio
async def test_approve_updates_attendance_and_notifies_the_student(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Approving Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, trainer)

    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction_id}", json={"status": "approved", "review_notes": "  Checked the register.  "})

    assert response.status_code == 200
    assert response.json() == {"id": correction_id, "status": "approved"}
    db_session.expunge_all()
    assert (await db_session.get(Attendance, attendance.id)).status == "present"
    correction = await db_session.get(AttendanceCorrection, uuid.UUID(correction_id))
    assert correction.review_notes == "Checked the register."
    assert correction.reviewed_by_id == trainer.id
    notes = await _notes(db_session, student)
    assert len(notes) == 1
    assert notes[0].title == "Attendance correction approved"
    assert batch.name in notes[0].body and "20 Oct 2026" in notes[0].body and "Checked the register." in notes[0].body
    assert notes[0].action_url == "/it/student/attendance"
    assert len(await _emails(db_session, notes[0])) == 1


@pytest.mark.asyncio
async def test_reject_keeps_attendance_and_notifies_the_student(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Rejecting Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, trainer)

    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction_id}", json={"status": "rejected", "review_notes": "   "})

    assert response.status_code == 200
    db_session.expunge_all()
    assert (await db_session.get(Attendance, attendance.id)).status == "absent"
    assert (await db_session.get(AttendanceCorrection, uuid.UUID(correction_id))).review_notes is None
    notes = await _notes(db_session, student)
    assert [n.title for n in notes] == ["Attendance correction rejected"]
    assert "Comment" not in notes[0].body


@pytest.mark.asyncio
async def test_a_decided_request_cannot_be_reviewed_again(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Twice Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, trainer)
    url = f"/api/v1/workflows/it/attendance-corrections/{correction_id}"
    assert (await client.patch(url, json={"status": "rejected"})).status_code == 200

    response = await client.patch(url, json={"status": "approved"})

    assert response.status_code == 409
    db_session.expunge_all()
    assert (await db_session.get(Attendance, attendance.id)).status == "absent"
    assert len(await _notes(db_session, student)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"status": "maybe"},
        {"status": None},
        {"status": "approved", "review_notes": "x" * 2001},
        {"status": "approved", "review_notes": 5},
    ],
)
async def test_malformed_review_body_is_422(db_session, client, enqueued, body):
    trainer = await _user(db_session, "trainer", "Strict Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, trainer)

    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction_id}", json=body)

    assert response.status_code == 422
    db_session.expunge_all()
    assert (await db_session.get(AttendanceCorrection, uuid.UUID(correction_id))).status == "pending"


@pytest.mark.asyncio
async def test_another_batch_trainer_cannot_review(db_session, client, enqueued):
    trainer = await _user(db_session, "trainer", "Owner Trainer")
    outsider = await _user(db_session, "trainer", "Outsider Trainer")
    student, _, attendance = await _world(db_session, trainer=trainer)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, outsider)

    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction_id}", json={"status": "approved"})

    assert response.status_code == 403
    assert await _notes(db_session, student) == []


@pytest.mark.asyncio
async def test_it_admin_reviews_a_trainerless_batch_request(db_session, client, enqueued):
    admin = await _user(db_session, "it_admin", "Reviewing Admin")
    student, _, attendance = await _world(db_session, trainer=None)
    correction_id = (await _request(client, student, attendance)).json()["id"]
    await _login(client, admin)

    response = await client.patch(f"/api/v1/workflows/it/attendance-corrections/{correction_id}", json={"status": "approved"})

    assert response.status_code == 200
    assert [n.title for n in await _notes(db_session, student)] == ["Attendance correction approved"]
