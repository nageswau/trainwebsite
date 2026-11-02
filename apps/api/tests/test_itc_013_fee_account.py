"""itc-013 (DEC-SCOPE-344) -- the per-enrolment fee account: one computed definition (`services/fee_accounts.py`, Q-13), staff recording
a partial or full offline payment with its mode and transaction reference, the receipt carrying both, and who may read an account
(the student their own, the IT counselor their linked students, a `payments.view` holder in IT)."""

import datetime
import uuid

import pytest
from sqlalchemy import func, select

from app.api.payments import _receipt_lines
from app.models import AuditLog, Batch, Enrollment, ItStudentCounselor, Payment, Program, Receipt, User
from app.services import fee_accounts, student_access
from tests.agn011_helpers import captured, razorpay_on, signed
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import login

API = "/api/v1"
MINE = f"{API}/it/student/fee-accounts"


def account_url(enrollment) -> str:
    return f"{API}/it/enrollments/{enrollment.id}/fee-account"


def record_url(enrollment) -> str:
    return f"{API}/it/enrollments/{enrollment.id}/payments"


async def enrolled(db, fee: float | None = 45000, *, student: User | None = None) -> tuple[User, Enrollment]:
    """An IT student enrolled in a fresh batch; `fee` is billed the way enrolling bills it (one pending `enrollment_fee`), None bills nothing."""
    tag = uuid.uuid4().hex[:8]
    student = student or await make_user(db, "it_student", "it")
    trainer = await make_user(db, "trainer", "it")
    program = Program(slug=f"i013-{tag}", title=f"I013 Course {tag}", category="Testing", summary="-", duration="3 months", eligibility="-",
                      fees=fee or 0, certification="-", placement_assistance="-", trainer_name="-")  # fmt: skip
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, trainer_id=trainer.id, name=f"I013-{tag}", start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 4, 1),
                  schedule="-", capacity=40, enrollment_open=True, status="active")  # fmt: skip
    db.add(batch)
    await db.flush()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"I013-{tag}", status="active")
    db.add(enrollment)
    await db.flush()
    if fee:
        db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=fee, status="pending", is_manual=True))
    await db.commit()
    return student, enrollment


async def figures(db, enrollment) -> dict:
    return (await fee_accounts.balance_for(db, [enrollment.id]))[enrollment.id]


async def rows(db, enrollment) -> list[Payment]:
    stmt = select(Payment).where(Payment.reference_id == enrollment.id).order_by(Payment.created_at).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def as_admin(client, db) -> User:
    admin = await make_user(db, "it_admin", "it")
    await login(client, admin)
    return admin


# --- the one definition (AC1, AC2, AC5) ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_billed_enrolment_owes_its_whole_fee(db_session):
    _, enrollment = await enrolled(db_session)
    assert await figures(db_session, enrollment) == {
        "course_fee": 45000.0, "discount_approved": 0.0, "tax": 0.0, "total_payable": 45000.0, "paid_confirmed": 0.0, "credits": 0.0,
        "balance": 45000.0, "state": "enrolled_pending_payment",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_a_pending_or_failed_payment_never_counts_as_paid(db_session):
    student, enrollment = await enrolled(db_session, 30000)
    db_session.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=5000, status="failed", provider="razorpay"))
    await db_session.commit()
    got = await figures(db_session, enrollment)
    assert (got["paid_confirmed"], got["balance"], got["course_fee"]) == (0.0, 30000.0, 30000.0)


@pytest.mark.asyncio
async def test_a_legacy_enrolment_with_no_payment_row_is_not_billed(db_session):
    student, enrollment = await enrolled(db_session, None)
    got = await figures(db_session, enrollment)
    assert (got["total_payable"], got["balance"], got["state"]) == (0.0, 0.0, "not_billed")
    assert await student_access.student_state(db_session, student.id) == "fully_paid"  # the access state already treats it as owing nothing


