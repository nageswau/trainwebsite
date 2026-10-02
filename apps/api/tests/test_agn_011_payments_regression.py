"""AGN-011 -- the shared payments path (spec §4.1, §4.5, D2, D4): the paid-guard for every payment, `/payments/mine` without deposits,
the generic checkout and admin routes refusing agent-deposit payments, and the receipt's optional student line. Runs without real
Razorpay secrets (settings monkeypatched)."""

import hashlib
import hmac
import uuid
from datetime import date
from pathlib import Path

import pytest
from pdf_text import pdf_text
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Payment, Receipt
from app.services.billing_documents import generate_receipt_pdf
from tests.agn001_helpers import client_for, mk_user
from tests.agn011_helpers import KEY_SECRET, captured, deposit_world, mk_deposit, mk_deposit_payment, razorpay_on, reload, signed

WEBHOOK = "/api/v1/payments/webhooks/razorpay"


async def _fee(db, user, **fields) -> Payment:
    payment = Payment(
        user_id=user.id, division="overseas", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=f"order_{uuid.uuid4().hex[:14]}", **fields
    )
    db.add(payment)
    await db.commit()
    return payment


async def _receipts(db, payment_id) -> int:
    return await db.scalar(select(func.count()).select_from(Receipt).where(Receipt.payment_id == payment_id))


@pytest.mark.asyncio
async def test_a_late_failed_event_never_moves_a_paid_student_fee_back(db_session, client, monkeypatch):
    razorpay_on(monkeypatch)
    student = await mk_user(db_session, role="overseas_student")
    fee = await _fee(db_session, student)
    raw, headers = signed(captured(fee.checkout_provider_order_id, 100000))
    assert (await client.post(WEBHOOK, content=raw, headers=headers)).json() == {"received": True, "matched": True, "status": "paid"}
    raw, headers = signed(captured(fee.checkout_provider_order_id, 100000, event="payment.failed", status="failed"))
    late = await client.post(WEBHOOK, content=raw, headers=headers)
    assert late.status_code == 200 and late.json() == {"received": True, "matched": True, "status": "paid"}
    assert (await reload(db_session, Payment, fee.id)).status == "paid"
    assert await _receipts(db_session, fee.id) == 1


@pytest.mark.asyncio
async def test_a_failed_event_still_moves_an_unpaid_fee_as_today(db_session, client, monkeypatch):
    razorpay_on(monkeypatch)
    student = await mk_user(db_session, role="overseas_student")
    fee = await _fee(db_session, student)
    raw, headers = signed(captured(fee.checkout_provider_order_id, 100000, event="payment.failed", status="failed"))
    assert (await client.post(WEBHOOK, content=raw, headers=headers)).json()["status"] == "failed"
    assert (await reload(db_session, Payment, fee.id)).status == "failed"


@pytest.mark.asyncio
async def test_verify_on_a_paid_fee_changes_nothing(db_session, monkeypatch):
    razorpay_on(monkeypatch)
    student = await mk_user(db_session, role="overseas_student")
    fee = await _fee(db_session, student)
    signature = hmac.new(KEY_SECRET.encode(), f"{fee.checkout_provider_order_id}|pay_1".encode(), hashlib.sha256).hexdigest()
    body = {"razorpay_payment_id": "pay_1", "razorpay_order_id": fee.checkout_provider_order_id, "razorpay_signature": signature}
    async with client_for(student.email) as c:
        assert (await c.post(f"/api/v1/payments/{fee.id}/verify", json=body)).json()["status"] == "paid"
        assert (await c.post(f"/api/v1/payments/{fee.id}/verify", json=body)).json()["status"] == "paid"
    assert await _receipts(db_session, fee.id) == 1


@pytest.mark.asyncio
async def test_payments_mine_hides_deposit_payments_and_keeps_fees(db_session):
    w = await deposit_world(db_session)
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    await mk_deposit_payment(db_session, deposit, w["master"])
    fee = await _fee(db_session, w["master"])
    async with client_for(w["master"].email) as c:
        rows = (await c.get("/api/v1/payments/mine")).json()
    assert [r["id"] for r in rows] == [str(fee.id)]


@pytest.mark.asyncio
async def test_the_generic_checkout_refuses_a_deposit_payment(db_session):
    w = await deposit_world(db_session)
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    payment = await mk_deposit_payment(db_session, deposit, w["master"], order_id=None)
    async with client_for(w["master"].email) as c:
        r = await c.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["detail"] == "Pay this deposit from its application"


@pytest.mark.asyncio
async def test_admin_cannot_create_or_discount_a_deposit_payment(db_session):
    w = await deposit_world(db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    payment = await mk_deposit_payment(db_session, deposit, w["master"])
    async with client_for(admin.email) as c:
        created = await c.post("/api/v1/admin/payments", json={"user_id": str(w["master"].id), "amount": 10, "reference_type": "agent_deposit"})
        discounted = await c.post(f"/api/v1/admin/payments/{payment.id}/discount", json={"amount": 1, "reason": "goodwill"})
    assert created.status_code == 422 and created.json()["detail"] == "Agent deposits are created from the application"
    assert discounted.status_code == 409 and discounted.json()["detail"] == "An agent deposit's amount is set on its application"
    assert (await reload(db_session, Payment, payment.id)).amount == deposit.amount


def _pdf(url: str) -> str:
    return pdf_text((Path(settings.local_upload_dir) / url.removeprefix("/local-files/")).read_bytes())


def test_receipt_draws_the_student_only_when_given():
    common = {"payer_name": "Asha Master", "amount": 50000.0, "currency": "INR", "issued_on": date(2026, 10, 2), "reference_type": "agent_deposit"}
    with_student = _pdf(generate_receipt_pdf(receipt_no=f"RCPT-T-{uuid.uuid4().hex[:6]}", student_name="Ravi <b>Kumar</b>", **common))
    assert "Billed to: Asha Master" in with_student and "Student: Ravi <b>Kumar</b>" in with_student
    assert "Student:" not in _pdf(generate_receipt_pdf(receipt_no=f"RCPT-T-{uuid.uuid4().hex[:6]}", **common))
