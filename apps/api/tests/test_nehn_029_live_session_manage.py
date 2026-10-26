"""nehn-029 -- live class reschedule and cancel (spec docs/superpowers/specs/2026-10-26-nehn-029-live-class-reschedule-cancel-design.md,
DEC-SCOPE-283). `PATCH /communications/it/live-sessions/{id}` moves/edits a session that has not started, `POST …/cancel` cancels one
with a reason; students are notified in-app and by email (queue_deliveries), provider sessions carry a manual-update warning, and a
date whose only live sessions are cancelled refuses attendance."""

import datetime
import uuid
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Attendance, AuditLog, Batch, Enrollment, LiveSession, Notification, NotificationDelivery, Program, User

PASSWORD = "Sup3r-Secret-Pass!"
API = "/api/v1/communications/it/live-sessions"
UTC = datetime.UTC


async def _user(db, role: str) -> User:
    user = User(email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"N029 {role}", role=role, division="it", active=True)
    db.add(user)
    await db.commit()
    return user


async def _world(db, *, provider: str = "manual", starts_in: datetime.timedelta = datetime.timedelta(days=2)):
    trainer = await _user(db, "trainer")
    student = await _user(db, "it_student")
    dropped = await _user(db, "it_student")
    program = Program(
        slug=f"n029-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title="N029 Program",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test",
        curriculum=["M1"],
        placement_assistance="Yes",
        trainer_name="T",
        active=True,
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"N029-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon 7pm",
        capacity=20,
        status="active",
    )
    db.add(batch)
    await db.flush()
    db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N029-{uuid.uuid4().hex[:10]}", status="active"))
    db.add(Enrollment(student_id=dropped.id, batch_id=batch.id, enrollment_code=f"N029-{uuid.uuid4().hex[:10]}", status="dropped"))
    starts = datetime.datetime.now(UTC) + starts_in
    session = LiveSession(
        batch_id=batch.id,
        trainer_id=trainer.id,
        title="Original title",
        starts_at=starts,
        ends_at=starts + datetime.timedelta(hours=1),
        provider=provider,
        meeting_url="https://meet.example.com/a",
        sync_status="manual" if provider == "manual" else "created",
        status="scheduled",
    )
    db.add(session)
    await db.commit()
    return {"trainer": trainer, "student": student, "dropped": dropped, "batch": batch, "session": session}


async def _login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": "it"})
    assert response.status_code == 200


async def _notes(db, user: User) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at))).all())


async def _fresh(db, session: LiveSession) -> LiveSession:
    await db.refresh(session)
    return session


def _iso(value: datetime.datetime) -> str:
    return value.isoformat()


# --- reschedule ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trainer_moves_a_class_by_one_hour_and_enrolled_students_are_notified(client, db_session, enqueued):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    new_start = w["session"].starts_at + datetime.timedelta(hours=1)
    response = await client.patch(f"{API}/{w['session'].id}", json={"starts_at": _iso(new_start), "ends_at": _iso(new_start + datetime.timedelta(hours=1))})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "scheduled" and body["warning"] is None
    assert datetime.datetime.fromisoformat(body["starts_at"]) == new_start

    stored = await _fresh(db_session, w["session"])
    assert stored.starts_at == new_start
    notes = await _notes(db_session, w["student"])
    assert [n.title for n in notes] == ["Live class rescheduled"]
    assert "Original title" in notes[0].body
    assert await _notes(db_session, w["dropped"]) == []
    channels = (await db_session.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id == notes[0].id))).all()
    assert "email" in channels and enqueued  # in-app row + email queued for the worker after commit
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(w["session"].id), AuditLog.action == "live_session.update"))
    assert audit and set(audit.metadata_json["changed"]) == {"starts_at", "ends_at"}

    # the student sees the new time
    await _login(client, w["student"])
    listed = next(s for s in (await client.get(API)).json() if s["id"] == str(w["session"].id))
    assert datetime.datetime.fromisoformat(listed["starts_at"]) == new_start


