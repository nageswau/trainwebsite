"""AGN-011 -- an agency application's deposit, paid through EduSphere Razorpay (DEC-SCOPE-057; spec §4).

Master, and Staff for students assigned to them, set the deposit and pay it (D7); anything outside the caller's scope is 404 (the AGN-008
application scope). Writes lock the organisation, the application, the deposit and then any payment, and commit once. Only the payments
paid hook marks a deposit paid; only an Overseas Admin records remittance and refunds (D5).
"""

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_applications import _audit, _gate, _locked, _log, _refuse_closed
from app.api.deps import get_current_user
from app.api.payments import _ensure_invoice
from app.core.database import get_db
from app.models import ApplicationDeposit, AuditLog, Payment, User
from app.schemas import AgentDepositSave
from app.services import agent_deposits as deposits
from app.services.agent_applications import detail
from app.services.agent_deposits import PAID_LOCKED, PAID_STATES, cancel_active, deposit_for
from app.services.payment import payments

router = APIRouter(prefix="/workflows/overseas/agent/crm/applications", tags=["agent-deposits"])
admin_router = APIRouter(prefix="/overseas-admin/deposits", tags=["overseas-admin"])


@router.put("/{application_id}/deposit")
async def save_deposit(application_id: UUID, payload: AgentDepositSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§4.2: create or replace the deposit terms while it is unpaid. An identical request writes nothing (a retry is safe). Changing the
    amount, or making it not required, cancels the open checkout so its order can never mark the deposit paid."""
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    deposit = await deposit_for(db, item.id, lock=True)
    if deposit is not None and deposit.status in PAID_STATES:
        raise HTTPException(409, PAID_LOCKED)
    new = {"required": payload.required, "amount": payload.amount, "due_date": payload.due_date, "status": "pending" if payload.required else "not_required"}
    if deposit is None:
        deposit = ApplicationDeposit(application_id=item.id, currency="INR", created_by_user_id=user.id, updated_by_user_id=user.id)
        db.add(deposit)
        changed = sorted(k for k in ("required", "amount", "due_date") if new[k] is not None or k == "required")
    else:
        changed = sorted(k for k in ("required", "amount", "due_date") if getattr(deposit, k) != new[k])
    if not changed:
        return {"application": await detail(db, user, item, record=record)}
    if {"required", "amount"} & set(changed):
        await cancel_active(db, deposit)
    for key, value in new.items():
        setattr(deposit, key, value)
    deposit.updated_by_user_id = user.id
    _audit(db, user, "deposit", item.id, {"fields": changed, "required": payload.required})
    await db.commit()
    _log("agent_deposit_saved", membership, user, item.id, fields=changed, required=payload.required)
    return {"application": await detail(db, user, item, record=record)}


@router.post("/{application_id}/deposit/checkout")
async def deposit_checkout(
    application_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§4.4 (AC1, AC3, AC6): open a Razorpay order for the stored deposit amount -- no request body is read. Three steps so no row lock
    is held during the up-to-20-second provider call: (1) under the locks, check and record the payer-owned attempt; (2) call Razorpay;
    (3) under the locks again, keep the order id, or cancel the attempt on a provider error."""
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(422, "Idempotency-Key header is required")
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    await _refuse_closed(db, user, item)
    deposit = await deposit_for(db, item.id, lock=True)
    if deposit is None or deposit.status == "not_required":
        raise HTTPException(409, deposits.NOT_REQUIRED)
    if deposit.status in PAID_STATES:
        raise HTTPException(409, deposits.ALREADY_PAID)
    if not deposits.payment_available():
        await db.rollback()
        return {"status": "configuration_required"}  # AC6: today's checkout contract; nothing is written
    active = await deposits.locked_payment(db, deposit.active_payment_id) if deposit.active_payment_id else None
    if active is not None and active.status == deposits.OPEN_PAYMENT:
        if active.user_id == user.id and active.checkout_idempotency_key == idempotency_key:
            if active.checkout_provider_order_id:
                replay = deposits.checkout_result(active, replayed=True)  # read before the rollback expires the row
                await db.rollback()
                return replay
            raise HTTPException(409, deposits.OPENING)
        if deposits.blocked_by_other(active, user.id):
            raise HTTPException(409, deposits.OTHER_PAYING)
    wait = await deposits.checkout_wait_seconds(db, deposit.id)
    if wait:
        _log("agent_deposit_checkout_throttled", membership, user, item.id, level=logging.WARNING, wait_seconds=wait)
        raise HTTPException(429, deposits.CHECKOUT_THROTTLED, headers={"Retry-After": str(wait)})
    await cancel_active(db, deposit)  # an abandoned or expired attempt: its order can no longer mark the deposit paid
    payment = Payment(
        user_id=user.id,
        division="overseas",
        reference_type=deposits.REFERENCE_TYPE,
        reference_id=deposit.id,
        amount=deposit.amount,
        currency=deposit.currency,
        provider="razorpay",
        due_date=deposit.due_date,
        checkout_idempotency_key=idempotency_key,
    )
    db.add(payment)
    await db.flush()
    deposit.active_payment_id = payment.id
    deposit_id, payment_id, amount = deposit.id, payment.id, float(payment.amount)
    await db.commit()

    try:
        result = await payments.create_checkout("razorpay", amount, "INR", f"PAY-{payment_id}")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        await _abandon(db, deposit_id, payment_id)
        _log("agent_deposit_checkout_provider_error", membership, user, item.id, level=logging.WARNING, error=type(exc).__name__)
        raise HTTPException(502, deposits.PROVIDER_DOWN) from None

    deposit = await db.get(ApplicationDeposit, deposit_id, with_for_update=True, populate_existing=True)
    payment = await deposits.locked_payment(db, payment_id)
    if result.get("status") != "ready":  # the keys were removed while the order was opening
        await _abandon(db, deposit_id, payment_id)
        return {"status": "configuration_required"}
    if payment.status != deposits.OPEN_PAYMENT or deposit.active_payment_id != payment.id:
        await db.commit()
        raise HTTPException(409, deposits.CHANGED)  # the amount changed meanwhile, which cancelled this attempt
    payment.checkout_provider_order_id = result["provider_order_id"]
    await _ensure_invoice(db, payment, user)
    db.add(AuditLog(user_id=user.id, action="payment.checkout", entity_type="payment", entity_id=str(payment.id), metadata_json={"provider": "razorpay", "checkout_status": "ready"}))
    _audit(db, user, "deposit_checkout", item.id, {"payment_id": str(payment.id)})
    await db.commit()
    _log("agent_deposit_checkout_opened", membership, user, item.id, payment_id=str(payment.id))
    return deposits.checkout_result(payment)


async def _abandon(db: AsyncSession, deposit_id, payment_id) -> None:
    """A failed attempt: cancel the payment and free the deposit, in the deposit-then-payment lock order."""
    await db.rollback()
    deposit = await db.get(ApplicationDeposit, deposit_id, with_for_update=True, populate_existing=True)
    payment = await deposits.locked_payment(db, payment_id)
    if payment is not None and payment.status == deposits.OPEN_PAYMENT:
        payment.status = deposits.CANCELLED
    if deposit is not None and deposit.active_payment_id == payment_id:
        deposit.active_payment_id = None
    await db.commit()
