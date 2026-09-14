"""PAY-001/STU-010 -- Payment gateway integration, fee payment/EMI/invoices/receipts.

Exercised against the real Razorpay TEST-mode credentials now present in `.env`
(`rzp_test_...`) -- both a real order-creation call to Razorpay's own API and a real HMAC
webhook-signature computation against the real `RAZORPAY_WEBHOOK_SECRET`, closing the
"test gate requires real webhook signature verification" blocker pending.md tracked.
`Invoice`/`Receipt`/`EMISchedule`/`PaymentWebhookEvent` are net-new (DATA_MODEL.md #7.2 --
mislabeled "carries over" there; none of these existed in code before this feature).
"""

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.models import Invoice, Payment, PaymentWebhookEvent, Receipt, User


async def _create_user(db_session, *, role: str = "it_student", division: str = "it") -> User:
    user = User(
        email=f"pay001-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Payment Tester",
        role=role,
        division=division,
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, division: str = "it") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


def _razorpay_signature(raw_body: bytes) -> str:
    assert settings.razorpay_webhook_secret, "RAZORPAY_WEBHOOK_SECRET must be set for this test"
    return hmac.new(settings.razorpay_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_checkout_requires_idempotency_key(db_session, client):
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    response = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_checkout_creates_a_real_razorpay_order_and_an_invoice(db_session, client):
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1500, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    response = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["provider_order_id"].startswith("order_")

    invoice_response = await client.get(f"/api/v1/payments/{payment.id}/invoice")
    assert invoice_response.status_code == 200
    assert invoice_response.json()["url"]

    await db_session.refresh(payment)
    assert payment.checkout_provider_order_id == body["provider_order_id"]


@pytest.mark.asyncio
async def test_checkout_replays_on_the_same_idempotency_key_without_creating_a_second_order(db_session, client):
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=2000, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)
    key = uuid.uuid4().hex

    first = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": key})
    second = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": key})
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["replayed"] is True
    assert first.json()["provider_order_id"] == second.json()["provider_order_id"]


@pytest.mark.asyncio
async def test_checkout_rejects_a_payment_belonging_to_another_user(db_session, client):
    owner = await _create_user(db_session)
    other = await _create_user(db_session)
    payment = Payment(user_id=owner.id, division="it", reference_type="course_fee", amount=1000, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, other.email)

    response = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_checkout_is_self_only_even_for_admin_roles(db_session, client):
    # STU-010-AC04/RBAC_MATRIX.md #2.9: Admin's scope over payments is view (read-only) --
    # a pre-existing gap let any admin role trigger checkout on another user's payment.
    owner = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    payment = Payment(user_id=owner.id, division="it", reference_type="course_fee", amount=1000, currency="INR")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/payments/{payment.id}/checkout", json={"provider": "razorpay"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_endpoint_requires_no_session_it_is_a_system_endpoint(client):
    # Audit item from CLAUDE.md's Testing section: a webhook must never require the
    # session-cookie authentication a human-facing endpoint uses -- it authenticates via
    # HMAC signature instead. This call carries no login/cookie at all.
    raw = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    response = await client.post(
        "/api/v1/payments/webhooks/razorpay",
        content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": "bad", "x-razorpay-event-id": uuid.uuid4().hex},
    )
    # Rejected for a bad *signature*, not for missing session auth -- proves the endpoint
    # never depends on `get_current_user` despite returning the same 401 status code.
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Razorpay signature"


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature_and_logs_it_without_touching_the_payment(db_session, client):
    # RAID.md I-06/I-09: this shared dev DB has no test-DB isolation, so a hardcoded
    # order id can collide with a leftover row from an earlier run of this same test --
    # uuid-suffixed here like every other identifying value this session's tests use.
    order_id = f"order_fake_{uuid.uuid4().hex}"
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()

    raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_fake", "order_id": order_id}}}}).encode()
    event_id = uuid.uuid4().hex
    response = await client.post(
        "/api/v1/payments/webhooks/razorpay",
        content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": "not-a-real-signature", "x-razorpay-event-id": event_id},
    )
    assert response.status_code == 401

    event_row = await db_session.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id))
    assert event_row is not None
    assert event_row.signature_verified is False
    assert event_row.payment_id is None

    await db_session.refresh(payment)
    assert payment.status == "pending"