@pytest.mark.asyncio
async def test_a_naive_time_is_read_in_the_batch_timezone(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    local = (datetime.datetime.now(ZoneInfo("Asia/Kolkata")) + datetime.timedelta(days=3)).replace(hour=19, minute=0, second=0, microsecond=0, tzinfo=None)
    response = await client.patch(f"{API}/{w['session'].id}", json={"starts_at": local.isoformat(), "ends_at": (local + datetime.timedelta(hours=1)).isoformat()})
    assert response.status_code == 200, response.text
    stored = await _fresh(db_session, w["session"])
    assert stored.starts_at == local.replace(tzinfo=ZoneInfo("Asia/Kolkata"))


@pytest.mark.asyncio
async def test_title_and_link_change_notifies_as_an_update(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    response = await client.patch(f"{API}/{w['session'].id}", json={"title": "New title", "meeting_url": "https://meet.example.com/b"})
    assert response.status_code == 200, response.text
    stored = await _fresh(db_session, w["session"])
    assert (stored.title, stored.meeting_url) == ("New title", "https://meet.example.com/b")
    assert [n.title for n in await _notes(db_session, w["student"])] == ["Live class updated"]


@pytest.mark.asyncio
async def test_an_unchanged_payload_notifies_nobody(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    response = await client.patch(f"{API}/{w['session'].id}", json={"title": "Original title"})
    assert response.status_code == 200
    assert await _notes(db_session, w["student"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,label", [("google_meet", "Google Meet"), ("zoho_meeting", "Zoho Meeting")])
async def test_a_provider_session_changes_locally_and_warns_the_trainer(client, db_session, provider, label):
    w = await _world(db_session, provider=provider)
    await _login(client, w["trainer"])
    new_start = w["session"].starts_at + datetime.timedelta(hours=1)
    response = await client.patch(f"{API}/{w['session'].id}", json={"starts_at": _iso(new_start), "ends_at": _iso(new_start + datetime.timedelta(hours=1))})
    assert response.status_code == 200
    assert label in response.json()["warning"]
    stored = await _fresh(db_session, w["session"])
    assert stored.starts_at == new_start and stored.sync_status == "manual_update_required"


@pytest.mark.asyncio
async def test_a_started_session_cannot_be_rescheduled(client, db_session):
    w = await _world(db_session, starts_in=datetime.timedelta(minutes=-5))
    await _login(client, w["trainer"])
    response = await client.patch(f"{API}/{w['session'].id}", json={"title": "Too late"})
    assert response.status_code == 409
    assert "Past sessions cannot be rescheduled" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"starts_at": "2020-01-01T10:00:00+00:00", "ends_at": "2020-01-01T11:00:00+00:00"},
        {"meeting_url": "javascript:alert(1)"},
        {"title": "x"},
    ],
)
async def test_invalid_reschedules_are_422(client, db_session, payload):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    response = await client.patch(f"{API}/{w['session'].id}", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_an_end_before_the_start_is_422_even_when_only_one_side_moves(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    response = await client.patch(f"{API}/{w['session'].id}", json={"starts_at": _iso(w["session"].ends_at + datetime.timedelta(minutes=5))})
    assert response.status_code == 422
    assert "end time" in response.json()["detail"]


# --- cancel ---------------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_records_the_reason_and_students_see_cancelled(client, db_session, enqueued):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    response = await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "  Trainer unwell  "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["cancel_reason"], body["attendance_records"], body["warning"]) == ("cancelled", "Trainer unwell", 0, None)

    notes = await _notes(db_session, w["student"])
    assert [n.title for n in notes] == ["Live class cancelled"] and "Trainer unwell" in notes[0].body
    assert enqueued
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(w["session"].id), AuditLog.action == "live_session.cancel"))

    await _login(client, w["student"])
    listed = next(s for s in (await client.get(API)).json() if s["id"] == str(w["session"].id))
    assert (listed["status"], listed["cancel_reason"]) == ("cancelled", "Trainer unwell")
    course = (await client.get("/api/v1/workflows/it/student/learning")).json()
    assert next(s for s in course["live_sessions"] if s["id"] == str(w["session"].id))["cancel_reason"] == "Trainer unwell"


@pytest.mark.asyncio
async def test_a_cancelled_session_cannot_be_cancelled_again_or_rescheduled(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "First"})).status_code == 200
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Again"})).status_code == 409
    assert (await client.patch(f"{API}/{w['session'].id}", json={"title": "Back on"})).status_code == 409
    assert len(await _notes(db_session, w["student"])) == 1


@pytest.mark.asyncio
async def test_a_started_session_cannot_be_cancelled(client, db_session):
    w = await _world(db_session, starts_in=datetime.timedelta(minutes=-5))
    await _login(client, w["trainer"])
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Too late"})).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
async def test_cancel_needs_a_real_reason(client, db_session, reason):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": reason})).status_code == 422


