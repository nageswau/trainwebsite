"""nehn-019 -- payment discount ledger and complete receipt (DEC-SCOPE-315; spec
docs/superpowers/specs/2026-10-28-nehn-019-discount-ledger-complete-receipt-design.md, API §12HM): a discount keeps the gross amount
(AC2), `paid_at` is recorded, the receipt shows every listed field (AC1) and "—" for what is unknown (AC3), and `amount` stays net (AC4).
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.api.payments import _mark_paid
from app.models import Batch, Enrollment, Payment, Program, Receipt, User
from app.services.billing_documents import receipt_lines
from app.services.storage import storage
from tests.bdm001_helpers import login, make_user
from tests.nehn019_helpers import receipt_rows

API = "/api/v1"


async def _enrolment(db, student: User) -> Enrollment:
    tag = uuid.uuid4().hex[:8]
    program = Program(
        slug=f"n019-{tag}",
        title=f"N019 Data Science {tag}",
        category="Testing",
        summary="-",
        duration="1 month",
        eligibility="-",
        fees=30000,
        certification="-",
        placement_assistance="-",
        trainer_name="-",
    )
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"N019-Batch-{tag}", start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 2, 1), schedule="-", status="active")
    db.add(batch)
    await db.flush()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N019-{tag}", status="active")
    db.add(enrollment)
    await db.commit()
    return enrollment


async def _student(db) -> User:
    student = await make_user(db, "it_student", "it", name="Asha Learner")
    student.student_code = uuid.uuid4().hex[:8].upper()
    student.phone = "+91 90000 11111"
    await db.commit()
    return student


async def _discount(client, payment_id, amount, reason="Scholarship for merit."):
    return await client.post(f"{API}/admin/payments/{payment_id}/discount", json={"amount": amount, "reason": reason})


def _rows(receipt: Receipt) -> dict[str, str]:
    return receipt_rows(storage.read_bytes(f"receipts/{receipt.receipt_no}.pdf"))


# --- AC2: the discount ledger ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_discount_keeps_the_gross_amount_and_records_reason_and_admin(client, db_session):
    student = await _student(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    payment = Payment(user_id=student.id, division="it", reference_type="service_fee", amount=10000, status="pending")
    db_session.add(payment)
    await db_session.commit()
    await login(client, admin)

    response = await _discount(client, payment.id, 8000)
    assert response.status_code == 200
    assert response.json() == {"id": str(payment.id), "amount": 8000.0, "status": "pending", "gross_amount": 10000.0, "discount_amount": 2000.0}
    # a second discount is cumulative; the reason and the admin are the latest ones
    response = await _discount(client, payment.id, 7500, reason="Early-payment offer.")
    assert response.json()["gross_amount"] == 10000.0 and response.json()["discount_amount"] == 2500.0

    await db_session.refresh(payment)
    assert float(payment.amount) == 7500  # AC4: amount stays the net payable
    assert float(payment.discount_amount) == 2500 and payment.gross_amount == 10000
    assert payment.discount_reason == "Early-payment offer." and payment.discounted_by_id == admin.id


@pytest.mark.asyncio
async def test_a_discount_reason_longer_than_500_characters_is_refused(client, db_session):
    student = await _student(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    payment = Payment(user_id=student.id, division="it", reference_type="service_fee", amount=10000, status="pending")
    db_session.add(payment)
    await db_session.commit()
    await login(client, admin)

    assert (await _discount(client, payment.id, 9000, reason="x" * 501)).status_code == 422
    await db_session.refresh(payment)
    assert float(payment.amount) == 10000 and float(payment.discount_amount) == 0


# --- paid_at ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_paid_and_admin_recorded_paid_payments_carry_paid_at(client, db_session):
    student = await _student(db_session)
    payment = Payment(user_id=student.id, division="it", reference_type="service_fee", amount=500, status="pending")
    db_session.add(payment)
    await db_session.commit()
    await _mark_paid(db_session, payment, student, source="verify")
    await db_session.commit()
    assert payment.paid_at is not None

    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    response = await client.post(f"{API}/admin/payments", json={"user_id": str(student.id), "amount": 700, "status": "paid"})
    created = await db_session.get(Payment, uuid.UUID(response.json()["id"]))
    await db_session.refresh(created)
    assert created.paid_at is not None
    pending = await client.post(f"{API}/admin/payments", json={"user_id": str(student.id), "amount": 700})
    assert (await db_session.get(Payment, uuid.UUID(pending.json()["id"]))).paid_at is None


# --- AC1 / AC3: the receipt -------------------------------------------------------------------------------------------------------


def test_receipt_lines_show_every_field_and_a_dash_for_unknown_values():
    lines = dict(
        receipt_lines(
            receipt_no="RCPT-1",
            payment_date=datetime.date(2026, 10, 28),
            payer_name="Asha",
            student_name="Asha",
            student_code="AB12CD34",
            email="asha@example.local",
            phone=None,
            course="Data Science",
            batch=None,
            reference_type="enrollment_fee",
            currency="INR",
            gross=30000,
            discount=3000,
            paid=13500,
            balance=13500,
            status="Partially paid",
        )
    )
    assert lines == {
        "Receipt No": "RCPT-1",
        "Payment date": "2026-10-28",
        "Billed to": "Asha",
        "Student": "Asha",
        "Student code": "AB12CD34",
        "Email": "asha@example.local",
        "Phone": "—",
        "Course": "Data Science",
        "Batch": "—",
        "Reference": "enrollment_fee",
        "Gross amount": "INR 30,000.00",
        "Discount": "INR 3,000.00",
        "Amount paid": "INR 13,500.00",
        "Remaining balance": "INR 13,500.00",
        "Payment status": "Partially paid",
    }
    bare = dict(receipt_lines(receipt_no="RCPT-2", payment_date=None, payer_name="B", currency="INR", gross=100, discount=0, paid=100, balance=0, status="Paid"))
    assert bare["Payment date"] == bare["Course"] == bare["Student code"] == bare["Discount"] == "—"
    assert bare["Remaining balance"] == "INR 0.00" and bare["Payment status"] == "Paid"


@pytest.mark.asyncio
async def test_a_discounted_partially_paid_emi_enrolment_receipt_shows_every_field(client, db_session):
    """AC1: gross, discount, amount paid, remaining balance, "Partially paid", course, batch, student code, email and payment date."""
    student = await _student(db_session)
    enrollment = await _enrolment(db_session, student)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    plan = await client.post(
        f"{API}/admin/payments/emi-schedule",
        json={
            "user_id": str(student.id),
            "reference_type": "enrollment_fee",
            "reference_id": str(enrollment.id),
            "installments": [{"amount": 15000, "due_date": "2026-11-01"}, {"amount": 15000, "due_date": "2026-12-01"}],
        },
    )
    assert plan.status_code == 201
    first_id = plan.json()["installments"][0]["id"]
    assert (await _discount(client, first_id, 12000)).status_code == 200

    first = await db_session.get(Payment, uuid.UUID(first_id))
    await db_session.refresh(first)
    await _mark_paid(db_session, first, student, source="verify")
    await db_session.commit()

    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == first.id))
    batch = await db_session.get(Batch, enrollment.batch_id)
    program = await db_session.get(Program, batch.program_id)
    assert _rows(receipt) == {
        "Receipt No": receipt.receipt_no,
        "Payment date": first.paid_at.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat(),
        "Billed to": "Asha Learner",
        "Student": "Asha Learner",
        "Student code": student.student_code,
        "Email": student.email,
        "Phone": "+91 90000 11111",
        "Course": program.title,
        "Batch": batch.name,
        "Reference": "enrollment_fee",
        "Gross amount": "INR 15,000.00",
        "Discount": "INR 3,000.00",
        "Amount paid": "INR 12,000.00",
        "Remaining balance": "INR 15,000.00",  # the unpaid second instalment
        "Payment status": "Partially paid",
    }


@pytest.mark.asyncio
async def test_a_plain_payment_without_enrolment_or_code_renders_with_dashes(db_session):
    """AC3: nothing known beyond the payment -- the receipt still renders, status Paid, balance 0, dashes for the rest."""
    student = await make_user(db_session, "overseas_student", "overseas")
    payment = Payment(user_id=student.id, division="overseas", reference_type="service_fee", amount=2500, status="pending")
    db_session.add(payment)
    await db_session.commit()
    await _mark_paid(db_session, payment, student, source="verify")
    await db_session.commit()
    rows = _rows(await db_session.scalar(select(Receipt).where(Receipt.payment_id == payment.id)))
    assert (rows["Payment status"], rows["Remaining balance"], rows["Amount paid"], rows["Gross amount"]) == ("Paid", "INR 0.00", "INR 2,500.00", "INR 2,500.00")
    assert rows["Student code"] == rows["Phone"] == rows["Course"] == rows["Batch"] == rows["Discount"] == "—"


# --- additive API fields --------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payment_responses_carry_the_ledger_fields(client, db_session):
    student = await _student(db_session)
    enrollment = await _enrolment(db_session, student)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    plan = await client.post(
        f"{API}/admin/payments/emi-schedule",
        json={"user_id": str(student.id), "reference_type": "enrollment_fee", "reference_id": str(enrollment.id), "installments": [{"amount": 10000}, {"amount": 10000}]},
    )
    first_id = plan.json()["installments"][0]["id"]
    await _discount(client, first_id, 9000, reason="Internal: sibling discount.")
    rows = {r["id"]: r for r in (await client.get(f"{API}/admin/payments")).json()}
    assert (rows[first_id]["gross_amount"], rows[first_id]["discount_amount"], rows[first_id]["discount_reason"], rows[first_id]["paid_at"]) == (10000.0, 1000.0, "Internal: sibling discount.", None)

    first = await db_session.get(Payment, uuid.UUID(first_id))
    await _mark_paid(db_session, first, student, source="verify")
    await db_session.commit()

    await login(client, student)
    mine = {r["id"]: r for r in (await client.get(f"{API}/payments/mine")).json()}
    assert (mine[first_id]["amount"], mine[first_id]["gross_amount"], mine[first_id]["discount_amount"]) == (9000.0, 10000.0, 1000.0)
    assert mine[first_id]["paid_at"] is not None and "discount_reason" not in mine[first_id]  # D11: the reason is internal
    (schedule,) = (await client.get(f"{API}/payments/emi-schedule")).json()
    assert (schedule["paid_amount"], schedule["balance"]) == (9000.0, 10000.0)
    assert schedule["installments"][0]["discount_amount"] == 1000.0 and schedule["installments"][0]["paid_at"] is not None