@pytest.mark.asyncio
async def test_webhook_requires_the_event_id_header(client):
    raw = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    response = await client.post(
        "/api/v1/payments/webhooks/razorpay",
        content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": _razorpay_signature(raw)},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_with_a_real_valid_signature_marks_the_payment_paid_and_generates_a_receipt(db_session, client):
    order_id = f"order_realmatch_{uuid.uuid4().hex}"
    payment_ref = f"pay_realmatch_{uuid.uuid4().hex}"
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()

    raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": payment_ref, "order_id": order_id, "status": "captured"}}}}).encode()
    event_id = uuid.uuid4().hex
    response = await client.post(
        "/api/v1/payments/webhooks/razorpay",
        content=raw,
        headers={"content-type": "application/json", "x-razorpay-signature": _razorpay_signature(raw), "x-razorpay-event-id": event_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"received": True, "matched": True, "status": "paid"}

    await db_session.refresh(payment)
    assert payment.status == "paid"
    assert payment.provider_reference == payment_ref

    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == payment.id))
    assert receipt is not None


@pytest.mark.asyncio
async def test_webhook_duplicate_delivery_of_the_same_event_id_is_not_reprocessed(db_session, client):
    order_id = f"order_dup_{uuid.uuid4().hex}"
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()

    raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_dup", "order_id": order_id, "status": "captured"}}}}).encode()
    event_id = uuid.uuid4().hex
    headers = {"content-type": "application/json", "x-razorpay-signature": _razorpay_signature(raw), "x-razorpay-event-id": event_id}

    first = await client.post("/api/v1/payments/webhooks/razorpay", content=raw, headers=headers)
    second = await client.post("/api/v1/payments/webhooks/razorpay", content=raw, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["status"] == "already_processed"

    events = (await db_session.scalars(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id))).all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_admin_manual_payment_marked_paid_at_creation_gets_both_invoice_and_receipt(db_session, client):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    await _login(client, admin.email)

    response = await client.post(
        "/api/v1/admin/payments",
        json={"user_id": str(student.id), "reference_type": "service_fee", "amount": 500, "currency": "INR", "provider": "manual", "status": "paid"},
    )
    assert response.status_code == 201
    payment_id = response.json()["id"]

    invoice = await db_session.scalar(select(Invoice).where(Invoice.payment_id == uuid.UUID(payment_id)))
    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == uuid.UUID(payment_id)))
    assert invoice is not None
    assert receipt is not None


