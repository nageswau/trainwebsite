"""itc-015 (DEC-SCOPE-364) -- refunds, adjustments and payment correction on an IT enrolment's fee account (`services/fee_accounts.py`).

Every write here is a new immutable `FeeAdjustment` row; nothing is updated in place or deleted (no such route exists):
- a **credit note** lowers what is owed -- the owed bills, latest due first (a bill covered whole becomes `waived`); what no bill
  absorbs is a credit (balance < 0). At most what is still payable.
- a **write-off** lowers what is owed, at most the balance still owed (so always fully absorbed by the bills).
- a **refund** pays a credit back out (Q-15: manual only, with the mode and reference), at most the credit -- so never more than paid.
- a **correction** of a mistyped manual payment (F2): the original is marked `reversed` (its amount, mode, reference and receipt stay
  as recorded), its bill is reopened as a new pending row, and the corrected payment is recorded on that bill by itc-013's
  `record_payment`; a `reversal` adjustment links the two.

Callers commit. The enrolment row is locked first, so two adjustments of one enrolment serialise; its owed bills are then locked in
`record_payment`'s way. The recorder is the approver until maker-checker exists (Q-14).
"""

import logging
import secrets
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enrollment, FeeAdjustment, Invoice, Payment, User
from app.services import fee_accounts
from app.services.audit_changes import audit_change
from app.services.billing_documents import DASH, generate_receipt_pdf

logger = logging.getLogger("app.fee_adjustments")

RECORDED = "it.fee.adjustment_recorded"
CORRECTED = "it.fee.payment_corrected"
DOCUMENT_KIND = "Fee-adjustment"  # stored under fee-adjustments/<document_no>.pdf
PREFIX = {"credit_note": "CN", "write_off": "WO", "refund": "RF"}
TITLES = {"credit_note": "Credit note", "write_off": "Write-off", "refund": "Refund receipt"}
NOT_BILLED = "Nothing has been billed on this enrolment"
PAYMENT_NOT_FOUND = "Payment not found"


def document_key(document_no: str) -> str:
    return f"{DOCUMENT_KIND.lower()}s/{document_no}.pdf"


async def _lock(db: AsyncSession, enrollment: Enrollment) -> dict:
    """Locks the enrolment row and returns its figures as they stand under that lock."""
    await db.scalar(select(Enrollment.id).where(Enrollment.id == enrollment.id).with_for_update())
    return (await fee_accounts.balance_for(db, [enrollment.id]))[enrollment.id]


async def _reissue_invoice(db: AsyncSession, bill: Payment, payer: User) -> None:
    """The invoice of a still-unpaid bill follows its amount (the discount endpoint's rule)."""
    from app.api.payments import _ensure_invoice  # noqa: PLC0415 -- the payments API imports fee_accounts, which this module imports

    stale = await db.scalar(select(Invoice).where(Invoice.payment_id == bill.id))
    if stale is not None:
        await db.delete(stale)
        await db.flush()
    await _ensure_invoice(db, bill, payer)


async def _lower_bills(db: AsyncSession, enrollment: Enrollment, payer: User, amount: float) -> float:
    """Takes up to `amount` off the owed bills, latest due first; returns how much they absorbed. A stale online checkout on a lowered
    bill is cleared (an old order cannot settle the smaller bill), as `record_payment` does for a split."""
    stmt = (
        select(Payment)
        .where(*fee_accounts._fee_rows([enrollment.id]), Payment.status.in_(fee_accounts.OWED), Payment.user_id == enrollment.student_id, Payment.amount > 0)
        .order_by(Payment.due_date.desc().nulls_first(), Payment.created_at.desc(), Payment.id.desc())
        .with_for_update()
    )
    left = amount
    for bill in (await db.scalars(stmt)).all():
        if left <= 0:
            break
        cut = min(float(bill.amount), left)
        bill.amount = round(float(bill.amount) - cut, 2)
        bill.provider, bill.checkout_provider_order_id, bill.checkout_idempotency_key = "manual", None, None
        if bill.amount == 0:
            bill.status = fee_accounts.WAIVED
        await _reissue_invoice(db, bill, payer)
        left = round(left - cut, 2)
    return round(amount - left, 2)


def _limit(kind: str, figures: dict) -> tuple[float, str]:
    if kind == "credit_note":
        return round(figures["total_payable"] - figures["credits"], 2), "Credit at most INR {:,.2f}, what is still payable on this enrolment"
    if kind == "write_off":
        return max(figures["balance"], 0.0), "Write off at most INR {:,.2f}, the balance still owed"
    credit = max(-figures["balance"], 0.0)
    if credit == 0:
        raise HTTPException(422, "There is no credit to refund on this account; record a credit note first")
    return credit, "Refund at most INR {:,.2f}, the credit on this account"


