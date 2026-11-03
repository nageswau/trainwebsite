"""itc-018 (DEC-SCOPE-353) -- the IT student's fee summary (the itc-013 account plus the next amount due) and course details (effective
dates and mode, room or link), and another student's receipt answering 404 (AC2)."""

import datetime

import pytest
from sqlalchemy import event

from app.models import Batch, BatchTimetableSlot, Payment, Receipt
from app.services import fee_accounts
from tests.bdm001_helpers import make_user
from tests.test_itc_013_fee_account import as_admin, enrolled, record_url
from tests.upc001_helpers import login

API = "/api/v1"
MINE = f"{API}/it/student/fee-accounts"
COURSE = f"{API}/portal/it/student/course"


def receipt_url(payment_id) -> str:
    return f"{API}/payments/{payment_id}/receipt"


async def mine(client, student) -> dict:
    await login(client, student)
    response = await client.get(MINE)
    assert response.status_code == 200, response.text
    return {a["enrollment_id"]: a for a in response.json()}


# --- the fee summary: next due (AC1, the + scenario, E) -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_partial_payment_shows_the_balance_and_the_next_due(client, db_session):
    student, enrollment = await enrolled(db_session, 45000)
    bill = (await db_session.execute(Payment.__table__.select().where(Payment.reference_id == enrollment.id))).first()
    await db_session.execute(Payment.__table__.update().where(Payment.id == bill.id).values(due_date=datetime.date(2026, 12, 10)))
    await db_session.commit()
    await as_admin(client, db_session)
    paid = await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "cash"})
    assert paid.status_code == 201, paid.text
    account = (await mine(client, student))[str(enrollment.id)]
    assert account["balance"] == 25000.0
    assert account["next_due"] == {"amount": 25000.0, "due_date": "2026-12-10"}
    # AC1: the same balance the accounts team reads
    assert account["balance"] == (await fee_accounts.balance_for(db_session, [enrollment.id]))[enrollment.id]["balance"]


@pytest.mark.asyncio
async def test_the_next_due_is_the_oldest_owed_bill_by_due_date(client, db_session):
    student, enrollment = await enrolled(db_session, 10000)
    await db_session.execute(Payment.__table__.update().where(Payment.reference_id == enrollment.id).values(due_date=datetime.date(2027, 1, 5)))
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=4000, status="overdue",
                           is_manual=True, due_date=datetime.date(2026, 11, 1)))  # fmt: skip
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=3000, status="pending",
                           is_manual=True))  # no due date: last  # fmt: skip
    await db_session.commit()
    account = (await mine(client, student))[str(enrollment.id)]
    assert account["next_due"] == {"amount": 4000.0, "due_date": "2026-11-01"} and account["balance"] == 17000.0


@pytest.mark.asyncio
async def test_an_owed_bill_without_a_due_date_is_still_the_next_due(client, db_session):
    student, enrollment = await enrolled(db_session, 8000)
    assert (await mine(client, student))[str(enrollment.id)]["next_due"] == {"amount": 8000.0, "due_date": None}


@pytest.mark.asyncio
async def test_a_fully_paid_unbilled_or_zero_fee_enrolment_has_no_next_due(client, db_session):
    student, paid = await enrolled(db_session, 5000)
    _, unbilled = await enrolled(db_session, None, student=student)
    _, scholarship = await enrolled(db_session, None, student=student)
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=scholarship.id, amount=0,
                           discount_amount=30000, status="pending", is_manual=True))  # a 100 % discount  # fmt: skip
    await db_session.commit()
    await as_admin(client, db_session)
    assert (await client.post(record_url(paid), json={"amount": 5000, "payment_mode": "upi"})).status_code == 201
    accounts = await mine(client, student)
    assert accounts[str(paid.id)]["state"] == "fully_paid" and accounts[str(paid.id)]["next_due"] is None
    assert accounts[str(unbilled.id)]["state"] == "not_billed" and accounts[str(unbilled.id)]["next_due"] is None
    assert accounts[str(scholarship.id)]["balance"] == 0.0 and accounts[str(scholarship.id)]["next_due"] is None