@pytest.mark.asyncio
async def test_admin_can_create_an_emi_schedule_and_the_student_can_list_it(db_session, client):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    await _login(client, admin.email)

    response = await client.post(
        "/api/v1/admin/payments/emi-schedule",
        json={
            "user_id": str(student.id),
            "reference_type": "course_fee",
            "currency": "INR",
            "installments": [
                {"amount": 1000, "due_date": "2026-10-01"},
                {"amount": 1000, "due_date": "2026-11-01"},
                {"amount": 1000, "due_date": "2026-12-01"},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["installment_count"] == 3
    assert len(body["installments"]) == 3

    await _login(client, student.email)
    listing = await client.get("/api/v1/payments/emi-schedule")
    assert listing.status_code == 200
    schedules = listing.json()
    assert len(schedules) == 1
    assert schedules[0]["installment_count"] == 3
    assert [i["installment_no"] for i in schedules[0]["installments"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_emi_schedule_requires_at_least_one_installment(db_session, client):
    student = await _create_user(db_session)
    admin = await _create_user(db_session, role="it_admin")
    await _login(client, admin.email)

    response = await client.post("/api/v1/admin/payments/emi-schedule", json={"user_id": str(student.id), "installments": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invoice_and_receipt_download_require_ownership(db_session, client):
    owner = await _create_user(db_session)
    other = await _create_user(db_session)
    payment = Payment(user_id=owner.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="paid")
    db_session.add(payment)
    await db_session.flush()
    db_session.add(Invoice(payment_id=payment.id, user_id=owner.id, division="it", invoice_no=f"INV-TEST-{uuid.uuid4().hex[:8]}", amount=1000, currency="INR", file_url="/local-files/invoices/x.pdf"))
    await db_session.commit()
    await _login(client, other.email)

    response = await client.get(f"/api/v1/payments/{payment.id}/invoice")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_receipt_download_404s_before_payment_completes(db_session, client):
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    response = await client.get(f"/api/v1/payments/{payment.id}/receipt")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_payments_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/payments/mine")).status_code == 401
    assert (await client.get("/api/v1/payments/emi-schedule")).status_code == 401
    assert (await client.post(f"/api/v1/payments/{uuid.uuid4()}/checkout", json={})).status_code == 401


def _razorpay_payment_signature(order_id: str, payment_id: str) -> str:
    assert settings.razorpay_key_secret, "RAZORPAY_KEY_SECRET must be set for this test"
    return hmac.new(settings.razorpay_key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_verify_with_a_valid_signature_marks_the_payment_paid_and_generates_a_receipt(db_session, client):
    """The client-side confirmation gap found live: a successful test payment left
    'Pay Now' showing forever with no receipt, because only the webhook (which can
    never reach a local dev server) ever marked a payment paid."""
    order_id = f"order_verify_{uuid.uuid4().hex}"
    razorpay_payment_id = f"pay_verify_{uuid.uuid4().hex}"
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    signature = _razorpay_payment_signature(order_id, razorpay_payment_id)
    response = await client.post(
        f"/api/v1/payments/{payment.id}/verify",
        json={"razorpay_payment_id": razorpay_payment_id, "razorpay_order_id": order_id, "razorpay_signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paid"

    await db_session.refresh(payment)
    assert payment.status == "paid"
    assert payment.provider_reference == razorpay_payment_id

    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == payment.id))
    assert receipt is not None


@pytest.mark.asyncio
async def test_verify_rejects_an_invalid_signature_and_never_marks_the_payment_paid(db_session, client):
    order_id = f"order_bad_{uuid.uuid4().hex}"
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    response = await client.post(
        f"/api/v1/payments/{payment.id}/verify",
        json={"razorpay_payment_id": "pay_bad", "razorpay_order_id": order_id, "razorpay_signature": "not-a-real-signature"},
    )
    assert response.status_code == 400

    await db_session.refresh(payment)
    assert payment.status == "pending"


@pytest.mark.asyncio
async def test_verify_rejects_an_order_id_that_does_not_match_this_payments_own_checkout_session(db_session, client):
    user = await _create_user(db_session)
    payment = Payment(user_id=user.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=f"order_real_{uuid.uuid4().hex}")
    db_session.add(payment)
    await db_session.commit()
    await _login(client, user.email)

    other_order_id = f"order_swapped_{uuid.uuid4().hex}"
    signature = _razorpay_payment_signature(other_order_id, "pay_swapped")
    response = await client.post(
        f"/api/v1/payments/{payment.id}/verify",
        json={"razorpay_payment_id": "pay_swapped", "razorpay_order_id": other_order_id, "razorpay_signature": signature},
    )
    assert response.status_code == 409

    await db_session.refresh(payment)
    assert payment.status == "pending"


@pytest.mark.asyncio
async def test_verify_rejects_someone_elses_payment(db_session, client):
    owner = await _create_user(db_session)
    other = await _create_user(db_session)
    order_id = f"order_other_{uuid.uuid4().hex}"
    payment = Payment(user_id=owner.id, division="it", reference_type="course_fee", amount=1000, currency="INR", status="pending", checkout_provider_order_id=order_id)
    db_session.add(payment)
    await db_session.commit()
    await _login(client, other.email)

    signature = _razorpay_payment_signature(order_id, "pay_other")
    response = await client.post(
        f"/api/v1/payments/{payment.id}/verify",
        json={"razorpay_payment_id": "pay_other", "razorpay_order_id": order_id, "razorpay_signature": signature},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_verify_requires_authentication(client):
    response = await client.post(f"/api/v1/payments/{uuid.uuid4()}/verify", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_from_a_different_division_cannot_create_a_payment_for_another_divisions_student(db_session, client):
    student = await _create_user(db_session, division="overseas", role="overseas_student")
    admin = await _create_user(db_session, role="it_admin", division="it")
    await _login(client, admin.email, division="it")

    response = await client.post("/api/v1/admin/payments", json={"user_id": str(student.id), "amount": 500})
    assert response.status_code == 403
