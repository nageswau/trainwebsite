"""itc-020 (DEC-SCOPE-342) -- the batch timetable: weekly slots (IT Admin), the trainer/batch overlap rule (409, T3), single-class
cancellation with the student notice, and the calendar feed scoped per role (student, trainer, IT counselor, admin)."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Batch, Enrollment, ItStudentCounselor, LiveSession, Notification, Program
from app.services.batch_timetable import _expand
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, make_student

IST = ZoneInfo("Asia/Kolkata")
FEED = "/api/v1/it/timetable"
MON, WED, FRI = 0, 2, 4


def today() -> dt.date:
    return dt.datetime.now(dt.UTC).astimezone(IST).date()


def slots_url(batch_id, tail: str = "") -> str:
    return f"/api/v1/it/batches/{batch_id}/timetable{tail}"


def slot(weekday=MON, start="19:00", end="21:00", mode="online", **extra) -> dict:
    return {"weekday": weekday, "start_time": start, "end_time": end, "mode": mode, **extra}


def next_weekday(weekday: int, after: dt.date | None = None) -> dt.date:
    base = (after or today()) + dt.timedelta(days=1)
    return base + dt.timedelta(days=(weekday - base.weekday()) % 7)


async def make_batch(db, *, trainer=None, start: dt.date | None = None, days: int = 60) -> Batch:
    program = Program(slug=f"itc020-{uuid.uuid4().hex[:8]}", category="Software Development", title=f"Python {uuid.uuid4().hex[:6]}", summary="",
                      duration="8 weeks", eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="T", active=True)  # fmt: skip
    db.add(program)
    await db.flush()
    start = start or today()
    batch = Batch(program_id=program.id, name=f"PY-{uuid.uuid4().hex[:6]}", start_date=start, end_date=start + dt.timedelta(days=days),
                  schedule="Mon/Wed/Fri 7-9 pm", capacity=20, enrollment_open=True, status="active", trainer_id=trainer.id if trainer else None)  # fmt: skip
    db.add(batch)
    await db.commit()
    return batch


async def seat(db, student, batch, status="active") -> None:
    db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-020-{uuid.uuid4().hex[:8]}", status=status))
    await db.commit()


async def admin(client, db):
    user = await make_user(db, "it_admin", "it")
    await as_user(client, user)
    return user


# --- occurrences (pure) -----------------------------------------------------------------------------------------------------------------


def test_weekly_slot_expands_inside_the_batch_dates_only():
    batch = Batch(start_date=dt.date(2026, 12, 2), end_date=dt.date(2026, 12, 16))  # Wed .. Wed
    row = type("S", (), {"weekday": MON})()
    assert list(_expand(row, batch, dt.date(2026, 11, 30), dt.date(2026, 12, 31))) == [dt.date(2026, 12, 7), dt.date(2026, 12, 14)]
    row.weekday = WED  # E: the batch ends in the middle of a week -- its last Wednesday is still a class
    assert list(_expand(row, batch, dt.date(2026, 12, 1), dt.date(2026, 12, 31))) == [dt.date(2026, 12, 2), dt.date(2026, 12, 9), dt.date(2026, 12, 16)]
    assert list(_expand(row, batch, dt.date(2027, 1, 1), dt.date(2027, 1, 31))) == []


# --- AC1: Mon/Wed/Fri 7-9 pm produce the right IST classes -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_admin_creates_mon_wed_fri_slots_and_the_feed_shows_ist_classes(client, db_session):
    trainer = await make_user(db_session, "trainer", "it")
    batch = await make_batch(db_session, trainer=trainer)
    user = await admin(client, db_session)
    for day in (MON, WED, FRI):
        response = await client.post(slots_url(batch.id), json=slot(day, meeting_url="https://meet.example/py", topic="Python basics"))
        assert response.status_code == 201, response.text
    listed = (await client.get(slots_url(batch.id))).json()["items"]
    assert [(s["day"], s["start_time"], s["end_time"]) for s in listed] == [("Monday", "19:00", "21:00"), ("Wednesday", "19:00", "21:00"), ("Friday", "19:00", "21:00")]
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "batch.timetable.create", AuditLog.entity_id == str(batch.id), AuditLog.user_id == user.id)) == 3

    start = today()
    body = (await client.get(FEED, params={"from": start.isoformat(), "to": (start + dt.timedelta(days=13)).isoformat(), "batch_id": str(batch.id)})).json()
    assert body["can_edit"] is True
    classes = [i for i in body["items"] if i["kind"] == "class"]
    assert len(classes) == 6  # 14 days = two of each weekday
    for item in classes:
        starts = dt.datetime.fromisoformat(item["starts_at"])
        assert starts.utcoffset() == dt.timedelta(hours=5, minutes=30)
        assert (starts.hour, starts.minute, starts.weekday()) == (19, 0, dt.date.fromisoformat(item["date"]).weekday())
        assert item["mode"] == "online" and item["meeting_url"] == "https://meet.example/py" and item["status"] == "scheduled"
    assert [i["starts_at"] for i in body["items"]] == sorted(i["starts_at"] for i in body["items"])


@pytest.mark.asyncio
async def test_slot_validation_is_422(client, db_session):
    batch = await make_batch(db_session)
    await admin(client, db_session)
    for bad in (slot(start="21:00", end="19:00"), slot(mode="offline"), slot(weekday=7), slot(mode="hybrid"), slot(meeting_url="javascript:alert(1)")):
        assert (await client.post(slots_url(batch.id), json=bad)).status_code == 422, bad
    created = await client.post(slots_url(batch.id), json=slot(mode="offline", room="  Lab 2  ", topic="  "))
    assert created.status_code == 201 and (created.json()["room"], created.json()["topic"]) == ("Lab 2", None)


# --- T3: overlaps --------------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overlapping_slots_in_one_batch_or_for_one_trainer_are_409(client, db_session):
    trainer = await make_user(db_session, "trainer", "it")
    first, second = await make_batch(db_session, trainer=trainer), await make_batch(db_session, trainer=trainer)
    later = await make_batch(db_session, trainer=trainer, start=today() + dt.timedelta(days=90))  # dates do not intersect
    await admin(client, db_session)
    assert (await client.post(slots_url(first.id), json=slot(MON))).status_code == 201
    same = await client.post(slots_url(first.id), json=slot(MON, start="20:00", end="22:00"))
    assert same.status_code == 409 and "Monday 19:00" in same.json()["detail"]
    clash = await client.post(slots_url(second.id), json=slot(MON, start="18:00", end="19:30"))
    assert clash.status_code == 409 and first.name in clash.json()["detail"]
    assert (await client.post(slots_url(second.id), json=slot(MON, start="21:00", end="22:00"))).status_code == 201  # touching is fine
    assert (await client.post(slots_url(later.id), json=slot(MON))).status_code == 201


@pytest.mark.asyncio
async def test_an_admin_edits_and_deletes_a_slot(client, db_session):
    batch = await make_batch(db_session)
    await admin(client, db_session)
    one = (await client.post(slots_url(batch.id), json=slot(MON))).json()
    two = (await client.post(slots_url(batch.id), json=slot(WED))).json()
    moved = await client.put(slots_url(batch.id, f"/{one['id']}"), json=slot(WED, start="06:00", end="07:00", topic="Early"))
    assert moved.status_code == 200 and (moved.json()["day"], moved.json()["topic"]) == ("Wednesday", "Early")
    assert (await client.put(slots_url(batch.id, f"/{one['id']}"), json=slot(WED))).status_code == 409  # onto slot two
    same = await client.put(slots_url(batch.id, f"/{two['id']}"), json=slot(WED))  # no change: no audit row
    assert same.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "batch.timetable.update", AuditLog.entity_id == str(batch.id))) == 1
    assert (await client.delete(slots_url(batch.id, f"/{one['id']}"))).status_code == 204
    assert [s["id"] for s in (await client.get(slots_url(batch.id))).json()["items"]] == [two["id"]]
    other = await make_batch(db_session)
    assert (await client.delete(slots_url(other.id, f"/{two['id']}"))).status_code == 404  # slot of another batch
    assert (await client.post(slots_url(uuid.uuid4()), json=slot())).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["trainer", "it_student", "counselor", "coordinator", "overseas_admin"])
async def test_only_the_it_admin_edits_a_timetable(client, db_session, role):
    batch = await make_batch(db_session)
    await as_user(client, await make_user(db_session, role, "overseas" if role == "overseas_admin" else "it"))
    assert (await client.get(slots_url(batch.id))).status_code == 403
    assert (await client.post(slots_url(batch.id), json=slot())).status_code == 403


# --- AC2: a cancelled class disappears for students, who are notified -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cancelled_class_disappears_for_students_and_they_are_notified(client, db_session):
    trainer = await make_user(db_session, "trainer", "it")
    batch = await make_batch(db_session, trainer=trainer)
    student, dropped = await make_student(db_session), await make_student(db_session)
    await seat(db_session, student, batch)
    await seat(db_session, dropped, batch, status="withdrawn")
    await admin(client, db_session)
    row = (await client.post(slots_url(batch.id), json=slot(FRI, meeting_url="https://meet.example/x"))).json()
    day = next_weekday(FRI)
    cancel = await client.post(slots_url(batch.id, f"/{row['id']}/cancellations"), json={"occurs_on": day.isoformat(), "reason": "Trainer unwell"})
    assert cancel.status_code == 201, cancel.text
    assert (await client.post(slots_url(batch.id, f"/{row['id']}/cancellations"), json={"occurs_on": day.isoformat(), "reason": "again"})).status_code == 409
    params = {"from": today().isoformat(), "to": (today() + dt.timedelta(days=20)).isoformat()}

    staff = (await client.get(FEED, params=params | {"batch_id": str(batch.id)})).json()["items"]
    gone = [i for i in staff if i["date"] == day.isoformat()]
    assert [(i["status"], i["cancel_reason"]) for i in gone] == [("cancelled", "Trainer unwell")]

    await as_user(client, trainer)
    assert [i["status"] for i in (await client.get(FEED, params=params)).json()["items"] if i["date"] == day.isoformat()] == ["cancelled"]

    await as_user(client, student)
    mine = (await client.get(FEED, params=params)).json()
    assert mine["can_edit"] is False and mine["items"] and day.isoformat() not in {i["date"] for i in mine["items"]}
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.event_type == "it.batch.changed"))
    assert note is not None and note.entity_id == str(batch.id) and note.action_url == "/it/student/timetable" and "Trainer unwell" not in note.body
    assert await db_session.scalar(select(Notification).where(Notification.user_id == dropped.id, Notification.event_type == "it.batch.changed")) is None
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "batch.timetable.cancel", AuditLog.entity_id == str(batch.id))) is not None


@pytest.mark.asyncio
async def test_cancelling_a_non_class_or_past_date_is_422(client, db_session):
    batch = await make_batch(db_session, start=today() - dt.timedelta(days=30))
    await admin(client, db_session)
    row = (await client.post(slots_url(batch.id), json=slot(MON))).json()
    url = slots_url(batch.id, f"/{row['id']}/cancellations")
    wrong_day = next_weekday(1)  # a Tuesday
    assert (await client.post(url, json={"occurs_on": wrong_day.isoformat(), "reason": "nope"})).status_code == 422
    past = next_weekday(MON, today() - dt.timedelta(days=15))
    assert (await client.post(url, json={"occurs_on": past.isoformat(), "reason": "late"})).status_code == 422
    after_end = next_weekday(MON, batch.end_date)
    assert (await client.post(url, json={"occurs_on": after_end.isoformat(), "reason": "after"})).status_code == 422
    assert (await client.post(url, json={"occurs_on": next_weekday(MON).isoformat(), "reason": "  "})).status_code == 422


# --- the feed's scope ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_role_sees_only_its_batches(client, db_session):
    trainer, other_trainer = await make_user(db_session, "trainer", "it"), await make_user(db_session, "trainer", "it")
    mine, theirs = await make_batch(db_session, trainer=trainer), await make_batch(db_session, trainer=other_trainer)
    student, stranger = await make_student(db_session), await make_student(db_session)
    await seat(db_session, student, mine)
    await seat(db_session, stranger, theirs)
    counselor = await make_user(db_session, "counselor", "it")
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    await admin(client, db_session)
    for batch in (mine, theirs):
        assert (await client.post(slots_url(batch.id), json=slot(next_weekday(MON).weekday(), meeting_url="https://meet.example/a"))).status_code == 201

    async def batches_seen(user, **params):
        await as_user(client, user)
        response = await client.get(FEED, params=params)
        return response.status_code, {i["batch_id"] for i in response.json().get("items", [])}, response

    for user in (trainer, student, counselor):
        status, seen, response = await batches_seen(user)
        assert (status, seen) == (200, {str(mine.id)}), user.role
        if user is counselor:
            assert all(i["meeting_url"] is None for i in response.json()["items"])  # not a batch member
        assert (await batches_seen(user, batch_id=str(theirs.id)))[0] == 404
    for role, division in (("overseas_student", "overseas"), ("telecaller", "it"), ("counselor", "overseas")):
        assert (await batches_seen(await make_user(db_session, role, division)))[0] == 403


@pytest.mark.asyncio
async def test_a_student_without_an_active_enrolment_sees_nothing_and_live_sessions_merge_in(client, db_session):
    batch = await make_batch(db_session)
    pending, student = await make_student(db_session), await make_student(db_session)
    await seat(db_session, pending, batch, status="pending_consent")
    await seat(db_session, student, batch)
    starts = dt.datetime.combine(next_weekday(WED), dt.time(10, 0), IST)
    db_session.add(LiveSession(batch_id=batch.id, title="Guest lecture", starts_at=starts, ends_at=starts + dt.timedelta(hours=1), meeting_url="https://meet.example/g"))
    db_session.add(LiveSession(batch_id=batch.id, title="Called off", starts_at=starts + dt.timedelta(hours=3), status="cancelled", cancel_reason="x"))
    await db_session.commit()
    await as_user(client, pending)
    assert (await client.get(FEED)).json()["items"] == []
    await as_user(client, student)
    items = (await client.get(FEED)).json()["items"]
    assert [(i["kind"], i["topic"]) for i in items] == [("live_session", "Guest lecture")]


@pytest.mark.asyncio
async def test_the_window_is_bounded(client, db_session):
    await admin(client, db_session)
    start = today()
    assert (await client.get(FEED, params={"from": start.isoformat(), "to": (start + dt.timedelta(days=62)).isoformat()})).status_code == 422
    assert (await client.get(FEED, params={"from": start.isoformat(), "to": (start - dt.timedelta(days=1)).isoformat()})).status_code == 422
    body = (await client.get(FEED)).json()
    assert (body["from"], body["to"]) == (start.isoformat(), (start + dt.timedelta(days=13)).isoformat())


# --- the Timetable page header per role ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "path", "status"), [
    ("it_student", "it", "it/student", 200), ("trainer", "it", "it/trainer", 200), ("counselor", "it", "it/counselor", 200),
    ("it_admin", "it", "it/admin", 200), ("overseas_admin", "overseas", "overseas/admin", 404),
])  # fmt: skip
async def test_the_timetable_page_exists_for_the_it_roles(client, db_session, role, division, path, status):
    await as_user(client, await make_user(db_session, role, division))
    response = await client.get(f"/api/v1/portal/{path}/timetable")
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()["title"] == "Timetable"
