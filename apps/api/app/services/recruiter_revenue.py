"""rec-031 (DEC-SCOPE-176, spec §1-§3): revenue / commercial tracking per requirement, track only (R9: no invoice PDF, no GST, no sync).

Functions only; nothing here commits -- the route owns the transaction. Every requirement resolves through rec-007's `load_scoped` and every
invoice through its requirement's scope, so an id outside the caller's scope is the same 404 as a missing one. The role gate (RV10) runs
first: the BDM reads the requirement (R10) but never its revenue (403). Figures are computed on read, never stored:
- selected (RV5): applications that ever entered Selected, or are Selected / Joined now;
- joined (RV4, AC3): applications at Joined -- the rec-007 `joined_count` rule;
- fee per hire (RV1/RV2): the requirement override, else the company's current contract; a percentage is priced per hire on the offer's
  INR compensation, and a hire without one is unpriced;
- invoiced / received / outstanding (AC1): open invoices only; a cancelled invoice counts nowhere (RV8)."""

import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Candidate,
    Company,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    RecruiterContract,
    RecruiterInvoice,
    RecruiterPayment,
    User,
)
from app.services import recruiter_contracts as contracts
from app.services import recruiter_requirements as requirements
from app.services.interviews import field_error
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.recruiter_companies import person

logger = logging.getLogger("app.recruiter")

READERS = (ROLE, MANAGER_ROLE, "super_admin")  # RV10: they also record invoices and payments
FEE_SETTERS = (MANAGER_ROLE, "super_admin")  # RV10: the override is a pricing exception to the contract
NOT_READER = "Revenue is visible to recruiters and their managers"
NOT_FEE_SETTER = "Only a manager can change the fee for a requirement"
INVOICE_NOT_FOUND = "Invoice not found"
NUMBER_TAKEN = {"message": "This invoice number is already used", "code": "invoice_number_taken"}
CANCELLED = {"message": "This invoice is cancelled", "code": "invoice_cancelled"}
HAS_PAYMENTS = {"message": "An invoice with payments can't be cancelled", "code": "invoice_has_payments"}
PAYMENT_LABELS = {"unpaid": "Unpaid", "part_paid": "Part paid", "paid": "Paid", "cancelled": "Cancelled"}
VIEWS = ("outstanding", "overdue", "paid", "cancelled")
SELECTED, JOINED = "selected", requirements.HIRED_APPLICATION_STATUSES
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def inr(value: Decimal) -> str:
    """₹1,50,000.00 (Indian grouping) for messages."""
    whole, cents = f"{money(value):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        head, groups = head[:-2], [head[-2:], *groups]
    return "₹" + ",".join([g for g in [head, *groups] if g] + [tail]) + f".{cents}"


def now() -> datetime:
    return contracts.now()


# --- roles and scope -------------------------------------------------------------------------------------------------------------
def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, NOT_READER)


def require_fee_setter(user: User) -> None:
    if user.role not in FEE_SETTERS:
        logger.warning("recruiter_revenue_fee_refused", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role}})
        raise HTTPException(403, NOT_FEE_SETTER)


async def load_job(db: AsyncSession, user: User, job_id: UUID, *, lock: bool = False) -> Job:
    require_reader(user)
    return await requirements.load_scoped(db, user, job_id, lock=lock)


async def load_invoice(db: AsyncSession, user: User, invoice_id: UUID, *, lock: bool = False) -> RecruiterInvoice:
    """With `lock`, the invoice row is locked by id first and scope is checked in a fresh statement (the rec-003 rule)."""
    require_reader(user)
    stmt = select(RecruiterInvoice).join(Job, Job.id == RecruiterInvoice.job_id).where(RecruiterInvoice.id == invoice_id, *await requirements.caller_scope(db, user))
    if lock:
        await db.execute(select(RecruiterInvoice.id).where(RecruiterInvoice.id == invoice_id).with_for_update())
        stmt = stmt.execution_options(populate_existing=True)
    invoice = await db.scalar(stmt)
    if invoice is None:
        raise HTTPException(404, INVOICE_NOT_FOUND)
    return invoice


# --- rules -----------------------------------------------------------------------------------------------------------------------
def check_fee(basis: str | None, value: Decimal | None) -> None:
    if basis is None and value is not None:
        raise field_error("fee_basis", contracts.FEE_BASIS_REQUIRED)
    if basis is not None and value is None:
        raise field_error("fee_value", contracts.FEE_VALUE_REQUIRED)
    if basis == "percent_of_ctc" and value is not None and value > 100:
        raise field_error("fee_value", contracts.FEE_PERCENT_MAX, str(value))


