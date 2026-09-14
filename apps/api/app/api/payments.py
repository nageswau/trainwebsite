import hashlib
import hmac
import json
import secrets
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import AuditLog, EMISchedule, Invoice, Payment, PaymentWebhookEvent, Receipt, User
from app.services.billing_documents import generate_invoice_pdf, generate_receipt_pdf
from app.services.payment import payments
from app.services.storage import storage

router = APIRouter(prefix="/payments", tags=["payments"])

ADMIN_ROLES = {"super_admin", "it_admin", "overseas_admin"}


async def _ensure_invoice(db: AsyncSession, item: Payment, payer: User) -> Invoice:
    """PRD-PAY-003: an invoice is generated once a Payment (a bill) exists, whatever created
    it (admin-recorded or gateway checkout) -- idempotent, never duplicated for the same Payment.
    """
    existing = await db.scalar(select(Invoice).where(Invoice.payment_id == item.id))
    if existing:
        return existing
    invoice_no = f"INV-{date.today():%Y}-{secrets.token_hex(4).upper()}"
    file_url = generate_invoice_pdf(invoice_no=invoice_no, payer_name=payer.full_name, amount=float(item.amount), currency=item.currency, issued_on=date.today(), reference_type=item.reference_type)
    invoice = Invoice(payment_id=item.id, user_id=item.user_id, division=item.division, invoice_no=invoice_no, amount=item.amount, currency=item.currency, file_url=file_url)
    db.add(invoice)
    await db.flush()
    return invoice


async def _ensure_receipt(db: AsyncSession, item: Payment, payer: User) -> Receipt:
    """PRD-PAY-003: a receipt is generated once a Payment reaches paid/succeeded -- idempotent,
    never duplicated for the same Payment.
    """
    existing = await db.scalar(select(Receipt).where(Receipt.payment_id == item.id))
    if existing:
        return existing
    receipt_no = f"RCPT-{date.today():%Y}-{secrets.token_hex(4).upper()}"
    file_url = generate_receipt_pdf(receipt_no=receipt_no, payer_name=payer.full_name, amount=float(item.amount), currency=item.currency, issued_on=date.today(), reference_type=item.reference_type)
    receipt = Receipt(payment_id=item.id, user_id=item.user_id, division=item.division, receipt_no=receipt_no, amount=item.amount, currency=item.currency, file_url=file_url)
    db.add(receipt)
    await db.flush()
    return receipt


@router.get("/mine")
async def mine(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()))).all()
    return [
        {
            "id": x.id,
            "division": x.division,
            "amount": float(x.amount),
            "currency": x.currency,
            "provider": x.provider,
            "status": x.status,
            "due_date": x.due_date,
            "reference_type": x.reference_type,
            "is_manual": x.is_manual,
            "emi_schedule_id": x.emi_schedule_id,
            "installment_no": x.installment_no,
        }
        for x in rows
    ]