@pytest.mark.asyncio
async def test_balance_for_answers_many_enrolments_in_one_query(db_session):
    enrolments = [(await enrolled(db_session, fee))[1] for fee in (1000, 2000, 3000)]
    queries = []

    def count(*_):
        queries.append(1)

    from sqlalchemy import event

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", count)
    try:
        got = await fee_accounts.balance_for(db_session, [e.id for e in enrolments])
    finally:
        event.remove(sync_engine, "before_cursor_execute", count)
    assert [got[e.id]["balance"] for e in enrolments] == [1000.0, 2000.0, 3000.0] and len(queries) == 1
    assert await fee_accounts.balance_for(db_session, []) == {}


# --- recording payments (AC3, the + scenario) ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_partial_payments_clear_a_45000_fee(client, db_session):
    student, enrollment = await enrolled(db_session)
    admin = await as_admin(client, db_session)
    first = await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "upi", "provider_reference": "UPI-123"})
    assert first.status_code == 201, first.text
    assert (first.json()["account"]["balance"], first.json()["account"]["state"]) == (25000.0, "partially_paid")
    assert await student_access.student_state(db_session, student.id) == "partially_paid"  # AC5: the access state agrees
    second = await client.post(record_url(enrollment), json={"amount": 25000, "payment_mode": "cash"})
    assert second.status_code == 201, second.text
    account = second.json()["account"]
    assert (account["course_fee"], account["paid_confirmed"], account["balance"], account["state"]) == (45000.0, 45000.0, 0.0, "fully_paid")
    assert await student_access.student_state(db_session, student.id) == "fully_paid"
    paid = await rows(db_session, enrollment)
    assert sorted((float(p.amount), p.status, p.payment_mode, p.provider_reference) for p in paid) == [
        (20000.0, "paid", "upi", "UPI-123"), (25000.0, "paid", "cash", None)]  # fmt: skip
    receipts = await db_session.scalar(select(func.count()).select_from(Receipt).where(Receipt.payment_id.in_([p.id for p in paid])))
    assert receipts == 2
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.fee.payment_recorded", AuditLog.entity_id == str(enrollment.id), AuditLog.user_id == admin.id).limit(1))
    assert audit.metadata_json["changes"]["balance"] == [45000.0, 25000.0] and "payment_id" in audit.metadata_json


@pytest.mark.asyncio
async def test_a_discount_after_a_partial_payment_lowers_only_the_balance(client, db_session):
    _, enrollment = await enrolled(db_session, 40000)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 10000, "payment_mode": "card"})).status_code == 201
    owed = next(p for p in await rows(db_session, enrollment) if p.status == "pending")
    response = await client.post(f"{API}/admin/payments/{owed.id}/discount", json={"amount": 25000, "reason": "Scholarship"})
    assert response.status_code == 200, response.text
    got = await figures(db_session, enrollment)
    assert (got["course_fee"], got["discount_approved"], got["total_payable"], got["paid_confirmed"], got["balance"]) == (40000.0, 5000.0, 35000.0, 10000.0, 25000.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, message",
    [
        ({"amount": 45000.01, "payment_mode": "cash"}, "at most"),  # Q-13: never more than is owed, so no overpayment
        ({"amount": 0, "payment_mode": "cash"}, None),
        ({"amount": 100, "payment_mode": "razorpay"}, None),  # only the gateway records razorpay
        ({"amount": 100, "payment_mode": "bitcoin"}, None),
        ({"amount": 100}, None),
    ],
)
async def test_an_invalid_payment_is_refused_and_changes_nothing(client, db_session, body, message):
    _, enrollment = await enrolled(db_session)
    await as_admin(client, db_session)
    response = await client.post(record_url(enrollment), json=body)
    assert response.status_code == 422, response.text
    if message:
        assert message in response.text
    assert (await figures(db_session, enrollment))["balance"] == 45000.0 and len(await rows(db_session, enrollment)) == 1


@pytest.mark.asyncio
async def test_a_fully_paid_or_unbilled_enrolment_takes_no_payment(client, db_session):
    _, unbilled = await enrolled(db_session, None)
    _, enrollment = await enrolled(db_session, 1000)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 1000, "payment_mode": "cheque", "provider_reference": "CHQ 000123"})).status_code == 201
    for target in (enrollment, unbilled):
        response = await client.post(record_url(target), json={"amount": 1, "payment_mode": "cash"})
        assert response.status_code == 409 and "Nothing is owed" in response.text


