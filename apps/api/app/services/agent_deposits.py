"""AGN-011 / DEC-SCOPE-057 -- the deposit on an agency application, paid through EduSphere Razorpay.

Functions only (the services/agent_applications.py shape): nothing here commits -- the routers and the payments paid hook lock, write,
audit and commit. Lock order everywhere: organisation, application, deposit, then payment (the paid hook takes deposit then payment).
Spec: docs/superpowers/specs/2026-10-02-agn-011-deposit-collection-design.md.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models import AgentOrg, AgentOrgMember, AgentStudent, ApplicationDeposit, AuditLog, OverseasApplication, Payment, Receipt, University, User

logger = logging.getLogger("app.agent_deposits")

REFERENCE_TYPE = "agent_deposit"
PAID_STATES = ("paid", "remitted", "refunded")
OPEN_PAYMENT = "pending"
CANCELLED = "cancelled"

PAID_LOCKED = "This deposit is already paid and can no longer be changed"
NOT_REQUIRED = "No deposit is required for this application"
ALREADY_PAID = "This deposit is already paid"
OPENING = "A checkout is already being opened for this deposit"
OTHER_PAYING = "Another team member is paying this deposit -- try again in a few minutes"
CHECKOUT_THROTTLED = "Too many payment attempts for this deposit -- try again later"
PROVIDER_DOWN = "The payment provider is unavailable -- nothing was charged. Try again shortly"
CHANGED = "This deposit changed while the checkout was opening -- reload and try again"

OTHER_MEMBER_WINDOW = timedelta(minutes=15)  # D8: another member's open checkout blocks a new one this long
CHECKOUT_WINDOW = timedelta(hours=1)
CHECKOUT_LIMIT = 10  # D8: pay attempts per deposit per rolling hour (each one opens a Razorpay order)


def payment_available() -> bool:
    """AC6: both keys are needed to open a Razorpay order (`PaymentService.create_checkout`)."""
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


async def deposit_for(db: AsyncSession, application_id, *, lock: bool = False) -> ApplicationDeposit | None:
    stmt = select(ApplicationDeposit).where(ApplicationDeposit.application_id == application_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def locked_payment(db: AsyncSession, payment_id) -> Payment | None:
    return await db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update().execution_options(populate_existing=True))


def blocked_by_other(active: Payment, user_id) -> bool:
    """D8: a different member's open checkout younger than 15 minutes (they may be in the Razorpay window right now)."""
    return active.user_id != user_id and active.created_at > datetime.now(UTC) - OTHER_MEMBER_WINDOW


async def checkout_wait_seconds(db: AsyncSession, deposit_id) -> int:
    """D8: seconds until another pay attempt is allowed, 0 when under the limit. Counted in PostgreSQL, so it holds across instances;
    the caller holds the deposit lock, so two requests cannot both squeeze under it."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(Payment.created_at).where(Payment.reference_type == REFERENCE_TYPE, Payment.reference_id == deposit_id, Payment.created_at > now - CHECKOUT_WINDOW).order_by(Payment.created_at)
        )
    ).all()
    if len(recent) < CHECKOUT_LIMIT:
        return 0
    return max(1, int((recent[-CHECKOUT_LIMIT] + CHECKOUT_WINDOW - now).total_seconds()) + 1)


def checkout_result(payment: Payment, *, replayed: bool = False) -> dict:
    """What the browser needs to open Razorpay Checkout: the public key id only, never a secret."""
    body = {
        "status": "ready",
        "payment_id": str(payment.id),
        "key_id": settings.razorpay_key_id,
        "provider_order_id": payment.checkout_provider_order_id,
        "amount": float(payment.amount),
        "currency": payment.currency,
    }
    return body | {"replayed": True} if replayed else body


async def cancel_active(db: AsyncSession, deposit: ApplicationDeposit) -> None:
    """A superseded checkout: the open payment becomes `cancelled` so its stale order can never mark the deposit paid (§4.5). The caller
    holds the deposit lock; the payment is locked after it."""
    if deposit.active_payment_id is None:
        return
    payment = await locked_payment(db, deposit.active_payment_id)
    if payment is not None and payment.status == OPEN_PAYMENT:
        payment.status = CANCELLED
    deposit.active_payment_id = None


async def student_name(db: AsyncSession, application_id) -> str | None:
    """The application's student for the receipt (AC5): the account's name, else the agency record's (a student with no login)."""
    return await db.scalar(
        select(func.coalesce(User.full_name, AgentStudent.full_name))
        .select_from(OverseasApplication)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .where(OverseasApplication.id == application_id)
    )


async def on_payment_paid(db: AsyncSession, payment: Payment, *, source: str, provider_amount: int | None = None) -> None:
    """§4.5 (AC2): the paid hook's deposit step. The caller (`payments._mark_paid`) has just moved this payment into `paid` under
    `_lock_for_update`, which locked the deposit first, so this runs once per payment. The deposit is paid only by its open checkout
    for the stored amount; any other captured payment (a superseded order, a second payment, a mismatched amount) stays a paid
    payment and is flagged for a manual refund."""
    deposit = await db.get(ApplicationDeposit, payment.reference_id, populate_existing=True)
    if deposit is None:
        logger.warning("agent_deposit_payment_without_deposit", extra={"extra_fields": {"payment_id": str(payment.id)}})
        return
    reason = None
    if deposit.status != "pending" or deposit.active_payment_id != payment.id:
        reason = "not_the_open_checkout"
    elif provider_amount is not None and provider_amount != int(round(deposit.amount * 100)):
        reason = "amount_mismatch"
    if reason:
        db.add(
            AuditLog(
                user_id=None, action="overseas.deposit.unlinked_payment", entity_type="application_deposit", entity_id=str(deposit.id), metadata_json={"payment_id": str(payment.id), "reason": reason}
            )
        )
        logger.warning("agent_deposit_unlinked_payment", extra={"extra_fields": {"deposit_id": str(deposit.id), "payment_id": str(payment.id), "reason": reason, "source": source}})
        return
    deposit.status = "paid"
    deposit.paid_payment_id = payment.id
    deposit.paid_at = datetime.now(UTC)
    deposit.active_payment_id = None
    db.add(
        AuditLog(
            user_id=payment.user_id,
            action="overseas.application.deposit_paid",
            entity_type="overseas_application",
            entity_id=str(deposit.application_id),
            metadata_json={"payment_id": str(payment.id), "source": source},
        )
    )
    logger.info("agent_deposit_paid", extra={"extra_fields": {"deposit_id": str(deposit.id), "payment_id": str(payment.id), "application_id": str(deposit.application_id), "source": source}})