def _document(item: FeeAdjustment, payer: User, enrollment: Enrollment, balance: float) -> None:
    lines = [
        ("Document number", item.document_no or DASH),
        ("Student", payer.full_name),
        ("Student ID", payer.student_code or DASH),
        ("Enrolment", enrollment.enrollment_code or DASH),
        ("Amount", f"INR {float(item.amount):,.2f}"),
        ("Reason", item.reason),
        ("Payment mode", fee_accounts.MODE_LABELS.get(item.payment_mode or "", DASH)),
        ("Transaction reference", item.reference or DASH),
        ("Balance after this", f"INR {balance:,.2f}" if balance >= 0 else f"Credit INR {-balance:,.2f}"),
    ]
    generate_receipt_pdf(receipt_no=item.document_no, issued_on=date.today(), lines=lines, title=TITLES[item.kind], kind=DOCUMENT_KIND)


async def record(db: AsyncSession, actor: User, enrollment: Enrollment, kind: str, amount: float, reason: str, mode: str | None, reference: str | None) -> FeeAdjustment:
    """A credit note, write-off or refund (see the module docstring); 409 when nothing was ever billed, 422 past the kind's limit."""
    before = await _lock(db, enrollment)
    if before["state"] == "not_billed":
        raise HTTPException(409, NOT_BILLED)
    limit, message = _limit(kind, before)
    if amount > limit:
        raise HTTPException(422, message.format(limit))
    payer = await db.get(User, enrollment.student_id)
    applied = await _lower_bills(db, enrollment, payer, amount) if kind in fee_accounts.CREDITS else 0.0
    item = FeeAdjustment(
        enrollment_id=enrollment.id, kind=kind, amount=amount, applied_amount=applied, reason=reason, payment_mode=mode if kind == "refund" else None,
        reference=reference if kind == "refund" else None, document_no=f"{PREFIX[kind]}-{date.today():%Y}-{secrets.token_hex(4).upper()}", approved_by_id=actor.id,
    )  # fmt: skip
    db.add(item)
    await db.flush()
    after = (await fee_accounts.balance_for(db, [enrollment.id]))[enrollment.id]["balance"]
    _document(item, payer, enrollment, after)
    audit_change(db, actor, RECORDED, "enrollment", enrollment.id, {"balance": before["balance"]}, {"balance": after},
                 metadata={"adjustment_id": str(item.id), "kind": kind, "amount": amount})  # fmt: skip
    logger.info("it_fee_adjustment_recorded", extra={"extra_fields": {"actor_id": str(actor.id), "enrollment_id": str(enrollment.id), "adjustment_id": str(item.id), "kind": kind}})
    return item


async def correct(db: AsyncSession, actor: User, enrollment: Enrollment, payment_id: UUID, amount: float, mode: str, reference: str | None, reason: str) -> Payment:
    """Replaces a mistyped manual payment of this enrolment (F2); returns the replacement. 404 for another enrolment's payment, 409 for one
    already corrected, unpaid or paid through the gateway, 422 when nothing changes or the amount exceeds the reopened bill."""
    await _lock(db, enrollment)
    original = await db.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.division == "it", Payment.reference_type.in_(fee_accounts.FEE_REFERENCES), Payment.reference_id == enrollment.id).with_for_update()
    )
    if original is None:
        raise HTTPException(404, PAYMENT_NOT_FOUND)
    if original.status == "reversed":
        raise HTTPException(409, "This payment has already been corrected")
    if original.status not in fee_accounts.PAID:
        raise HTTPException(409, "Only a paid payment can be corrected")
    if original.payment_mode == "razorpay" or (original.provider == "razorpay" and not original.is_manual):
        raise HTTPException(409, "A gateway payment cannot be corrected; record a credit note and a refund instead")
    old = {"amount": float(original.amount), "payment_mode": original.payment_mode, "provider_reference": original.provider_reference}
    new = {"amount": amount, "payment_mode": mode, "provider_reference": reference}
    if old == new:
        raise HTTPException(422, "Nothing to correct: the amount, mode and reference are unchanged")
    payer = await db.get(User, enrollment.student_id)
    original.status = "reversed"
    reopened = Payment(
        user_id=original.user_id, division="it", reference_type=original.reference_type, reference_id=enrollment.id, amount=original.amount, currency=original.currency,
        due_date=original.due_date, installment_no=original.installment_no, emi_schedule_id=original.emi_schedule_id, discount_amount=original.discount_amount,
        discount_reason=original.discount_reason, discounted_by_id=original.discounted_by_id, status="pending", provider="manual", is_manual=True,
    )  # fmt: skip
    db.add(reopened)
    await db.flush()
    await _reissue_invoice(db, reopened, payer)
    replacement = await fee_accounts.record_payment(db, actor, enrollment, amount, mode, reference, bill_id=reopened.id)
    db.add(FeeAdjustment(enrollment_id=enrollment.id, kind="reversal", amount=original.amount, reason=reason, payment_id=original.id,
                         replacement_payment_id=replacement.id, approved_by_id=actor.id))  # fmt: skip
    audit_change(db, actor, CORRECTED, "enrollment", enrollment.id, old, new,
                 metadata={"payment_id": str(original.id), "replacement_payment_id": str(replacement.id)})  # fmt: skip
    logger.info("it_fee_payment_corrected", extra={"extra_fields": {"actor_id": str(actor.id), "enrollment_id": str(enrollment.id), "payment_id": str(original.id)}})
    return replacement
