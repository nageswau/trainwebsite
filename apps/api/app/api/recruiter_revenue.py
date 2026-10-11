"""rec-031 (DEC-SCOPE-175, spec §3): revenue per requirement and company, the fee override, invoices, payments and the receivables list.

Role first (403: RV10), then the requirement's scope (404, rec-007 `load_scoped`). Every write is one transaction -- the row lock, the rules
(422 on a field / coded 409), the write, an audit row (ids and amounts only), one commit here, then the log line. Track only (R9)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RecruiterInvoice, RecruiterPayment, User
from app.schemas import RecCompanyRevenue, RecFeeOverride, RecInvoiceCancel, RecInvoiceCreate, RecInvoiceEnvelope, RecInvoicePage, RecPaymentCreate, RecRequirementRevenue
from app.services import recruiter_companies as companies
from app.services import recruiter_revenue as svc
from app.services.recruiter_requirements import ist_today

router = APIRouter(prefix="/recruiter", tags=["recruiter-revenue"])


@router.get("/requirements/{requirement_id}/revenue", response_model=RecRequirementRevenue)
async def requirement_revenue(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.requirement_revenue(db, user, await svc.load_job(db, user, requirement_id))


@router.put("/requirements/{requirement_id}/fee", response_model=RecRequirementRevenue)
async def set_fee(requirement_id: UUID, payload: RecFeeOverride, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """RV1: the requirement's own fee per hire, or both null to fall back to the contract. Nothing changed = nothing recorded."""
    job = await svc.load_job(db, user, requirement_id, lock=True)
    svc.require_fee_setter(user)
    svc.check_fee(payload.fee_basis, payload.fee_value)
    before = {"basis": job.fee_basis, "value": str(svc.money(job.fee_value))} if job.fee_basis else None
    after = {"basis": payload.fee_basis, "value": str(svc.money(payload.fee_value))} if payload.fee_basis else None
    if before != after:
        job.fee_basis, job.fee_value = payload.fee_basis, svc.money(payload.fee_value) if payload.fee_basis else None
        svc.audit(db, user, "fee_set", "job", job.id, {"from": before, "to": after})
        await db.commit()
        await db.refresh(job)
        svc.log("recruiter_revenue_fee_set", user, job_id=job.id)
    return await svc.requirement_revenue(db, user, job)


@router.post("/invoices", status_code=201, response_model=RecInvoiceEnvelope)
async def create_invoice(payload: RecInvoiceCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """RV6. The number is unique ignoring case; the unique index is the backstop for two people typing it at once."""
    job = await svc.load_job(db, user, payload.requirement_id)
    svc.check_invoice_dates(payload.invoice_date, payload.due_date, ist_today())
    if await svc.number_taken(db, payload.invoice_number):
        raise HTTPException(409, svc.NUMBER_TAKEN)
    invoice = RecruiterInvoice(
        job_id=job.id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        amount=svc.money(payload.amount),
        note=payload.note,
        created_by_user_id=user.id,
    )
    db.add(invoice)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, svc.NUMBER_TAKEN) from None
    svc.audit(db, user, "invoice_created", "recruiter_invoice", invoice.id, {"job_id": str(job.id), "amount": str(invoice.amount)})
    await db.commit()
    await db.refresh(invoice)
    svc.log("recruiter_revenue_invoice_created", user, job_id=job.id, invoice_id=invoice.id)
    return {"invoice": await svc.invoice_out(db, user, invoice)}


@router.post("/invoices/{invoice_id}/payments", status_code=201, response_model=RecInvoiceEnvelope)
async def record_payment(invoice_id: UUID, payload: RecPaymentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """RV7 / AC2: under the invoice lock, so two payments at once can't together pass the invoice amount."""
    invoice = await svc.load_invoice(db, user, invoice_id, lock=True)
    if invoice.cancelled_at is not None:
        raise HTTPException(409, svc.CANCELLED)
    amount = svc.money(payload.amount)
    svc.check_payment(invoice, payload.received_on, amount, await svc.received_total(db, invoice.id), ist_today())
    payment = RecruiterPayment(invoice_id=invoice.id, received_on=payload.received_on, amount=amount, reference=payload.reference, created_by_user_id=user.id)
    db.add(payment)
    await db.flush()
    svc.audit(db, user, "payment_recorded", "recruiter_invoice", invoice.id, {"job_id": str(invoice.job_id), "payment_id": str(payment.id), "amount": str(amount)})
    await db.commit()
    await db.refresh(invoice)
    svc.log("recruiter_revenue_payment_recorded", user, invoice_id=invoice.id, payment_id=payment.id)
    return {"invoice": await svc.invoice_out(db, user, invoice)}


@router.post("/invoices/{invoice_id}/cancel", response_model=RecInvoiceEnvelope)
async def cancel_invoice(invoice_id: UUID, payload: RecInvoiceCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """RV8: an unpaid invoice only; its number stays used."""
    invoice = await svc.load_invoice(db, user, invoice_id, lock=True)
    if invoice.cancelled_at is not None:
        raise HTTPException(409, svc.CANCELLED)
    if await svc.received_total(db, invoice.id) > 0:
        raise HTTPException(409, svc.HAS_PAYMENTS)
    invoice.cancelled_at, invoice.cancelled_by_user_id, invoice.cancel_reason = svc.now(), user.id, payload.reason
    svc.audit(db, user, "invoice_cancelled", "recruiter_invoice", invoice.id, {"job_id": str(invoice.job_id), "amount": str(svc.money(invoice.amount))})
    await db.commit()
    await db.refresh(invoice)
    svc.log("recruiter_revenue_invoice_cancelled", user, invoice_id=invoice.id)
    return {"invoice": await svc.invoice_out(db, user, invoice)}


@router.get("/companies/{company_id}/revenue", response_model=RecCompanyRevenue)
async def company_revenue(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    return await svc.company_revenue(db, user, await companies.load_scoped(db, user, company_id))


@router.get("/invoices", response_model=RecInvoicePage)
async def list_invoices(
    view: Literal[svc.VIEWS] = "outstanding",  # type: ignore[valid-type]
    company_id: UUID | None = Query(None),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc.require_reader(user)
    return await svc.invoice_page(db, user, view, company_id, limit, offset)