@pytest.mark.asyncio
async def test_cancel_of_a_provider_session_warns_and_reports_marked_attendance(client, db_session):
    w = await _world(db_session, provider="zoho_meeting", starts_in=datetime.timedelta(hours=1))
    session_date = w["session"].starts_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    db_session.add(Attendance(student_id=w["student"].id, batch_id=w["batch"].id, session_date=session_date, status="present"))
    await db_session.commit()
    await _login(client, w["trainer"])
    body = (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Holiday"})).json()
    assert "Zoho Meeting" in body["warning"] and body["attendance_records"] == 1
    assert await db_session.scalar(select(Attendance).where(Attendance.batch_id == w["batch"].id))  # kept, never deleted


@pytest.mark.asyncio
async def test_the_trainer_portal_table_shows_cancelled_with_the_reason_and_no_join_link(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    row = (await client.get("/api/v1/portal/it/trainer/live-sessions")).json()["rows"][0]
    assert (row["status"], row["meeting"]) == ("Scheduled", "https://meet.example.com/a")
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Holiday"})).status_code == 200
    row = (await client.get("/api/v1/portal/it/trainer/live-sessions")).json()["rows"][0]
    assert (row["status"], row["meeting"]) == ("Cancelled — Holiday", None)


# --- authorization --------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_trainer_gets_403_on_both_routes(client, db_session):
    w = await _world(db_session)
    other = await _user(db_session, "trainer")
    await _login(client, other)
    assert (await client.patch(f"{API}/{w['session'].id}", json={"title": "Hijack"})).status_code == 403
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Hijack"})).status_code == 403
    stored = await _fresh(db_session, w["session"])
    assert (stored.title, stored.status) == ("Original title", "scheduled")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "hr_team"])
async def test_non_trainer_roles_get_403(client, db_session, role):
    w = await _world(db_session)
    await _login(client, await _user(db_session, role))
    assert (await client.patch(f"{API}/{w['session'].id}", json={"title": "Nope"})).status_code == 403
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Nope"})).status_code == 403


@pytest.mark.asyncio
async def test_it_admin_can_manage_any_session(client, db_session):
    w = await _world(db_session)
    await _login(client, await _user(db_session, "it_admin"))
    assert (await client.patch(f"{API}/{w['session'].id}", json={"title": "Admin edit"})).status_code == 200
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Admin cancel"})).status_code == 200


@pytest.mark.asyncio
async def test_unknown_session_is_404_and_anonymous_is_401(client, db_session):
    w = await _world(db_session)
    assert (await client.patch(f"{API}/{w['session'].id}", json={"title": "Anon"})).status_code == 401
    await _login(client, w["trainer"])
    assert (await client.patch(f"{API}/{uuid.uuid4()}", json={"title": "Ghost"})).status_code == 404
    assert (await client.post(f"{API}/{uuid.uuid4()}/cancel", json={"reason": "Ghost"})).status_code == 404


# --- attendance -----------------------------------------------------------------------------------------------------------------------


async def _mark(client, w, session_date: datetime.date):
    return await client.post(
        "/api/v1/workflows/it/trainer/attendance",
        json={"batch_id": str(w["batch"].id), "session_date": session_date.isoformat(), "records": [{"student_id": str(w["student"].id), "status": "present"}]},
    )


@pytest.mark.asyncio
async def test_a_date_whose_only_session_is_cancelled_refuses_attendance(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    session_date = w["session"].starts_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Holiday"})).status_code == 200
    response = await _mark(client, w, session_date)
    assert response.status_code == 409 and "cancelled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_date_with_another_live_session_or_none_still_takes_attendance(client, db_session):
    w = await _world(db_session)
    await _login(client, w["trainer"])
    session_date = w["session"].starts_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
    later = w["session"].starts_at + datetime.timedelta(hours=3)
    db_session.add(LiveSession(batch_id=w["batch"].id, trainer_id=w["trainer"].id, title="Second", starts_at=later, ends_at=later + datetime.timedelta(hours=1), provider="manual", status="scheduled"))
    await db_session.commit()
    assert (await client.post(f"{API}/{w['session'].id}/cancel", json={"reason": "Holiday"})).status_code == 200
    assert (await _mark(client, w, session_date)).status_code == 201
    assert (await _mark(client, w, session_date + datetime.timedelta(days=5))).status_code == 201