@pytest.mark.asyncio
async def test_accounts_reads_many_enrolments_in_a_fixed_number_of_queries(db_session):
    async def count_for(n: int) -> int:
        enrolments = [(await enrolled(db_session, 1000 * (i + 1)))[1] for i in range(n)]
        queries = []

        def count(*_):
            queries.append(1)

        sync_engine = db_session.bind.sync_engine
        event.listen(sync_engine, "before_cursor_execute", count)
        try:
            got = await fee_accounts.accounts(db_session, enrolments)
        finally:
            event.remove(sync_engine, "before_cursor_execute", count)
        assert all(a["next_due"] is not None for a in got)
        return len(queries)

    assert await count_for(1) == await count_for(4) == 4  # itc-015: + the adjustments query


# --- AC2: another student's receipt is 404 ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_students_receipt_is_404_and_the_owners_is_200(client, db_session):
    student, enrollment = await enrolled(db_session, 6000)
    await as_admin(client, db_session)
    payment_id = (await client.post(record_url(enrollment), json={"amount": 6000, "payment_mode": "cash"})).json()["payment"]["id"]
    assert await db_session.scalar(Receipt.__table__.select().where(Receipt.payment_id == payment_id).with_only_columns(Receipt.id)) is not None
    stranger = await make_user(db_session, "it_student", "it")
    await login(client, stranger)
    other = await client.get(receipt_url(payment_id))
    assert other.status_code == 404 and other.json()["detail"] == "Payment not found"
    assert (await client.get(receipt_url("00000000-0000-0000-0000-000000000000"))).status_code == 404  # the same answer as a missing id
    await login(client, student)
    assert (await client.get(receipt_url(payment_id))).status_code == 200
    await as_admin(client, db_session)  # an IT admin still reads any IT receipt
    assert (await client.get(receipt_url(payment_id))).status_code == 200


# --- course details (dates, mode, room or link) -------------------------------------------------------------------------------------


async def course_rows(client, student) -> dict:
    await login(client, student)
    response = await client.get(COURSE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"start_date", "end_date", "mode", "room_or_link"} <= {c["key"] for c in body["columns"]}
    return body, {r["enrollment_id"]: r for r in body["rows"]}


@pytest.mark.asyncio
async def test_course_rows_carry_the_effective_dates_mode_and_rooms(client, db_session):
    student, enrollment = await enrolled(db_session, None)
    batch = await db_session.get(Batch, enrollment.batch_id)
    batch.mode = "Hybrid"
    enrollment.start_date, enrollment.delivery_mode = datetime.date(2026, 2, 1), "Offline"  # itc-012 overrides win
    for weekday, room in ((0, "Lab 2"), (2, "Lab 2"), (4, "Room 101")):
        db_session.add(BatchTimetableSlot(batch_id=batch.id, weekday=weekday, start_time=datetime.time(10), end_time=datetime.time(12), mode="offline", room=room))
    await db_session.commit()
    _, rows = await course_rows(client, student)
    row = rows[enrollment.enrollment_code]
    assert (row["start_date"], row["end_date"], row["mode"]) == ("2026-02-01", "2026-04-01", "Offline")
    assert row["room_or_link"] == "Lab 2, Room 101"


@pytest.mark.asyncio
async def test_an_online_class_points_to_the_timetable_and_never_carries_the_url(client, db_session):
    student, enrollment = await enrolled(db_session, None)
    db_session.add(BatchTimetableSlot(batch_id=enrollment.batch_id, weekday=1, start_time=datetime.time(18), end_time=datetime.time(19), mode="online",
                                      meeting_url="https://meet.example.test/secret-room"))  # fmt: skip
    db_session.add(BatchTimetableSlot(batch_id=enrollment.batch_id, weekday=3, start_time=datetime.time(18), end_time=datetime.time(19), mode="offline", room="Lab 1"))
    await db_session.commit()
    _, other = await enrolled(db_session, None, student=student)  # no timetable yet
    body, rows = await course_rows(client, student)
    assert rows[enrollment.enrollment_code]["room_or_link"] == "Lab 1; Online (join link in your Timetable)"
    assert rows[other.enrollment_code]["room_or_link"] == "Not scheduled yet"
    assert (rows[other.enrollment_code]["start_date"], rows[other.enrollment_code]["mode"]) == ("2026-01-01", "Online")  # the batch's
    assert "secret-room" not in str(body) and "https://" not in str(body)
