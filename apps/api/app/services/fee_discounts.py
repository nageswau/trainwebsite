"""itc-014 (DEC-SCOPE-363) -- discount and waiver approval (maker-checker) for an IT enrolment's fee.

A request asks for an amount off what the enrolment still owes; it never touches `Payment` (AC1). An approval by someone other than the
requester (AC3) takes the amount off the owed bills, latest due first (the reverse of `fee_accounts.record_payment`'s order), with the
nehn-019 discount columns, the bill's invoice reissued and a stale online checkout cleared; a bill brought to 0 becomes `waived`, so it
is never offered for payment. The approval is audited with the account's old and new figures (AC2). Nothing here commits.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Batch, Enrollment, FeeDiscountRequest, Invoice, Payment, Program, User
from app.services import fee_accounts
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.fee_discounts")

NOT_FOUND = "Discount request not found"
OWN_REQUEST = "You cannot decide your own discount request; another approver must"
ALREADY_PENDING = "A discount request for this enrolment is already waiting for approval"
NOT_PENDING = "This discount request has already been decided"
FIGURES = ("discount_approved", "total_payable", "balance")


async def _owed_bills(db: AsyncSession, enrollment: Enrollment, *, lock: bool = False) -> list[Payment]:
    """The enrolment's owed bills, latest due first (undated bills are the latest, as `record_payment` pays them last)."""
    stmt = (
        select(Payment)
        .where(*fee_accounts._fee_rows([enrollment.id]), Payment.status.in_(fee_accounts.OWED), Payment.user_id == enrollment.student_id)
        .order_by(Payment.due_date.desc().nulls_first(), Payment.created_at.desc(), Payment.id.desc())
    )
    return list((await db.scalars(stmt.with_for_update() if lock else stmt)).all())


def _owed(bills: list[Payment]) -> float:
    return sum(float(b.amount) for b in bills)


async def create(db: AsyncSession, actor: User, enrollment: Enrollment, amount: float, reason: str) -> FeeDiscountRequest:
    owed = _owed(await _owed_bills(db, enrollment))
    if owed <= 0:
        raise HTTPException(409, fee_accounts.NOTHING_OWED)
    if amount > owed:
        raise HTTPException(422, f"Request at most INR {owed:,.2f}, the balance still owed")
    item = FeeDiscountRequest(enrollment_id=enrollment.id, amount=amount, reason=reason, status="pending", requested_by_id=actor.id)
    db.add(item)
    try:
        await db.flush()  # the partial unique index allows one pending request per enrolment, even under a race
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, ALREADY_PENDING) from None
    audit_change(db, actor, "it.fee.discount_requested", "enrollment", enrollment.id, {}, {"discount_requested": amount}, metadata={"request_id": str(item.id)})
    return item


async def _pending(db: AsyncSession, actor: User, request_id: UUID) -> FeeDiscountRequest:
    """The request, locked, if this actor may decide it now."""
    stmt = select(FeeDiscountRequest).where(FeeDiscountRequest.id == request_id).with_for_update().execution_options(populate_existing=True)
    item = await db.scalar(stmt)
    if item is None:
        raise HTTPException(404, NOT_FOUND)
    if item.requested_by_id == actor.id:
        raise HTTPException(403, OWN_REQUEST)
    if item.status != "pending":
        raise HTTPException(409, NOT_PENDING)
    return item


def _decide(item: FeeDiscountRequest, actor: User, status: str, note: str | None) -> None:
    item.status, item.decided_by_id, item.decided_at, item.decision_note = status, actor.id, datetime.now(UTC), note


