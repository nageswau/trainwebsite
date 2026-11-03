"""itc-013 (DEC-SCOPE-346) -- the per-enrolment fee account, computed from `Payment` (Q-13: no stored table, so it cannot drift).

An enrolment's fee rows are its IT `enrollment_fee` payments that bill something (failed or cancelled attempts bill nothing). From them,
in one grouped query (`balance_for`, fixed query count for list pages):

    course_fee = sum(amount + discount_amount)          the gross billed
    discount_approved = sum(discount_amount)            nehn-021's discount
    tax = 0                                             Q-12: GST is NEEDS_CONFIRMATION
    total_payable = course_fee - discount_approved + tax
    paid_confirmed = sum(amount) of paid/succeeded rows
    credits = 0                                         refunds and adjustments arrive with itc-015
    balance = total_payable - paid_confirmed - credits

`student_access` sums the same owed rows per student, so the account and the access state agree. Staff record an offline payment with
`record_payment` (no commit): never more than the oldest owed bill, so an overpayment cannot be created; a part payment splits that bill.

itc-016 (DEC-SCOPE-357): each account also lists its installments (the same rows) with a derived `overdue` and the reminders sent.
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Enrollment, FeeReminderLog, Invoice, Payment, Program, User
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.fee_accounts")

FEE_REFERENCES = ("enrollment_fee", "enrollment")  # the seed's legacy rows say `enrollment` (management_it_revenue)
PAID = ("paid", "succeeded")
OWED = ("pending", "overdue")
OFFLINE_MODES = ("cash", "upi", "card", "bank_transfer", "cheque")  # `razorpay` is set only by the gateway's confirmation
MODE_LABELS = {"cash": "Cash", "upi": "UPI", "card": "Card", "bank_transfer": "Bank transfer", "cheque": "Cheque", "razorpay": "Razorpay"}
NOTHING_OWED = "Nothing is owed on this enrolment"
RECORDED = "it.fee.payment_recorded"
INDIA = ZoneInfo("Asia/Kolkata")


def _fee_rows(enrollment_ids):
    return (
        Payment.division == "it",
        Payment.reference_type.in_(FEE_REFERENCES),
        Payment.reference_id.in_(enrollment_ids),
        Payment.status.in_((*OWED, *PAID)),
    )


def _state(billed: bool, paid: float, balance: float) -> str:
    if not billed:
        return "not_billed"
    if balance <= 0:
        return "fully_paid"
    return "partially_paid" if paid > 0 else "enrolled_pending_payment"


def _figures(billed: bool, gross: float, discount: float, paid: float) -> dict:
    tax = credits = 0.0
    total_payable = gross - discount + tax
    balance = total_payable - paid - credits
    return {
        "course_fee": gross, "discount_approved": discount, "tax": tax, "total_payable": total_payable, "paid_confirmed": paid,
        "credits": credits, "balance": balance, "state": _state(billed, paid, balance),
    }  # fmt: skip


async def balance_for(db: AsyncSession, enrollment_ids: list[UUID]) -> dict[UUID, dict]:
    """Every requested enrolment's figures (an unbilled one included), in one query."""
    if not enrollment_ids:
        return {}
    stmt = (
        select(
            Payment.reference_id,
            func.sum(Payment.amount + Payment.discount_amount),
            func.sum(Payment.discount_amount),
            func.sum(case((Payment.status.in_(PAID), Payment.amount), else_=0)),
        )
        .where(*_fee_rows(enrollment_ids))
        .group_by(Payment.reference_id)
    )
    totals = {ref: (float(gross), float(discount), float(paid)) for ref, gross, discount, paid in (await db.execute(stmt)).all()}
    return {eid: _figures(eid in totals, *totals.get(eid, (0.0, 0.0, 0.0))) for eid in enrollment_ids}


async def student_balances(db: AsyncSession, student_ids: list[UUID]) -> dict[UUID, float | None]:
    """Each student's balance over their billed enrolments (None when nothing was ever billed), in two queries."""
    if not student_ids:
        return {}
    pairs = (await db.execute(select(Enrollment.id, Enrollment.student_id).where(Enrollment.student_id.in_(student_ids)))).all()
    figures = await balance_for(db, [eid for eid, _ in pairs])
    out: dict[UUID, float | None] = dict.fromkeys(student_ids)
    for eid, student_id in pairs:
        if figures[eid]["state"] != "not_billed":
            out[student_id] = (out[student_id] or 0.0) + figures[eid]["balance"]
    return out


def india_today() -> date:
    """itc-016 (F1): fee due dates are India calendar days."""
    return datetime.now(INDIA).date()


