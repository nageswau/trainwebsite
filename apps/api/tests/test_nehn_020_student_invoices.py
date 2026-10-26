"""nehn-020 (DEC-SCOPE-289): students get the receipt, not an invoice. The invoice route answers 404 to a student caller; admins keep
historical invoices; generation is unchanged until OD-11 (I4)."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Invoice, Payment, User


async def _user(db_session, role: str, division: str) -> User:
    user = User(email=f"nehn020-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Invoice Tester", role=role, division=division, active=True)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "Sup3r-Secret-Pass!", "division": user.division})
    assert response.status_code == 200


async def _paid_with_invoice(db_session, owner: User) -> Payment:
    payment = Payment(user_id=owner.id, division=owner.division, reference_type="course_fee", amount=1000, currency="INR", status="paid")
    db_session.add(payment)
    await db_session.flush()
    db_session.add(
        Invoice(payment_id=payment.id, user_id=owner.id, division=owner.division, invoice_no=f"INV-N020-{uuid.uuid4().hex[:8]}", amount=1000, currency="INR", file_url="/local-files/invoices/x.pdf")
    )
    await db_session.commit()
    return payment


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("overseas_student", "overseas")])
async def test_a_student_gets_no_invoice_for_their_own_payment(db_session, client, role, division):
    student = await _user(db_session, role, division)
    payment = await _paid_with_invoice(db_session, student)
    await _login(client, student)

    response = await client.get(f"/api/v1/payments/{payment.id}/invoice")
    assert response.status_code == 404
    assert response.json()["detail"] == "Invoices are not issued to students. Download your receipt instead."


@pytest.mark.asyncio
async def test_another_students_payment_is_still_403(db_session, client):
    owner = await _user(db_session, "it_student", "it")
    other = await _user(db_session, "it_student", "it")
    payment = await _paid_with_invoice(db_session, owner)
    await _login(client, other)

    assert (await client.get(f"/api/v1/payments/{payment.id}/invoice")).status_code == 403


@pytest.mark.asyncio
async def test_an_admin_still_downloads_a_historical_invoice(db_session, client):
    student = await _user(db_session, "it_student", "it")
    admin = await _user(db_session, "it_admin", "it")
    payment = await _paid_with_invoice(db_session, student)
    await _login(client, admin)

    response = await client.get(f"/api/v1/payments/{payment.id}/invoice")
    assert response.status_code == 200
    assert response.json()["url"]


@pytest.mark.asyncio
async def test_checkout_still_generates_the_invoice_row(db_session, client):
    student = await _user(db_session, "it_student", "it")
    payment = Payment(user_id=student.id, division="it", reference_type="course_fee", amount=1500, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, student)

    response = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 200
    assert await db_session.scalar(select(Invoice.id).where(Invoice.payment_id == payment.id))