async def approve(db: AsyncSession, actor: User, request_id: UUID, note: str | None) -> FeeDiscountRequest:
    from app.api.payments import _ensure_invoice  # noqa: PLC0415 -- the payments API imports fee_accounts' readers

    item = await _pending(db, actor, request_id)
    enrollment = await db.get(Enrollment, item.enrollment_id)
    bills = await _owed_bills(db, enrollment, lock=True)  # a payment recorded meanwhile serialises with this
    amount, owed = float(item.amount), _owed(bills)
    if amount > owed:
        raise HTTPException(409, f"Only INR {owed:,.2f} is still owed now. Reject this request, or ask for a new one.")
    before = (await fee_accounts.balance_for(db, [enrollment.id]))[enrollment.id]
    payer = await db.get(User, enrollment.student_id)
    left = amount
    for bill in bills:
        if left <= 0:
            break
        off = min(left, float(bill.amount))
        left -= off
        bill.amount = float(bill.amount) - off
        bill.discount_amount = float(bill.discount_amount or 0) + off
        bill.discount_reason, bill.discounted_by_id = item.reason, actor.id
        bill.provider, bill.checkout_provider_order_id, bill.checkout_idempotency_key = "manual", None, None  # an old order can't settle it
        if bill.amount == 0:
            bill.status = "waived"
        stale = await db.scalar(select(Invoice).where(Invoice.payment_id == bill.id))
        if stale is not None:  # the invoice of a still-unpaid bill follows its amount (the discount endpoint's rule)
            await db.delete(stale)
            await db.flush()
        await _ensure_invoice(db, bill, payer)
    _decide(item, actor, "approved", note)
    await db.flush()
    after = (await fee_accounts.balance_for(db, [enrollment.id]))[enrollment.id]
    audit_change(db, actor, "it.fee.discount_approved", "enrollment", enrollment.id, {k: before[k] for k in FIGURES}, {k: after[k] for k in FIGURES},
                 metadata={"request_id": str(item.id)})  # fmt: skip
    logger.info("it_fee_discount_approved", extra={"extra_fields": {"actor_id": str(actor.id), "enrollment_id": str(enrollment.id), "request_id": str(item.id)}})
    return item


async def reject(db: AsyncSession, actor: User, request_id: UUID, note: str) -> FeeDiscountRequest:
    item = await _pending(db, actor, request_id)
    _decide(item, actor, "rejected", note)
    audit_change(db, actor, "it.fee.discount_rejected", "enrollment", item.enrollment_id, {"status": "pending"}, {"status": "rejected"},
                 metadata={"request_id": str(item.id)})  # fmt: skip
    return item


async def listing(db: AsyncSession, actor: User, *, enrollment_id: UUID | None = None, status: str | None = None, request_id: UUID | None = None) -> list[dict]:
    """Requests with their enrolment, student, course and people, in one query: an enrolment's (newest first) or the queue by status
    (pending oldest first, so the longest wait is on top; decided newest first)."""
    student, requester, decider = aliased(User), aliased(User), aliased(User)
    stmt = (
        select(FeeDiscountRequest, Enrollment.enrollment_code, student.id, student.full_name, Program.title, requester.full_name, decider.full_name)
        .join(Enrollment, Enrollment.id == FeeDiscountRequest.enrollment_id)
        .join(student, student.id == Enrollment.student_id)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .join(requester, requester.id == FeeDiscountRequest.requested_by_id)
        .outerjoin(decider, decider.id == FeeDiscountRequest.decided_by_id)
    )
    if request_id is not None:
        stmt = stmt.where(FeeDiscountRequest.id == request_id)
    if enrollment_id is not None:
        stmt = stmt.where(FeeDiscountRequest.enrollment_id == enrollment_id).order_by(FeeDiscountRequest.created_at.desc())
    if status is not None:
        newest = FeeDiscountRequest.created_at.asc() if status == "pending" else FeeDiscountRequest.created_at.desc()
        stmt = stmt.where(FeeDiscountRequest.status == status).order_by(newest).limit(200)
    return [
        {
            "id": r.id,
            "enrollment_id": r.enrollment_id,
            "enrollment_code": code,
            "student": {"id": sid, "full_name": sname},
            "course": course,
            "amount": float(r.amount),
            "reason": r.reason,
            "status": r.status,
            "requested_by": {"id": r.requested_by_id, "full_name": rname},
            "created_at": r.created_at,
            "decided_by": r.decided_by_id and {"id": r.decided_by_id, "full_name": dname},
            "decided_at": r.decided_at,
            "decision_note": r.decision_note,
            "own": r.requested_by_id == actor.id,
        }
        for r, code, sid, sname, course, rname, dname in (await db.execute(stmt)).all()
    ]


async def one(db: AsyncSession, actor: User, request_id: UUID) -> dict:
    return (await listing(db, actor, request_id=request_id))[0]