@router.get("/emi-schedule")
async def emi_schedule(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """API_CONTRACT.md STU-010 row: `GET /student/payments/emi-schedule` -- implemented on the
    existing dedicated `/payments` router rather than a separate `/student/*` route, same
    "correct the doc to match the inherited router" pattern applied to STU-005.
    """
    schedules = (await db.scalars(select(EMISchedule).where(EMISchedule.user_id == user.id).order_by(EMISchedule.created_at.desc()))).all()
    if not schedules:
        return []
    installments = (await db.scalars(select(Payment).where(Payment.emi_schedule_id.in_([s.id for s in schedules])).order_by(Payment.installment_no))).all()
    by_schedule: dict[UUID, list[Payment]] = {}
    for p in installments:
        by_schedule.setdefault(p.emi_schedule_id, []).append(p)
    return [
        {
            "id": s.id,
            "division": s.division,
            "reference_type": s.reference_type,
            "total_amount": float(s.total_amount),
            "currency": s.currency,
            "installment_count": s.installment_count,
            "installments": [
                {"id": p.id, "installment_no": p.installment_no, "amount": float(p.amount), "due_date": p.due_date, "status": p.status}
                for p in by_schedule.get(s.id, [])
            ],
        }
        for s in schedules
    ]


@router.get("/{payment_id}/invoice")
async def download_invoice(payment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Signed download URL, same pattern as STU-007's certificate download -- never a public
    object link, only an id-for-URL exchange verified here.
    """
    item = await db.get(Payment, payment_id)
    if not item:
        raise HTTPException(404, "Payment not found")
    if item.user_id != user.id and not (user.role in ADMIN_ROLES and (user.role == "super_admin" or item.division == user.division)):
        raise HTTPException(403, "Payment belongs to another user")
    invoice = await db.scalar(select(Invoice).where(Invoice.payment_id == item.id))
    if not invoice:
        raise HTTPException(404, "Invoice not yet generated for this payment")
    key = f"invoices/{invoice.invoice_no}.pdf"
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


@router.get("/{payment_id}/receipt")
async def download_receipt(payment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Payment, payment_id)
    if not item:
        raise HTTPException(404, "Payment not found")
    if item.user_id != user.id and not (user.role in ADMIN_ROLES and (user.role == "super_admin" or item.division == user.division)):
        raise HTTPException(403, "Payment belongs to another user")
    receipt = await db.scalar(select(Receipt).where(Receipt.payment_id == item.id))
    if not receipt:
        raise HTTPException(404, "Receipt not yet available -- payment has not completed")
    key = f"receipts/{receipt.receipt_no}.pdf"
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}


@router.post("/{payment_id}/checkout")
async def checkout(
    payment_id: UUID,
    payload: dict,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # API_CONTRACT.md #0.2: checkout-session creation is idempotency-key gated -- a client
    # retry with the same key replays the original result rather than creating a second
    # provider order (INTEGRATION_CONTRACTS.md #2's synchronous-no-retry rule).
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    item = await db.get(Payment, payment_id)
    if not item:
        raise HTTPException(404, "Payment not found")
    if item.user_id != user.id:
        # RBAC_MATRIX.md #2.9/STU-010-AC04: Admin's scope over payments is "view (read-only)"
        # -- initiating a checkout is a Self-only action, not an Admin one. A pre-existing gap
        # (found while adding the idempotency-key gate) let any admin role trigger checkout on
        # another user's payment; fixed here rather than carried forward.
        raise HTTPException(403, "Payment belongs to another user")
    if item.checkout_idempotency_key == idempotency_key and item.checkout_provider_order_id:
        return {"status": "ready", "provider": item.provider, "amount": float(item.amount), "currency": item.currency, "reference": f"PAY-{item.id}", "provider_order_id": item.checkout_provider_order_id, "replayed": True}
    provider = payload.get("provider", "razorpay")
    if provider not in {"razorpay", "manual"}:
        raise HTTPException(422, "Unsupported payment provider")
    result = await payments.create_checkout(provider, float(item.amount), item.currency, f"PAY-{item.id}")
    item.provider = provider
    item.checkout_idempotency_key = idempotency_key
    item.checkout_provider_order_id = result.get("provider_order_id")
    await _ensure_invoice(db, item, user)
    db.add(AuditLog(user_id=user.id, action="payment.checkout", entity_type="payment", entity_id=str(item.id), metadata_json={"provider": provider, "checkout_status": result["status"]}))
    await db.commit()
    return result


@router.post("/{payment_id}/verify")
async def verify_checkout(payment_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Razorpay's own documented client-side confirmation step (separate from, and a
    backstop-independent complement to, the webhook above): their Checkout.js
    `handler` callback receives `razorpay_payment_id`/`razorpay_order_id`/
    `razorpay_signature` the instant a payment succeeds in the browser, signed with
    `order_id|payment_id` under the account's key secret. In a real deployment the
    webhook (above) eventually arrives too and is the durable source of truth; in a
    local/dev environment Razorpay's servers can never reach `localhost` at all, so
    without this endpoint a successful test payment had no way to ever actually mark
    itself paid -- "Pay Now" stayed forever, with no receipt, exactly the gap reported
    directly against the running app.
    """
    razorpay_payment_id = str(payload.get("razorpay_payment_id") or "")
    razorpay_order_id = str(payload.get("razorpay_order_id") or "")
    razorpay_signature = str(payload.get("razorpay_signature") or "")
    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        raise HTTPException(422, "razorpay_payment_id, razorpay_order_id, and razorpay_signature are required")
    item = await db.get(Payment, payment_id)
    if not item:
        raise HTTPException(404, "Payment not found")
    if item.user_id != user.id:
        raise HTTPException(403, "Payment belongs to another user")
    if item.checkout_provider_order_id != razorpay_order_id:
        raise HTTPException(409, "This order id does not match the checkout session created for this payment")
    if not settings.razorpay_key_secret:
        raise HTTPException(503, "Razorpay is not configured")
    expected = hmac.new(settings.razorpay_key_secret.encode(), f"{razorpay_order_id}|{razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, razorpay_signature):
        raise HTTPException(400, "Invalid payment signature")
    if item.status not in {"paid", "succeeded"}:
        item.status = "paid"
        item.provider_reference = razorpay_payment_id
        await _ensure_receipt(db, item, user)
        db.add(AuditLog(user_id=user.id, action="payment.verify", entity_type="payment", entity_id=str(item.id), metadata_json={"razorpay_payment_id": razorpay_payment_id}))
        await db.commit()
        await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    if provider != "razorpay":
        raise HTTPException(404, "Unsupported webhook provider")

    signature = request.headers.get("x-razorpay-signature")
    # Razorpay puts its delivery-dedup id in this header, not the JSON body (confirmed against
    # Razorpay's own webhook docs) -- INTEGRATION_CONTRACTS.md #2/#6's "idempotent on
    # event_id/equivalent" rule is keyed on it.
    event_id = request.headers.get("x-razorpay-event-id")
    if not settings.razorpay_webhook_secret:
        raise HTTPException(503, "Razorpay webhook secret is not configured")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    signature_verified = bool(signature) and hmac.compare_digest(expected, signature)

    if not event_id:
        # Can't guarantee the idempotency contract without a dedup key -- logged, not processed.
        raise HTTPException(400, "Missing x-razorpay-event-id header")

    existing_event = await db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id))
    if existing_event and existing_event.processed_at:
        # PAY-001-AC03 / INTEGRATION_CONTRACTS #2: a retried delivery is acknowledged once,
        # never reprocessed.
        return {"received": True, "matched": bool(existing_event.payment_id), "status": "already_processed"}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}

    if not signature_verified:
        # Logged and discarded -- never touches a Payment (PAY-001-AC03).
        if not existing_event:
            db.add(PaymentWebhookEvent(provider=provider, event_id=event_id, signature_verified=False, raw_payload=payload, payment_id=None, processed_at=None))
            await db.commit()
        raise HTTPException(401, "Invalid Razorpay signature")

    payment_payload = payload.get("payload", {}) if isinstance(payload.get("payload"), dict) else {}
    payment_entity = (payment_payload.get("payment") or {}).get("entity") or {}
    order_entity = (payment_payload.get("order") or {}).get("entity") or {}
    entity = payment_entity or order_entity
    provider_reference = entity.get("id")
    status = "paid" if payload.get("event") in {"payment.captured", "order.paid"} else entity.get("status")

    # Razorpay's Payment entity carries no "receipt" field (only Order does, per Razorpay's own
    # API reference), and whether order-level "notes" cascade onto the payment isn't documented
    # either way -- so this matches on the order id we ourselves stored at checkout time
    # (`checkout_provider_order_id`) rather than trusting either undocumented behavior. The order
    # id is `entity.id` when the event's own entity IS the order (order.paid), or
    # `payment_entity.order_id` when it's the payment (payment.captured).
    order_id = order_entity.get("id") or payment_entity.get("order_id")
    item = (await db.scalars(select(Payment).where(Payment.checkout_provider_order_id == order_id))).first() if order_id else None
    if not item:
        # Fallback for a payment created without going through this app's own checkout
        # endpoint (e.g. a receipt/notes reference set by another integration path).
        receipt_note = (entity.get("notes") or {}).get("reference") or entity.get("receipt", "")
        payment_ref = receipt_note.removeprefix("PAY-") if str(receipt_note).startswith("PAY-") else None
        payment_reference = uuid_reference(payment_ref, "payment reference", required=False) if payment_ref else None
        item = await db.get(Payment, payment_reference) if payment_reference else None

    event_row = existing_event or PaymentWebhookEvent(provider=provider, event_id=event_id, signature_verified=True, raw_payload=payload)
    if not existing_event:
        db.add(event_row)

    if not item:
        event_row.processed_at = None
        await db.commit()
        return {"received": True, "matched": False}

    item.provider = provider
    item.provider_reference = str(provider_reference) if provider_reference else item.provider_reference
    item.status = status or item.status
    event_row.payment_id = item.id
    event_row.processed_at = datetime.now(UTC)
    if item.status in {"paid", "succeeded"}:
        payer = await db.get(User, item.user_id)
        if payer:
            await _ensure_receipt(db, item, payer)
    db.add(AuditLog(user_id=None, action="payment.webhook", entity_type="payment", entity_id=str(item.id), metadata_json={"provider": provider, "status": item.status, "event_id": event_id}))
    await db.commit()
    return {"received": True, "matched": True, "status": item.status}