def check_invoice_dates(invoice_date: date, due_date: date, today: date) -> None:
    if invoice_date > today:
        raise field_error("invoice_date", "The invoice date can't be in the future", invoice_date.isoformat())
    if due_date < invoice_date:
        raise field_error("due_date", "The due date can't be before the invoice date", due_date.isoformat())


def check_payment(invoice: RecruiterInvoice, received_on: date, amount: Decimal, received: Decimal, today: date) -> None:
    if received_on > today:
        raise field_error("received_on", "The received date can't be in the future", received_on.isoformat())
    if received_on < invoice.invoice_date:
        raise field_error("received_on", "The received date can't be before the invoice date", received_on.isoformat())
    outstanding = money(invoice.amount) - received
    if amount > outstanding:  # AC2 (RV7)
        raise field_error("amount", f"This payment is more than the {inr(outstanding)} outstanding", str(amount))


async def number_taken(db: AsyncSession, number: str) -> bool:
    return bool(await db.scalar(select(RecruiterInvoice.id).where(func.lower(RecruiterInvoice.invoice_number) == number.lower())))


async def received_total(db: AsyncSession, invoice_id: UUID) -> Decimal:
    return money(await db.scalar(select(func.sum(RecruiterPayment.amount)).where(RecruiterPayment.invoice_id == invoice_id)))


# --- figures -----------------------------------------------------------------------------------------------------------------------
def _fee_value(basis: str | None, value) -> dict:
    return {"basis": basis, "value": money(value)}


async def _contract_fees(db: AsyncSession, company_ids: set[UUID]) -> dict[UUID, RecruiterContract]:
    rows = await db.scalars(select(RecruiterContract).where(RecruiterContract.company_id.in_(company_ids), RecruiterContract.is_current, RecruiterContract.fee_basis.is_not(None)))
    return {c.company_id: c for c in rows}


def _fee(job: Job, contract: RecruiterContract | None, on: date) -> dict:
    """RV1: the override wins, else the current contract's fee, else none."""
    override = _fee_value(job.fee_basis, job.fee_value) if job.fee_basis else None
    if override:
        return {**override, "source": "requirement", "contract_status_label": None, "override": override}
    if contract is not None:
        label = contracts.LABELS[contracts.effective_status(contract, on)]
        return {**_fee_value(contract.fee_basis, contract.fee_value), "source": "contract", "contract_status_label": label, "override": None}
    return {"basis": None, "value": None, "source": None, "contract_status_label": None, "override": None}


def _hire_fee(fee: dict, compensation, currency: str | None) -> Decimal | None:
    """RV2: a percentage needs the offer's INR compensation; without it the hire is unpriced."""
    if fee["basis"] == "fixed":
        return fee["value"]
    if fee["basis"] == "percent_of_ctc" and compensation is not None and currency == "INR":
        return money(Decimal(compensation) * fee["value"] / 100)
    return None


async def _selected(db: AsyncSession, job_ids: list[UUID]) -> dict[UUID, int]:
    entered = exists().where(JobApplicationStatusHistory.application_id == JobApplication.id, JobApplicationStatusHistory.to_status == SELECTED)
    rows = await db.execute(
        select(JobApplication.job_id, func.count()).where(JobApplication.job_id.in_(job_ids), or_(JobApplication.status.in_((SELECTED, *JOINED)), entered)).group_by(JobApplication.job_id)
    )
    return dict(rows.all())


async def _hires(db: AsyncSession, job_ids: list[UUID]) -> dict[UUID, list]:
    rows = await db.execute(
        select(JobApplication.job_id, JobApplication.id, Candidate.id, Candidate.candidate_code, Candidate.name, JobOffer.actual_joining_date, JobOffer.compensation, JobOffer.currency)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .outerjoin(JobOffer, JobOffer.application_id == JobApplication.id)
        .where(JobApplication.job_id.in_(job_ids), JobApplication.status.in_(JOINED))
        .order_by(JobOffer.actual_joining_date.desc().nulls_last(), Candidate.candidate_code)
    )
    by_job = defaultdict(list)
    for row in rows.all():
        by_job[row[0]].append(row[1:])
    return by_job


async def _money_by_job(db: AsyncSession, job_ids: list[UUID]) -> tuple[dict, dict]:
    """Open invoices only (RV8): Σ amount and Σ payments per requirement."""
    open_ = and_(RecruiterInvoice.job_id.in_(job_ids), RecruiterInvoice.cancelled_at.is_(None))
    invoiced = dict((await db.execute(select(RecruiterInvoice.job_id, func.sum(RecruiterInvoice.amount)).where(open_).group_by(RecruiterInvoice.job_id))).all())
    received = dict(
        (
            await db.execute(
                select(RecruiterInvoice.job_id, func.sum(RecruiterPayment.amount))
                .join(RecruiterPayment, RecruiterPayment.invoice_id == RecruiterInvoice.id)
                .where(open_)
                .group_by(RecruiterInvoice.job_id)
            )
        ).all()
    )
    return invoiced, received


