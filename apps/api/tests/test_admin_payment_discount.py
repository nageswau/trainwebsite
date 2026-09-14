"""Admin-applied discount on a still-unpaid fee. Same "a discretionary change is never
silent" pattern as `ADM-006`'s certificate override and `AGT-003`'s commission-amount
adjustment: only lowers an amount (never raises it -- that is `create_payment`'s own
job), requires a written reason, and only while nothing has actually been collected
yet -- a paid/succeeded payment is a completed transaction, not something this endpoint
retroactively rewrites. The invoice already generated for the bill is regenerated to
match, since it hasn't been paid yet and would otherwise show a stale amount.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Invoice, Payment, User


async def _create_user(db_session, *, role: str = "it_student", division: str = "it") -> User:
    user = User(
        email=f"discount-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Discount Tester",
        role=role,
        division=division,
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_payment(db_session, student: User, *, amount: float = 10000, status: str = "pending") -> Payment:
    payment = Payment(user_id=student.id, division="it", reference_type="enrollment_fee", amount=amount, currency="INR", status=status)
    db_session.add(payment)
    await db_session.commit()
    return payment


async def _login(client, email: str, division: str = "it") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_discounts_a_pending_payment_and_regenerates_its_invoice(client, db_session):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    payment = await _create_payment(db_session, student, amount=10000)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 7500, "reason": "Loyalty discount for a returning student."})
    assert response.status_code == 200
    assert response.json()["amount"] == 7500

    await db_session.refresh(payment)
    assert float(payment.amount) == 7500
    assert payment.status == "pending"

    invoice = await db_session.scalar(select(Invoice).where(Invoice.payment_id == payment.id))
    assert invoice is not None
    assert float(invoice.amount) == 7500


@pytest.mark.asyncio
async def test_discount_requires_a_written_reason(client, db_session):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    payment = await _create_payment(db_session, student)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 5000})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_discount_cannot_raise_the_amount(client, db_session):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    payment = await _create_payment(db_session, student, amount=10000)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 12000, "reason": "Trying to raise it."})
    assert response.status_code == 422

    await db_session.refresh(payment)
    assert float(payment.amount) == 10000


@pytest.mark.asyncio
async def test_a_paid_payment_cannot_be_discounted(client, db_session):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    payment = await _create_payment(db_session, student, amount=10000, status="paid")
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 5000, "reason": "Too late."})
    assert response.status_code == 409

    await db_session.refresh(payment)
    assert float(payment.amount) == 10000


@pytest.mark.asyncio
async def test_a_non_admin_cannot_discount_a_payment(client, db_session):
    student = await _create_user(db_session)
    payment = await _create_payment(db_session, student)
    await _login(client, student.email)

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 5000, "reason": "Self-discount attempt."})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_from_a_different_division_cannot_discount_a_payment(client, db_session):
    student = await _create_user(db_session, division="overseas", role="overseas_student")
    admin = await _create_user(db_session, role="it_admin", division="it")
    payment = await _create_payment(db_session, student)
    payment.division = "overseas"
    await db_session.commit()
    await _login(client, admin.email, division="it")

    response = await client.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 5000, "reason": "Wrong division."})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_discounting_an_unknown_payment_404s(client, db_session):
    admin = await _create_user(db_session, role="it_admin")
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/admin/payments/{uuid.uuid4()}/discount", json={"amount": 5000, "reason": "Ghost."})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_discount_requires_authentication(client):
    response = await client.post(f"/api/v1/admin/payments/{uuid.uuid4()}/discount", json={"amount": 5000, "reason": "x"})
    assert response.status_code == 401