async def receipt_student(db: AsyncSession, payment: Payment) -> str | None:
    """The receipt's student line (AC5): only for an agent-deposit payment, else None (every other receipt is unchanged)."""
    if payment.reference_type != REFERENCE_TYPE or payment.reference_id is None:
        return None
    application_id = await db.scalar(select(ApplicationDeposit.application_id).where(ApplicationDeposit.id == payment.reference_id))
    return None if application_id is None else await student_name(db, application_id)


Student = aliased(User)
Payer = aliased(User)


async def admin_rows(db: AsyncSession, *filters, limit: int, offset: int) -> list[dict]:
    """Overseas Admin's Agent deposits rows (§4.7), newest paid first. Agency: the organisation of the member who created the
    application; student: the account's name, else the agency record's."""
    rows = (
        await db.execute(
            select(ApplicationDeposit, AgentOrg.name, func.coalesce(Student.full_name, AgentStudent.full_name), University.name, Payer.full_name)
            .join(OverseasApplication, OverseasApplication.id == ApplicationDeposit.application_id)
            .join(University, University.id == OverseasApplication.university_id)
            .outerjoin(Student, Student.id == OverseasApplication.student_id)
            .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
            .outerjoin(AgentOrgMember, AgentOrgMember.user_id == OverseasApplication.agent_id)
            .outerjoin(AgentOrg, AgentOrg.id == AgentOrgMember.org_id)
            .outerjoin(Payment, Payment.id == ApplicationDeposit.paid_payment_id)
            .outerjoin(Payer, Payer.id == Payment.user_id)
            .where(*filters)
            .order_by(ApplicationDeposit.paid_at.desc().nulls_last(), ApplicationDeposit.created_at.desc(), ApplicationDeposit.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
    ).all()
    unlinked: dict = {}
    if rows:
        ids = [row[0].id for row in rows]
        unlinked = dict(
            (
                await db.execute(
                    select(Payment.reference_id, func.count())
                    .join(ApplicationDeposit, ApplicationDeposit.id == Payment.reference_id)
                    .where(
                        Payment.reference_type == REFERENCE_TYPE,
                        Payment.reference_id.in_(ids),
                        Payment.status.in_(("paid", "succeeded")),
                        Payment.id.is_distinct_from(ApplicationDeposit.paid_payment_id),
                    )
                    .group_by(Payment.reference_id)
                )
            ).all()
        )
    return [
        {
            "id": d.id,
            "application_id": d.application_id,
            "agency": agency,
            "student": student or "Unnamed student",
            "university": university,
            "amount": None if d.amount is None else f"{d.amount:.2f}",
            "currency": d.currency,
            "status": d.status,
            "due_date": d.due_date,
            "paid_at": d.paid_at,
            "paid_by": paid_by,
            "remitted_at": d.remitted_at,
            "remittance_reference": d.remittance_reference,
            "refunded_at": d.refunded_at,
            "refund_amount": None if d.refund_amount is None else f"{d.refund_amount:.2f}",
            "refund_reason": d.refund_reason,
            "unlinked_paid_payments": unlinked.get(d.id, 0),
        }
        for d, agency, student, university, paid_by in rows
    ]


async def deposit_view(db: AsyncSession, deposit: ApplicationDeposit | None) -> dict | None:
    """The detail's `deposit` (§4.3): no payment, order or key ids."""
    if deposit is None:
        return None
    paid_by = receipt = None
    if deposit.paid_payment_id is not None:
        paid_by = await db.scalar(select(User.full_name).join(Payment, Payment.user_id == User.id).where(Payment.id == deposit.paid_payment_id))
        receipt = await db.scalar(select(Receipt.id).where(Receipt.payment_id == deposit.paid_payment_id))
    in_progress = deposit.active_payment_id is not None and await db.scalar(select(Payment.status).where(Payment.id == deposit.active_payment_id)) == OPEN_PAYMENT
    return {
        "id": deposit.id,
        "required": deposit.required,
        "amount": None if deposit.amount is None else f"{deposit.amount:.2f}",
        "currency": deposit.currency,
        "due_date": deposit.due_date,
        "status": deposit.status,
        "paid_at": deposit.paid_at,
        "paid_by": paid_by,
        "receipt_available": receipt is not None,
        "remitted_at": deposit.remitted_at,
        "remittance_reference": deposit.remittance_reference,
        "refunded_at": deposit.refunded_at,
        "refund_amount": None if deposit.refund_amount is None else f"{deposit.refund_amount:.2f}",
        "refund_reason": deposit.refund_reason,
        "checkout_in_progress": bool(in_progress),
    }