@pytest.mark.asyncio
async def test_recording_needs_the_payments_add_grant_and_an_it_enrolment(client, db_session):
    _, enrollment = await enrolled(db_session)
    for role, division, status in (("trainer", "it", 403), ("counselor", "it", 403), ("overseas_admin", "overseas", 404)):
        await login(client, await make_user(db_session, role, division))
        assert (await client.post(record_url(enrollment), json={"amount": 10, "payment_mode": "cash"})).status_code == status, role
    await as_admin(client, db_session)
    assert (await client.post(f"{API}/it/enrollments/{uuid.uuid4()}/payments", json={"amount": 10, "payment_mode": "cash"})).status_code == 404
    typo = await client.post(f"{API}/it/enrollments/not-a-reference/payments", json={"amount": 10, "payment_mode": "cash"})
    assert (typo.status_code, typo.json()["detail"]) == (422, "A valid enrolment reference is required")  # QA13-02: a plain message
    assert (await figures(db_session, enrollment))["balance"] == 45000.0


@pytest.mark.asyncio
async def test_a_split_clears_a_stale_online_checkout_on_the_remaining_bill(client, db_session):
    _, enrollment = await enrolled(db_session)
    bill = (await rows(db_session, enrollment))[0]
    bill.provider, bill.checkout_provider_order_id, bill.checkout_idempotency_key = "razorpay", "order_stale", "key-1"
    await db_session.commit()
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 5000, "payment_mode": "cash"})).status_code == 201
    remaining = next(p for p in await rows(db_session, enrollment) if p.status == "pending")
    assert (float(remaining.amount), remaining.provider, remaining.checkout_provider_order_id, remaining.checkout_idempotency_key) == (40000.0, "manual", None, None)


# --- the receipt (AC4) ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_receipt_carries_mode_reference_and_the_account_balance(client, db_session):
    student, enrollment = await enrolled(db_session)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 20000, "payment_mode": "bank_transfer", "provider_reference": "NEFT-77"})).status_code == 201
    paid = next(p for p in await rows(db_session, enrollment) if p.status == "paid")
    lines = dict(await _receipt_lines(db_session, paid, student, "RCPT-X"))
    assert (lines["Payment mode"], lines["Transaction reference"], lines["Amount paid"], lines["Remaining balance"]) == ("Bank transfer", "NEFT-77", "INR 20,000.00", "INR 25,000.00")
    assert lines["Payment status"] == "Partially paid"


@pytest.mark.asyncio
async def test_a_gateway_payment_is_recorded_as_razorpay(client, db_session, monkeypatch):
    student, enrollment = await enrolled(db_session, 1500)
    bill = (await rows(db_session, enrollment))[0]
    bill.provider, bill.checkout_provider_order_id = "razorpay", f"order_{uuid.uuid4().hex[:10]}"
    await db_session.commit()
    razorpay_on(monkeypatch)
    body = captured(bill.checkout_provider_order_id, 150000)
    raw, headers = signed(body)
    response = await client.post(f"{API}/payments/webhooks/razorpay", content=raw, headers=headers)
    assert response.status_code == 200, response.text
    gateway_id = body["payload"]["payment"]["entity"]["id"]
    paid = (await rows(db_session, enrollment))[0]
    assert (paid.status, paid.payment_mode, paid.provider_reference) == ("paid", "razorpay", gateway_id)
    lines = dict(await _receipt_lines(db_session, paid, student, "RCPT-Y"))
    assert (lines["Payment mode"], lines["Transaction reference"], lines["Remaining balance"]) == ("Razorpay", gateway_id, "INR 0.00")
    await login(client, student)
    listed = next(p for p in (await client.get(f"{API}/payments/mine")).json() if p["id"] == str(paid.id))
    assert (listed["payment_mode"], listed["provider_reference"]) == ("razorpay", gateway_id)