async def figures(db: AsyncSession, jobs: list[Job], on: date) -> dict[UUID, dict]:
    """The §23 figures of each requirement, in a fixed number of queries whatever the count."""
    if not jobs:
        return {}
    ids = [j.id for j in jobs]
    selected, hires, (invoiced, received) = await _selected(db, ids), await _hires(db, ids), await _money_by_job(db, ids)
    fees = await _contract_fees(db, {j.company_id for j in jobs})
    out = {}
    for job in jobs:
        fee = _fee(job, fees.get(job.company_id), on)
        rows = [
            {"application_id": app_id, "candidate": {"id": cid, "code": code, "name": name}, "joined_on": joined_on, "fee": _hire_fee(fee, compensation, currency) if fee["basis"] else None}
            for app_id, cid, code, name, joined_on, compensation, currency in hires.get(job.id, [])
        ]
        priced = [r["fee"] for r in rows if r["fee"] is not None]
        inv, rec = money(invoiced.get(job.id)), money(received.get(job.id))
        expected = money(sum(priced, ZERO)) if fee["basis"] else None
        out[job.id] = {
            "selected": selected.get(job.id, 0),
            "joined": len(rows),
            "fee": fee,
            "hires": rows,
            "expected_revenue": expected,
            "unpriced_hires": len(rows) - len(priced) if fee["basis"] else 0,
            "invoiced": inv,
            "received": rec,
            "outstanding": inv - rec,
            "over_invoiced": inv > (expected or ZERO),  # RV9: e.g. a Did Not Join after invoicing
        }
    return out


def _requirement_ref(job: Job) -> dict:
    return {"id": job.id, "code": job.requirement_code, "title": job.title}


def _company_ref(company: Company) -> dict:
    return {"id": company.id, "code": company.company_code, "name": company.name}


# --- invoices out ------------------------------------------------------------------------------------------------------------------
def payment_status(invoice: RecruiterInvoice, received: Decimal) -> str:
    if invoice.cancelled_at is not None:
        return "cancelled"
    if received >= money(invoice.amount):
        return "paid"
    return "part_paid" if received > 0 else "unpaid"


async def invoices_out(db: AsyncSession, user: User, invoices: list[RecruiterInvoice], today: date) -> list[dict]:
    """Payments, people, requirement and company for a page of invoices, in four queries."""
    if not invoices:
        return []
    ids = [i.id for i in invoices]
    payments = defaultdict(list)
    for p in await db.scalars(select(RecruiterPayment).where(RecruiterPayment.invoice_id.in_(ids)).order_by(RecruiterPayment.received_on, RecruiterPayment.created_at)):
        payments[p.invoice_id].append(p)
    jobs = {j.id: j for j in await db.scalars(select(Job).where(Job.id.in_({i.job_id for i in invoices})))}
    companies = {c.id: c for c in await db.scalars(select(Company).where(Company.id.in_({j.company_id for j in jobs.values()})))}
    people_ids = {i.created_by_user_id for i in invoices} | {p.created_by_user_id for ps in payments.values() for p in ps}
    people = {u.id: u for u in await db.scalars(select(User).where(User.id.in_(people_ids)))}
    writer = user.role in READERS
    out = []
    for i in invoices:
        received = money(sum((p.amount for p in payments[i.id]), ZERO))
        status = payment_status(i, received)
        outstanding = ZERO if status == "cancelled" else money(i.amount) - received
        job = jobs[i.job_id]
        out.append(
            {
                "id": i.id,
                "invoice_number": i.invoice_number,
                "invoice_date": i.invoice_date,
                "due_date": i.due_date,
                "amount": money(i.amount),
                "note": i.note,
                "received": received,
                "outstanding": outstanding,
                "payment_status": status,
                "payment_status_label": PAYMENT_LABELS[status],
                "overdue": outstanding > 0 and i.due_date < today,
                "cancelled_at": i.cancelled_at,
                "cancel_reason": i.cancel_reason,
                "requirement": _requirement_ref(job),
                "company": _company_ref(companies[job.company_id]),
                "created_by": person(people[i.created_by_user_id]),
                "payments": [
                    {"id": p.id, "received_on": p.received_on, "amount": money(p.amount), "reference": p.reference, "created_by": person(people[p.created_by_user_id]), "created_at": p.created_at}
                    for p in payments[i.id]
                ],
                "permissions": {"can_pay": writer and outstanding > 0, "can_cancel": writer and status == "unpaid"},
                "created_at": i.created_at,
            }
        )
    return out


