"""itc-025 (DEC-SCOPE-346) -- a batch date/trainer/timetable change or a student transfer notifies the affected students and their linked
IT counselors (one notice each, AC1), with a fixed-vocabulary summary of what changed; a no-op save sends nothing (AC2)."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import func, select

from app.models import Enrollment, ItStudentCounselor, Notification
from app.notifications.events import notify
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, make_student
from tests.test_itc_020_timetable import admin, make_batch, next_weekday, seat, slot, slots_url

STUDENT_EVENT, COUNSELOR_EVENT = "it.batch.changed", "it.batch.student_changed"


async def link(db, student, counselor) -> None:
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()


async def notices(db, user, event: str) -> list[Notification]:
    return list(await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.event_type == event)))


async def count(db, users, event: str) -> int:
    return await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id.in_([u.id for u in users]), Notification.event_type == event)) or 0


async def classroom(db, *, students: int = 3, counselors: int = 2):
    """A batch with `students` active students spread over `counselors` IT counselors, plus a withdrawn student with a counselor."""
    trainer = await make_user(db, "trainer", "it")
    batch = await make_batch(db, trainer=trainer)
    advisers = [await make_user(db, "counselor", "it") for _ in range(counselors)]
    kids = []
    for i in range(students):
        kid = await make_student(db)
        await seat(db, kid, batch)
        await link(db, kid, advisers[i % counselors])
        kids.append(kid)
    dropped, dropped_adviser = await make_student(db), await make_user(db, "counselor", "it")
    await seat(db, dropped, batch, status="withdrawn")
    await link(db, dropped, dropped_adviser)
    return batch, kids, advisers, dropped, dropped_adviser


# --- the catalogue: a summary from a fixed vocabulary, never values -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_appends_the_changed_field_labels_and_refuses_unknown_keys(db_session):
    student = await make_student(db_session)
    [note] = await notify(db_session, [student], STUDENT_EVENT, uuid.uuid4(), changes=("trainer", "start_date"))
    assert note.body.endswith("Changed: trainer, start date.")
    with pytest.raises(ValueError):
        await notify(db_session, [student], STUDENT_EVENT, uuid.uuid4(), changes=("Trainer is Ravi",))
    await db_session.rollback()


# --- batch PATCH ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_trainer_change_notifies_each_student_and_each_linked_counselor_once(client, db_session):
    batch, kids, advisers, dropped, dropped_adviser = await classroom(db_session, students=4, counselors=2)
    new_trainer = await make_user(db_session, "trainer", "it")
    await admin(client, db_session)
    response = await client.patch(f"/api/v1/admin/batches/{batch.id}", json={"trainer_id": str(new_trainer.id), "capacity": 20})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(batch.id), "status": "active", "capacity": 20}  # the response contract is unchanged

    assert await count(db_session, kids, STUDENT_EVENT) == 4
    assert await count(db_session, advisers, COUNSELOR_EVENT) == 2  # 2 students each, still one notice each
    [note] = await notices(db_session, kids[0], STUDENT_EVENT)
    assert note.entity_type == "batch" and note.entity_id == str(batch.id) and note.action_url == "/it/student/course"
    assert note.body.endswith("Changed: trainer.") and new_trainer.full_name not in note.body
    [seen] = await notices(db_session, advisers[0], COUNSELOR_EVENT)
    assert seen.action_url == "/it/counselor/timetable" and seen.body.endswith("Changed: trainer.")
    assert await notices(db_session, dropped, STUDENT_EVENT) == [] and await notices(db_session, dropped_adviser, COUNSELOR_EVENT) == []


@pytest.mark.asyncio
async def test_dates_and_schedule_are_summarised_together(client, db_session):
    batch, kids, *_ = await classroom(db_session, students=1, counselors=1)
    await admin(client, db_session)
    end = (batch.end_date + dt.timedelta(days=7)).isoformat()
    response = await client.patch(f"/api/v1/admin/batches/{batch.id}", json={"end_date": end, "schedule": "Tue/Thu 6-8 pm"})
    assert response.status_code == 200, response.text
    [note] = await notices(db_session, kids[0], STUDENT_EVENT)
    assert note.body.endswith("Changed: end date, timetable.")


@pytest.mark.asyncio
async def test_a_no_op_or_admin_only_save_sends_nothing(client, db_session):
    batch, kids, advisers, *_ = await classroom(db_session, students=2, counselors=1)
    await admin(client, db_session)
    same = {"name": batch.name, "start_date": batch.start_date.isoformat(), "schedule": batch.schedule, "trainer_id": str(batch.trainer_id)}
    assert (await client.patch(f"/api/v1/admin/batches/{batch.id}", json=same)).status_code == 200
    assert (await client.patch(f"/api/v1/admin/batches/{batch.id}", json={"capacity": 15, "enrollment_open": False})).status_code == 200
    refused = await client.patch(f"/api/v1/admin/batches/{batch.id}", json={"schedule": "Sat 9-11 am", "trainer_id": str(uuid.uuid4())})
    assert refused.status_code == 422  # an invalid edit changes nothing and tells nobody
    assert await count(db_session, kids, STUDENT_EVENT) == 0 and await count(db_session, advisers, COUNSELOR_EVENT) == 0


# --- the timetable (itc-020 service) ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slot_add_edit_and_remove_notify_students_and_counselors(client, db_session):
    batch, kids, advisers, *_ = await classroom(db_session, students=2, counselors=1)
    await admin(client, db_session)
    row = (await client.post(slots_url(batch.id), json=slot())).json()
    assert await count(db_session, kids, STUDENT_EVENT) == 2 and await count(db_session, advisers, COUNSELOR_EVENT) == 1
    [note] = await notices(db_session, kids[0], STUDENT_EVENT)
    assert note.action_url == "/it/student/timetable" and note.body.endswith("Changed: timetable.")

    assert (await client.put(slots_url(batch.id, f"/{row['id']}"), json=slot())).status_code == 200  # unchanged -> nothing
    assert await count(db_session, kids, STUDENT_EVENT) == 2
    assert (await client.put(slots_url(batch.id, f"/{row['id']}"), json=slot(start="18:00"))).status_code == 200
    assert await count(db_session, kids, STUDENT_EVENT) == 4 and await count(db_session, advisers, COUNSELOR_EVENT) == 2
    assert (await client.delete(slots_url(batch.id, f"/{row['id']}"))).status_code == 204
    assert await count(db_session, kids, STUDENT_EVENT) == 6 and await count(db_session, advisers, COUNSELOR_EVENT) == 3


@pytest.mark.asyncio
async def test_a_cancelled_class_also_tells_the_counselor_without_the_reason(client, db_session):
    batch, kids, advisers, *_ = await classroom(db_session, students=1, counselors=1)
    await admin(client, db_session)
    row = (await client.post(slots_url(batch.id), json=slot(weekday=4))).json()
    cancel = await client.post(slots_url(batch.id, f"/{row['id']}/cancellations"), json={"occurs_on": next_weekday(4).isoformat(), "reason": "Trainer unwell"})
    assert cancel.status_code == 201, cancel.text
    notes = await notices(db_session, advisers[0], COUNSELOR_EVENT)
    assert sorted(n.body.rsplit("Changed: ", 1)[1] for n in notes) == ["cancelled class.", "timetable."]
    assert all("Trainer unwell" not in n.body for n in notes)


# --- the transfer -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transfer_notifies_only_the_moved_student_and_their_counselor(client, db_session):
    source, kids, advisers, *_ = await classroom(db_session, students=2, counselors=2)
    target, others, other_advisers, *_ = await classroom(db_session, students=1, counselors=1)
    moved = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == kids[0].id, Enrollment.batch_id == source.id))
    await admin(client, db_session)
    assert (await client.patch(f"/api/v1/admin/enrollments/{moved.id}", json={"batch_id": str(source.id)})).status_code == 200  # same batch
    assert await count(db_session, kids, STUDENT_EVENT) == 0

    response = await client.patch(f"/api/v1/admin/enrollments/{moved.id}", json={"batch_id": str(target.id)})
    assert response.status_code == 200, response.text
    [note] = await notices(db_session, kids[0], STUDENT_EVENT)
    assert note.entity_id == str(target.id) and note.body.endswith("Changed: batch.") and note.action_url == "/it/student/course"
    assert len(await notices(db_session, advisers[0], COUNSELOR_EVENT)) == 1
    assert await notices(db_session, kids[1], STUDENT_EVENT) == [] and await notices(db_session, advisers[1], COUNSELOR_EVENT) == []
    assert await count(db_session, others, STUDENT_EVENT) == 0 and await count(db_session, other_advisers, COUNSELOR_EVENT) == 0


@pytest.mark.asyncio
async def test_a_status_only_enrolment_update_sends_nothing(client, db_session):
    batch, kids, advisers, *_ = await classroom(db_session, students=1, counselors=1)
    item = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == kids[0].id, Enrollment.batch_id == batch.id))
    await admin(client, db_session)
    assert (await client.patch(f"/api/v1/admin/enrollments/{item.id}", json={"progress_percent": 40})).status_code == 200
    assert await count(db_session, kids, STUDENT_EVENT) == 0 and await count(db_session, advisers, COUNSELOR_EVENT) == 0


# --- the IT counselor's Notifications page -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_it_counselor_has_a_notifications_section(client, db_session):
    counselor = await make_user(db_session, "counselor", "it")
    await as_user(client, counselor)
    response = await client.get("/api/v1/portal/it/counselor/notifications")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Notifications"