async def _installments(db: AsyncSession, enrollment_ids: list[UUID]) -> dict[UUID, list[dict]]:
    """itc-016 (F1/F7): each enrolment's fee rows in `record_payment`'s order (due date, then age), with the reminders sent for each, in
    one query. `overdue` is derived (owed and due before today, IST); status is `paid` or `pending` (a legacy stored `overdue` reads as
    pending + overdue)."""
    stmt = (
        select(Payment.id, Payment.reference_id, Payment.installment_no, Payment.amount, Payment.due_date, Payment.status,
               FeeReminderLog.kind, FeeReminderLog.offset_days, FeeReminderLog.reminder_date)
        .outerjoin(FeeReminderLog, FeeReminderLog.payment_id == Payment.id)
        .where(*_fee_rows(enrollment_ids), Payment.amount > 0)
        .order_by(Payment.due_date.asc().nulls_last(), Payment.created_at, Payment.id, FeeReminderLog.reminder_date, FeeReminderLog.created_at)
    )  # fmt: skip
    today, out, seen = india_today(), {}, {}
    for r in (await db.execute(stmt)).all():  # keyed by `reference_id`, never null here (filtered by `_fee_rows`)
        if (item := seen.get(r.id)) is None:
            owed = r.status in OWED
            item = seen[r.id] = {
                "id": r.id, "installment_no": r.installment_no, "amount": float(r.amount), "due_date": r.due_date, "status": "pending" if owed else "paid",
                "overdue": owed and r.due_date is not None and r.due_date < today, "reminders": [],
            }  # fmt: skip
            out.setdefault(r.reference_id, []).append(item)
        if r.kind is not None:
            item["reminders"].append({"kind": r.kind, "offset_days": r.offset_days, "sent_on": r.reminder_date})
    return out


async def accounts(db: AsyncSession, enrollments: list[Enrollment]) -> list[dict]:
    """The full account (figures, the course and batch names, the installments, the next amount due) of each enrolment, in three queries.
    itc-018 (DEC-SCOPE-353 F1): `next_due` is the first owed installment, in `record_payment`'s order -- the next amount the student owes."""
    if not enrollments:
        return []
    ids = [e.id for e in enrollments]
    stmt = select(Enrollment.id, Program.title, Batch.name).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id).where(Enrollment.id.in_(ids))
    names = {eid: (course, batch) for eid, course, batch in (await db.execute(stmt)).all()}  # an enrolment always has a batch and course
    figures = await balance_for(db, ids)
    installments = await _installments(db, ids)
    out = []
    for e in enrollments:
        rows = installments.get(e.id, [])
        owed = next((i for i in rows if i["status"] == "pending"), None)
        out.append({"enrollment_id": e.id, "enrollment_code": e.enrollment_code, "course": names[e.id][0], "batch": names[e.id][1], "currency": "INR",
                    **figures[e.id], "next_due": owed and {"amount": owed["amount"], "due_date": owed["due_date"]}, "installments": rows})  # fmt: skip
    return out


async def account(db: AsyncSession, enrollment: Enrollment) -> dict:
    return (await accounts(db, [enrollment]))[0]


async def record_payment(db: AsyncSession, actor: User, enrollment: Enrollment, amount: float, mode: str, reference: str | None) -> Payment:
    """No commit. Pays the oldest owed bill (by due date, then age) under a row lock, so two recordings and a gateway confirmation of
    the same bill serialise. The whole bill: it becomes paid. Part of it: the bill keeps the rest (its invoice is reissued and a stale
    online checkout is cleared, so an old order cannot settle the smaller bill) and a new paid row holds this payment."""
    from app.api.payments import _ensure_invoice, _ensure_receipt  # noqa: PLC0415 -- the payments API imports this module's readers

    stmt = (
        select(Payment)
        .where(*_fee_rows([enrollment.id]), Payment.status.in_(OWED), Payment.user_id == enrollment.student_id)
        .order_by(Payment.due_date.asc().nulls_last(), Payment.created_at, Payment.id)
        .with_for_update()
    )
    owed = list((await db.scalars(stmt)).all())
    if not owed:
        raise HTTPException(409, NOTHING_OWED)
    bill = owed[0]
    if amount > float(bill.amount):
        raise HTTPException(422, f"Record at most INR {float(bill.amount):,.2f}, the amount still owed on the next bill")
    before = (await balance_for(db, [enrollment.id]))[enrollment.id]["balance"]
    payer = await db.get(User, enrollment.student_id)
    if amount == float(bill.amount):
        paid = bill
    else:
        bill.amount = float(bill.amount) - amount
        bill.provider, bill.checkout_provider_order_id, bill.checkout_idempotency_key = "manual", None, None
        stale = await db.scalar(select(Invoice).where(Invoice.payment_id == bill.id))
        if stale is not None:  # the invoice of a still-unpaid bill follows its amount (the discount endpoint's rule)
            await db.delete(stale)
            await db.flush()
        await _ensure_invoice(db, bill, payer)
        paid = Payment(
            user_id=bill.user_id, division="it", reference_type=bill.reference_type, reference_id=enrollment.id, amount=amount, currency=bill.currency, due_date=bill.due_date
        )  # marked paid just below, like a whole bill
        db.add(paid)
        await db.flush()
        await _ensure_invoice(db, paid, payer)
    paid.status, paid.paid_at, paid.provider, paid.is_manual = "paid", datetime.now(UTC), "manual", True
    paid.payment_mode, paid.provider_reference = mode, reference
    await db.flush()
    await _ensure_receipt(db, paid, payer)
    after = before - amount
    audit_change(db, actor, RECORDED, "enrollment", enrollment.id, {"balance": before}, {"balance": after},
                 metadata={"payment_id": str(paid.id), "payment_mode": mode, "split": paid is not bill})  # fmt: skip
    logger.info("it_fee_payment_recorded", extra={"extra_fields": {"actor_id": str(actor.id), "enrollment_id": str(enrollment.id), "payment_id": str(paid.id), "mode": mode}})
    return paid