async def invoice_out(db: AsyncSession, user: User, invoice: RecruiterInvoice) -> dict:
    return (await invoices_out(db, user, [invoice], requirements.ist_today()))[0]


async def requirement_revenue(db: AsyncSession, user: User, job: Job) -> dict:
    today = requirements.ist_today()
    company = (await db.scalars(select(Company).where(Company.id == job.company_id))).one()
    figures_ = (await figures(db, [job], today))[job.id]
    rows = list(await db.scalars(select(RecruiterInvoice).where(RecruiterInvoice.job_id == job.id).order_by(RecruiterInvoice.invoice_date.desc(), RecruiterInvoice.created_at.desc())))
    return {
        "requirement": _requirement_ref(job),
        "company": _company_ref(company),
        **figures_,
        "invoices": await invoices_out(db, user, rows, today),
        "permissions": {"can_invoice": user.role in READERS, "can_set_fee": user.role in FEE_SETTERS},
    }


async def company_revenue(db: AsyncSession, user: User, company: Company) -> dict:
    """The company's requirements in the caller's requirement scope (a recruiter may see the company but not every requirement)."""
    today = requirements.ist_today()
    jobs = list(await db.scalars(select(Job).where(Job.company_id == company.id, *await requirements.caller_scope(db, user)).order_by(Job.created_at.desc())))
    by_job = await figures(db, jobs, today)
    rows = [
        {
            "requirement": _requirement_ref(j),
            "status_label": requirements.STATUS_LABELS.get(j.status, j.status),
            **{k: by_job[j.id][k] for k in ("selected", "joined", "fee", "expected_revenue", "invoiced", "received", "outstanding")},
        }
        for j in jobs
    ]
    totals = {k: sum((r[k] for r in rows), 0) for k in ("selected", "joined")}
    totals |= {k: money(sum((r[k] or ZERO for r in rows), ZERO)) for k in ("expected_revenue", "invoiced", "received", "outstanding")}
    return {"requirements": rows, "totals": totals}


# --- the receivables list ----------------------------------------------------------------------------------------------------------
async def invoice_page(db: AsyncSession, user: User, view: str, company_id: UUID | None, limit: int, offset: int) -> dict:
    today = requirements.ist_today()
    received = select(func.coalesce(func.sum(RecruiterPayment.amount), 0)).where(RecruiterPayment.invoice_id == RecruiterInvoice.id).correlate(RecruiterInvoice).scalar_subquery()
    live = RecruiterInvoice.cancelled_at.is_(None)
    owing = and_(live, received < RecruiterInvoice.amount)
    conditions = {
        "outstanding": owing,
        "overdue": and_(owing, RecruiterInvoice.due_date < today),
        "paid": and_(live, received >= RecruiterInvoice.amount),
        "cancelled": RecruiterInvoice.cancelled_at.is_not(None),
    }
    soonest_due = (RecruiterInvoice.due_date, RecruiterInvoice.invoice_date, RecruiterInvoice.created_at)
    order = {
        "outstanding": soonest_due,
        "overdue": soonest_due,
        "paid": (RecruiterInvoice.invoice_date.desc(), RecruiterInvoice.created_at.desc()),
        "cancelled": (RecruiterInvoice.cancelled_at.desc(),),
    }
    scope = [*await requirements.caller_scope(db, user), *([Job.company_id == company_id] if company_id else [])]
    base = select(RecruiterInvoice).join(Job, Job.id == RecruiterInvoice.job_id).where(*scope)
    summary = (
        await db.execute(
            select(*(func.count().filter(c) for c in conditions.values()), func.coalesce(func.sum(RecruiterInvoice.amount - received).filter(owing), 0))
            .select_from(RecruiterInvoice)
            .join(Job, Job.id == RecruiterInvoice.job_id)
            .where(*scope)
        )
    ).one()
    counts = dict(zip(VIEWS, summary[:4], strict=True))
    rows = list(await db.scalars(base.where(conditions[view]).order_by(*order[view], RecruiterInvoice.id).limit(limit).offset(offset)))
    return {"items": await invoices_out(db, user, rows, today), "total": counts[view], "limit": limit, "offset": offset, "counts": counts, "outstanding_total": money(summary[4])}


# --- audit and log -----------------------------------------------------------------------------------------------------------------
def audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id: UUID, metadata: dict) -> None:
    """Same transaction as the write (fail closed); ids and amounts only -- never notes, references, reasons or names."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_revenue.{action}", entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


def log(event: str, user: User, **ids) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), **{k: str(v) for k, v in ids.items()}}})
