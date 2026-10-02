"""AGN-011 / DEC-SCOPE-057 -- the deposit on an agency application, paid through EduSphere Razorpay.

Functions only (the services/agent_applications.py shape): nothing here commits -- the routers and the payments paid hook lock, write,
audit and commit. Lock order everywhere: organisation, application, deposit, then payment (the paid hook takes deposit then payment).
Spec: docs/superpowers/specs/2026-10-02-agn-011-deposit-collection-design.md.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AgentStudent, ApplicationDeposit, OverseasApplication, Payment, Receipt, User

REFERENCE_TYPE = "agent_deposit"
PAID_STATES = ("paid", "remitted", "refunded")
OPEN_PAYMENT = "pending"
CANCELLED = "cancelled"

PAID_LOCKED = "This deposit is already paid and can no longer be changed"


def payment_available() -> bool:
    """AC6: both keys are needed to open a Razorpay order (`PaymentService.create_checkout`)."""
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


async def deposit_for(db: AsyncSession, application_id, *, lock: bool = False) -> ApplicationDeposit | None:
    stmt = select(ApplicationDeposit).where(ApplicationDeposit.application_id == application_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def locked_payment(db: AsyncSession, payment_id) -> Payment | None:
    return await db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update().execution_options(populate_existing=True))


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


async def receipt_student(db: AsyncSession, payment: Payment) -> str | None:
    """The receipt's student line (AC5): only for an agent-deposit payment, else None (every other receipt is unchanged)."""
    if payment.reference_type != REFERENCE_TYPE or payment.reference_id is None:
        return None
    application_id = await db.scalar(select(ApplicationDeposit.application_id).where(ApplicationDeposit.id == payment.reference_id))
    return None if application_id is None else await student_name(db, application_id)


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
