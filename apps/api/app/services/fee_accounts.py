"""itc-013 (DEC-SCOPE-346) -- the per-enrolment fee account, computed from `Payment` (Q-13: no stored table, so it cannot drift).

An enrolment's fee rows are its IT `enrollment_fee` payments that bill something (failed or cancelled attempts bill nothing). From them,
in one grouped query (`balance_for`, fixed query count for list pages):

    course_fee = sum(amount + discount_amount)          the gross billed (+ what credits took off bills, itc-015)
    discount_approved = sum(discount_amount)            nehn-021's discount
    tax = 0                                             Q-12: GST is NEEDS_CONFIRMATION
    total_payable = course_fee - discount_approved + tax
    paid_confirmed = sum(amount) of paid/succeeded rows
    credits = credit notes + write-offs                 itc-015 (DEC-SCOPE-363 F1)
    refunded = refunds                                  itc-015: a refund pays a credit back out
    balance = total_payable - paid_confirmed - credits + refunded

`student_access` sums the same owed rows per student, so the account and the access state agree. Staff record an offline payment with
`record_payment` (no commit): never more than the oldest owed bill, so an overpayment cannot be created; a part payment splits that bill.

itc-016 (DEC-SCOPE-358): each account also lists its installments (the same rows) with a derived `overdue` and the reminders sent.

itc-015 (DEC-SCOPE-363): a credit note or write-off lowers the owed bills (`services/fee_adjustments.py`); a bill it covers whole is
`waived` (amount 0, still billed so its gross and discount count). A corrected payment is `reversed` and bills nothing.
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Enrollment, FeeAdjustment, FeeReminderLog, Invoice, Payment, Program, User
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.fee_accounts")

FEE_REFERENCES = ("enrollment_fee", "enrollment")  # the seed's legacy rows say `enrollment` (management_it_revenue)
PAID = ("paid", "succeeded")
OWED = ("pending", "overdue")
WAIVED = "waived"  # itc-015: a bill a credit covered whole
CREDITS = ("credit_note", "write_off")  # itc-015: the adjustments that lower what is owed
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
        Payment.status.in_((*OWED, *PAID, WAIVED)),
    )


def _state(billed: bool, paid: float, balance: float) -> str:
    if not billed:
        return "not_billed"
    if balance <= 0:
        return "fully_paid"
    return "partially_paid" if paid > 0 else "enrolled_pending_payment"


def _figures(billed: bool, gross: float, discount: float, paid: float, credits: float, applied: float, refunded: float) -> dict:
    tax = 0.0
    course_fee = round(gross + applied, 2)
    total_payable = round(course_fee - discount + tax, 2)
    balance = round(total_payable - paid - credits + refunded, 2)
    return {
        "course_fee": course_fee, "discount_approved": discount, "tax": tax, "total_payable": total_payable, "paid_confirmed": paid,
        "credits": credits, "refunded": refunded, "balance": balance, "state": _state(billed, paid, balance),
    }  # fmt: skip


async def balance_for(db: AsyncSession, enrollment_ids: list[UUID]) -> dict[UUID, dict]:
    """Every requested enrolment's figures (an unbilled one included), in one query: its fee rows UNION ALL its adjustments (itc-015)."""
    if not enrollment_ids:
        return {}
    zero = literal(0)
    bills = select(
        Payment.reference_id.label("eid"), (Payment.amount + Payment.discount_amount).label("gross"), Payment.discount_amount.label("discount"),
        case((Payment.status.in_(PAID), Payment.amount), else_=0).label("paid"), zero.label("credits"), zero.label("applied"), zero.label("refunded"),
        literal(1).label("bills"),
    ).where(*_fee_rows(enrollment_ids))  # fmt: skip
    adjustments = select(
        FeeAdjustment.enrollment_id, zero, zero, zero, case((FeeAdjustment.kind.in_(CREDITS), FeeAdjustment.amount), else_=0), FeeAdjustment.applied_amount,
        case((FeeAdjustment.kind == "refund", FeeAdjustment.amount), else_=0), zero,
    ).where(FeeAdjustment.enrollment_id.in_(enrollment_ids))  # fmt: skip
    u = union_all(bills, adjustments).subquery()
    sums = [func.sum(col) for col in (u.c.gross, u.c.discount, u.c.paid, u.c.credits, u.c.applied, u.c.refunded, u.c.bills)]
    totals = {eid: [float(v) for v in values] for eid, *values in (await db.execute(select(u.c.eid, *sums).group_by(u.c.eid))).all()}
    out = {}
    for eid in enrollment_ids:
        *money, billed_rows = totals.get(eid, [0.0] * 7)
        out[eid] = _figures(billed_rows > 0, *money)
    return out


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