@pytest.mark.asyncio
async def test_an_admin_recorded_payment_takes_a_valid_mode(client, db_session):
    student = await make_user(db_session, "it_student", "it")
    await as_admin(client, db_session)
    base = {"user_id": str(student.id), "amount": 500, "status": "paid", "provider": "manual"}
    assert (await client.post(f"{API}/admin/payments", json={**base, "payment_mode": "bitcoin"})).status_code == 422
    created = await client.post(f"{API}/admin/payments", json={**base, "payment_mode": "cheque", "provider_reference": "CHQ-9"})
    assert created.status_code == 201, created.text
    listed = next(p for p in (await client.get(f"{API}/admin/payments")).json() if p["id"] == created.json()["id"])
    assert (listed["payment_mode"], listed["provider_reference"]) == ("cheque", "CHQ-9")


# --- who reads an account -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_student_reads_only_their_own_accounts(client, db_session):
    student, enrollment = await enrolled(db_session, 12000)
    _, second = await enrolled(db_session, 3000, student=student)
    _, other = await enrolled(db_session)
    await login(client, student)
    response = await client.get(account_url(enrollment))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["enrollment_id"], body["balance"], body["currency"]) == (str(enrollment.id), 12000.0, "INR") and body["course"].startswith("I013 Course")
    assert (await client.get(account_url(other))).status_code == 404
    listed = (await client.get(MINE)).json()
    assert {a["enrollment_id"]: a["balance"] for a in listed} == {str(enrollment.id): 12000.0, str(second.id): 3000.0}


@pytest.mark.asyncio
async def test_the_it_counselor_reads_only_linked_students(client, db_session):
    student, enrollment = await enrolled(db_session)
    _, other = await enrolled(db_session)
    counselor = await make_user(db_session, "counselor", "it")
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    await login(client, counselor)
    assert (await client.get(account_url(enrollment))).json()["balance"] == 45000.0
    assert (await client.get(account_url(other))).status_code == 404
    assert (await client.get(MINE)).status_code == 403


@pytest.mark.asyncio
async def test_staff_read_needs_payments_view_in_it(client, db_session):
    _, enrollment = await enrolled(db_session)
    await as_admin(client, db_session)
    assert (await client.get(account_url(enrollment))).status_code == 200
    for role, division, status in (("trainer", "it", 403), ("counselor", "overseas", 403), ("overseas_admin", "overseas", 404)):
        await login(client, await make_user(db_session, role, division))
        assert (await client.get(account_url(enrollment))).status_code == status, role
    assert (await client.get(f"{API}/it/enrollments/{uuid.uuid4()}/fee-account")).status_code == 404


# --- the list pages' balance column (batched) ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_counselor_students_page_shows_each_students_balance(client, db_session):
    student, _ = await enrolled(db_session, 9000)
    unbilled, _ = await enrolled(db_session, None)
    counselor = await make_user(db_session, "counselor", "it")
    for linked_student in (student, unbilled):
        db_session.add(ItStudentCounselor(student_user_id=linked_student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    await login(client, counselor)
    page = (await client.get(f"{API}/portal/it/counselor/students")).json()
    assert {"key": "fee_balance", "label": "Fee balance"} in page["columns"]
    balances = {row["id"]: row["fee_balance"] for row in page["rows"]}
    assert balances == {str(student.id): "INR 9,000.00", str(unbilled.id): "Not billed"}


@pytest.mark.asyncio
async def test_the_admin_enrolments_page_shows_each_enrolments_balance(client, db_session):
    _, enrollment = await enrolled(db_session, 7000)
    await as_admin(client, db_session)
    assert (await client.post(record_url(enrollment), json={"amount": 2000, "payment_mode": "cash"})).status_code == 201
    page = (await client.get(f"{API}/portal/it/admin/enrollments")).json()
    assert {"key": "fee_balance", "label": "Fee balance"} in page["columns"]
    row = next(r for r in page["rows"] if r["id"] == str(enrollment.id))
    assert row["fee_balance"] == "INR 5,000.00"
