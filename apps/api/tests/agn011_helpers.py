"""AGN-011 test helpers: an agency world with an application, deposits and deposit payments built directly, Razorpay settings switched
on or off, and a signed webhook sender. No test calls Razorpay: `create_checkout` is monkeypatched where an order is needed."""

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import settings
from app.models import ApplicationDeposit, AuditLog, Payment
from tests.agn008_helpers import APPS, agency_world, mk_application

WEBHOOK_SECRET = "agn011-webhook-secret"
KEY_ID = "rzp_test_agn011"
KEY_SECRET = "agn011-key-secret"


def deposit_url(app_id) -> str:
    return f"{APPS}/{app_id}/deposit"


def checkout_url(app_id) -> str:
    return f"{APPS}/{app_id}/deposit/checkout"


def razorpay_on(monkeypatch) -> None:
    monkeypatch.setattr(settings, "razorpay_key_id", KEY_ID)
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)


def razorpay_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "razorpay_key_id", None)
    monkeypatch.setattr(settings, "razorpay_key_secret", None)


def fake_orders(monkeypatch) -> list[dict]:
    """Replace the Razorpay order call; returns the list of calls (amount, currency, reference)."""
    from app.services.payment import payments

    calls: list[dict] = []

    async def create_checkout(provider, amount, currency, reference):
        calls.append({"provider": provider, "amount": amount, "currency": currency, "reference": reference})
        return {"status": "ready", "provider": provider, "amount": amount, "currency": currency, "reference": reference, "key_id": KEY_ID, "provider_order_id": f"order_{uuid.uuid4().hex[:14]}"}

    monkeypatch.setattr(payments, "create_checkout", create_checkout)
    return calls


async def deposit_world(db, *, status: str = "university_selection") -> dict:
    w = await agency_world(db)
    app = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    return w | {"app": app}


async def mk_deposit(db, app, *, by, amount: str | None = "50000.00", status: str = "pending", **fields) -> ApplicationDeposit:
    deposit = ApplicationDeposit(
        application_id=app.id,
        required=status != "not_required",
        amount=Decimal(amount) if amount and status != "not_required" else None,
        currency="INR",
        status=status,
        created_by_user_id=by.id,
        updated_by_user_id=by.id,
        **fields,
    )
    db.add(deposit)
    await db.commit()
    return deposit


async def mk_deposit_payment(db, deposit, payer, *, status: str = "pending", order_id: str | None = None, key: str | None = None, active: bool = True) -> Payment:
    payment = Payment(
        user_id=payer.id,
        division="overseas",
        reference_type="agent_deposit",
        reference_id=deposit.id,
        amount=deposit.amount,
        currency="INR",
        provider="razorpay",
        status=status,
        checkout_idempotency_key=key,
        checkout_provider_order_id=order_id or f"order_{uuid.uuid4().hex[:14]}",
    )
    db.add(payment)
    await db.flush()
    if active:
        deposit.active_payment_id = payment.id
    await db.commit()
    return payment


def signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    headers = {"content-type": "application/json", "x-razorpay-signature": hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest(), "x-razorpay-event-id": uuid.uuid4().hex}
    return raw, headers


def captured(order_id: str, amount_paise: int, *, event: str = "payment.captured", status: str = "captured") -> dict:
    return {"event": event, "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:14]}", "order_id": order_id, "status": status, "amount": amount_paise}}}}


async def audits(db, action: str, entity_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id)).order_by(AuditLog.created_at))).all())


async def deposit_payments(db, deposit_id) -> list[Payment]:
    return list((await db.scalars(select(Payment).where(Payment.reference_type == "agent_deposit", Payment.reference_id == deposit_id).order_by(Payment.created_at).execution_options(populate_existing=True))).all())


async def count_deposit_payments(db, deposit_id) -> int:
    return await db.scalar(select(func.count()).select_from(Payment).where(Payment.reference_type == "agent_deposit", Payment.reference_id == deposit_id))


async def reload(db, model, row_id):
    return await db.get(model, row_id, populate_existing=True)