def adjustment_out(a: FeeAdjustment) -> dict:
    """itc-015: one adjustment as every reader of the account sees it (the reason is written for the student to read)."""
    return {"id": a.id, "kind": a.kind, "amount": float(a.amount), "reason": a.reason, "payment_mode": a.payment_mode, "reference": a.reference,
            "document_no": a.document_no, "created_at": a.created_at}  # fmt: skip


async def _adjustments(db: AsyncSession, enrollment_ids: list[UUID]) -> dict[UUID, list[dict]]:
    stmt = select(FeeAdjustment).where(FeeAdjustment.enrollment_id.in_(enrollment_ids)).order_by(FeeAdjustment.created_at, FeeAdjustment.id)
    out: dict[UUID, list[dict]] = {}
    for a in (await db.scalars(stmt)).all():
        out.setdefault(a.enrollment_id, []).append(adjustment_out(a))
    return out


async def accounts(db: AsyncSession, enrollments: list[Enrollment]) -> list[dict]:
    """The full account (figures, the course and batch names, the installments, the next amount due, the adjustments) of each enrolment,
    in four queries. itc-018 (DEC-SCOPE-353 F1): `next_due` is the first owed installment, in `record_payment`'s order -- the next amount
    the student owes."""
    if not enrollments:
        return []
    ids = [e.id for e in enrollments]
    stmt = select(Enrollment.id, Program.title, Batch.name).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id).where(Enrollment.id.in_(ids))
    names = {eid: (course, batch) for eid, course, batch in (await db.execute(stmt)).all()}  # an enrolment always has a batch and course
    figures = await balance_for(db, ids)
    installments = await _installments(db, ids)
    adjustments = await _adjustments(db, ids)
    out = []
    for e in enrollments:
        rows = installments.get(e.id, [])
        owed = next((i for i in rows if i["status"] == "pending"), None)
        out.append({"enrollment_id": e.id, "enrollment_code": e.enrollment_code, "course": names[e.id][0], "batch": names[e.id][1], "currency": "INR",
                    **figures[e.id], "next_due": owed and {"amount": owed["amount"], "due_date": owed["due_date"]}, "installments": rows,
                    "adjustments": adjustments.get(e.id, [])})  # fmt: skip
    return out


async def account(db: AsyncSession, enrollment: Enrollment) -> dict:
    return (await accounts(db, [enrollment]))[0]


async def record_payment(db: AsyncSession, actor: User, enrollment: Enrollment, amount: float, mode: str, reference: str | None, *, bill_id: UUID | None = None) -> Payment:
    """No commit. Pays the oldest owed bill (by due date, then age; itc-015: or the bill `bill_id`, a correction's reopened bill) under a
    row lock, so two recordings and a gateway confirmation of the same bill serialise. The whole bill: it becomes paid. Part of it: the bill keeps the rest (its invoice is reissued and a stale
    online checkout is cleared, so an old order cannot settle the smaller bill) and a new paid row holds this payment."""
    from app.api.payments import _ensure_invoice, _ensure_receipt  # noqa: PLC0415 -- the payments API imports this module's readers

    stmt = (
        select(Payment)
        .where(*_fee_rows([enrollment.id]), Payment.status.in_(OWED), Payment.user_id == enrollment.student_id, *([Payment.id == bill_id] if bill_id else []))
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
