"""pob-012 (DEC-SCOPE-433): vendor payables and receivables (W2/W3) and vendor performance (W6/W7). Track only, like rec-031.

Functions only; nothing here commits -- the route owns the transaction. The `commercials.vendor` grant is checked first (W4: view to read,
edit to write), then the vendor resolves through the company scope (`load_scoped`), so an id outside it is the same 404 as a missing one.
The performance figures are computed on read from the rows the drill-down shows (W7), so every figure ties out to its drill-down."""

import logging
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Candidate,
    Company,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    ProfileShare,
    ProfileShareItem,
    User,
    VendorBill,
    VendorBillPayment,
)
from app.services import recruiter_companies as companies
from app.services import recruiter_contracts as contracts
from app.services import recruiter_requirements as requirements
from app.services.interviews import field_error
from app.services.recruiter_companies import person
from app.services.recruiter_revenue import PAYMENT_LABELS, ZERO, inr, money, now

logger = logging.getLogger("app.recruiter")

KINDS = ("payable", "receivable")
KIND_LABELS = {"payable": "We owe the vendor", "receivable": "The vendor owes us"}
NOT_A_VENDOR = "This company is not a vendor"
BILL_NOT_FOUND = "Bill not found"
NUMBER_TAKEN = {"message": "This vendor already has a bill with this number", "code": "bill_number_taken"}
CANCELLED = {"message": "This bill is cancelled", "code": "bill_cancelled"}
HAS_PAYMENTS = {"message": "A bill with payments can't be cancelled", "code": "bill_has_payments"}
WRONG_REQUIREMENT = "Choose a requirement that came through this vendor"
INTERVIEWED = ("interview", "selected", *requirements.HIRED_APPLICATION_STATUSES)
PLACED = ("selected", *requirements.HIRED_APPLICATION_STATUSES)
TENTH = Decimal("0.1")


# --- access ---------------------------------------------------------------------------------------------------------------------
async def require_grant(db: AsyncSession, user: User, route: str, *, edit: bool = False) -> None:
    await contracts.require_terms(db, user, route, edit=edit, party=contracts.VENDOR)


async def can_edit(db: AsyncSession, user: User) -> bool:
    return (await contracts.commercial_access(db, user, contracts.VENDOR))[1]


async def load_vendor(db: AsyncSession, user: User, company_id: UUID, route: str, *, edit: bool = False) -> Company:
    await require_grant(db, user, route, edit=edit)
    company = await companies.load_scoped(db, user, company_id)
    if not companies.is_vendor(company):
        raise HTTPException(422, NOT_A_VENDOR)
    return company


async def load_bill(db: AsyncSession, user: User, bill_id: UUID, route: str) -> VendorBill:
    """A write: the bill row is locked by id first and the scope is checked in a fresh statement (the rec-003 rule)."""
    await require_grant(db, user, route, edit=True)
    await db.execute(select(VendorBill.id).where(VendorBill.id == bill_id).with_for_update())
    stmt = select(VendorBill).join(Company, Company.id == VendorBill.company_id).where(VendorBill.id == bill_id, *await companies.caller_scope(db, user))
    bill = await db.scalar(stmt.execution_options(populate_existing=True))
    if bill is None:
        raise HTTPException(404, BILL_NOT_FOUND)
    return bill


# --- rules ----------------------------------------------------------------------------------------------------------------------
def check_dates(bill_date: date, due_date: date, today: date) -> None:
    if bill_date > today:
        raise field_error("bill_date", "The bill date can't be in the future", bill_date.isoformat())
    if due_date < bill_date:
        raise field_error("due_date", "The due date can't be before the bill date", due_date.isoformat())


def check_payment(bill: VendorBill, paid_on: date, amount: Decimal, paid: Decimal, today: date) -> None:
    if paid_on > today:
        raise field_error("paid_on", "The payment date can't be in the future", paid_on.isoformat())
    if paid_on < bill.bill_date:
        raise field_error("paid_on", "The payment date can't be before the bill date", paid_on.isoformat())
    outstanding = money(bill.amount) - paid
    if amount > outstanding:
        raise field_error("amount", f"This payment is more than the {inr(outstanding)} outstanding", str(amount))


async def check_requirement(db: AsyncSession, user: User, vendor: Company, job_id: UUID | None) -> Job | None:
    if job_id is None:
        return None
    job = await db.scalar(select(Job).where(Job.id == job_id, *await requirements.caller_scope(db, user)))
    if job is None or job.via_vendor_id != vendor.id:
        raise field_error("requirement_id", WRONG_REQUIREMENT, str(job_id))
    return job


async def number_taken(db: AsyncSession, vendor_id: UUID, number: str) -> bool:
    return bool(await db.scalar(select(VendorBill.id).where(VendorBill.company_id == vendor_id, func.lower(VendorBill.bill_number) == number.lower())))


async def paid_total(db: AsyncSession, bill_id: UUID) -> Decimal:
    return money(await db.scalar(select(func.sum(VendorBillPayment.amount)).where(VendorBillPayment.bill_id == bill_id)))


def payment_status(bill: VendorBill, paid: Decimal) -> str:
    if bill.cancelled_at is not None:
        return "cancelled"
    if paid >= money(bill.amount):
        return "paid"
    return "part_paid" if paid > 0 else "unpaid"


# --- writes (the route commits) -------------------------------------------------------------------------------------------------
async def add_bill(db: AsyncSession, user: User, vendor: Company, payload) -> VendorBill:
    """W2. An archived or merged vendor takes no new bill (409); the unique index backs the number check for two people at once."""
    if vendor.archived_at is not None or vendor.merged_into_id is not None:
        raise HTTPException(409, companies.STATE_REFUSALS["can_edit"])
    check_dates(payload.bill_date, payload.due_date, requirements.ist_today())
    job = await check_requirement(db, user, vendor, payload.requirement_id)
    if await number_taken(db, vendor.id, payload.bill_number):
        raise HTTPException(409, NUMBER_TAKEN)
    amount = money(payload.amount)
    bill = VendorBill(
        company_id=vendor.id, job_id=job.id if job else None, kind=payload.kind, bill_number=payload.bill_number, bill_date=payload.bill_date,
        due_date=payload.due_date, amount=amount, milestone=payload.milestone, note=payload.note, created_by_user_id=user.id,
    )  # fmt: skip
    db.add(bill)
    await db.flush()
    audit(db, user, "bill_created", bill, {"amount": str(amount)})
    return bill


async def add_payment(db: AsyncSession, user: User, bill: VendorBill, payload) -> VendorBillPayment:
    """W3: the route has locked the bill, so two payments at once can't together pass its amount."""
    if bill.cancelled_at is not None:
        raise HTTPException(409, CANCELLED)
    amount = money(payload.amount)
    check_payment(bill, payload.paid_on, amount, await paid_total(db, bill.id), requirements.ist_today())
    payment = VendorBillPayment(bill_id=bill.id, paid_on=payload.paid_on, amount=amount, reference=payload.reference, created_by_user_id=user.id)
    db.add(payment)
    await db.flush()
    audit(db, user, "payment_recorded", bill, {"payment_id": str(payment.id), "amount": str(amount)})
    return payment


async def cancel(db: AsyncSession, user: User, bill: VendorBill, reason: str) -> None:
    """W2 (rec-031 RV8): an unpaid bill only; its number stays used."""
    if bill.cancelled_at is not None:
        raise HTTPException(409, CANCELLED)
    if await paid_total(db, bill.id) > 0:
        raise HTTPException(409, HAS_PAYMENTS)
    bill.cancelled_at, bill.cancelled_by_user_id, bill.cancel_reason = now(), user.id, reason
    audit(db, user, "bill_cancelled", bill, {"amount": str(money(bill.amount))})


# --- bills out ------------------------------------------------------------------------------------------------------------------
def _requirement_ref(job: Job) -> dict:
    return {"id": job.id, "code": job.requirement_code, "title": job.title}


async def bills_out(db: AsyncSession, bills: list[VendorBill], editable: bool, today: date) -> list[dict]:
    """Payments, people and requirements for a list of bills, in three queries."""
    if not bills:
        return []
    payments = defaultdict(list)
    for p in await db.scalars(select(VendorBillPayment).where(VendorBillPayment.bill_id.in_([b.id for b in bills])).order_by(VendorBillPayment.paid_on, VendorBillPayment.created_at)):
        payments[p.bill_id].append(p)
    job_ids = {b.job_id for b in bills if b.job_id}
    jobs = {j.id: j for j in await db.scalars(select(Job).where(Job.id.in_(job_ids)))} if job_ids else {}
    people_ids = {b.created_by_user_id for b in bills} | {p.created_by_user_id for ps in payments.values() for p in ps}
    people = {u.id: u for u in await db.scalars(select(User).where(User.id.in_(people_ids)))}
    out = []
    for b in bills:
        paid = money(sum((p.amount for p in payments[b.id]), ZERO))
        status = payment_status(b, paid)
        outstanding = ZERO if status == "cancelled" else money(b.amount) - paid
        out.append(
            {
                "id": b.id,
                "kind": b.kind,
                "kind_label": KIND_LABELS[b.kind],
                "bill_number": b.bill_number,
                "bill_date": b.bill_date,
                "due_date": b.due_date,
                "amount": money(b.amount),
                "milestone": b.milestone,
                "note": b.note,
                "paid": paid,
                "outstanding": outstanding,
                "payment_status": status,
                "payment_status_label": PAYMENT_LABELS[status],
                "overdue": outstanding > 0 and b.due_date < today,
                "cancelled_at": b.cancelled_at,
                "cancel_reason": b.cancel_reason,
                "requirement": _requirement_ref(jobs[b.job_id]) if b.job_id in jobs else None,
                "created_by": person(people[b.created_by_user_id]),
                "payments": [
                    {"id": p.id, "paid_on": p.paid_on, "amount": money(p.amount), "reference": p.reference, "created_by": person(people[p.created_by_user_id]), "created_at": p.created_at}
                    for p in payments[b.id]
                ],
                "permissions": {"can_pay": editable and outstanding > 0, "can_cancel": editable and status == "unpaid"},
                "created_at": b.created_at,
            }
        )
    return out


async def bill_out(db: AsyncSession, user: User, bill: VendorBill) -> dict:
    return (await bills_out(db, [bill], await can_edit(db, user), requirements.ist_today()))[0]


async def money_totals(db: AsyncSession, vendor_ids: list[UUID]) -> dict[UUID, dict]:
    """W6 payment history per vendor and kind, open bills only: billed, paid, outstanding and the last payment date."""
    empty = {"billed": ZERO, "paid": ZERO, "outstanding": ZERO, "last_paid_on": None}
    out = {v: {k: dict(empty) for k in KINDS} for v in vendor_ids}
    if not vendor_ids:
        return out
    live = (VendorBill.company_id.in_(vendor_ids), VendorBill.cancelled_at.is_(None))
    for vendor_id, kind, billed in (await db.execute(select(VendorBill.company_id, VendorBill.kind, func.sum(VendorBill.amount)).where(*live).group_by(VendorBill.company_id, VendorBill.kind))).all():
        out[vendor_id][kind]["billed"] = money(billed)
    paid_rows = await db.execute(
        select(VendorBill.company_id, VendorBill.kind, func.sum(VendorBillPayment.amount), func.max(VendorBillPayment.paid_on))
        .join(VendorBillPayment, VendorBillPayment.bill_id == VendorBill.id)
        .where(*live)
        .group_by(VendorBill.company_id, VendorBill.kind)
    )
    for vendor_id, kind, paid, last in paid_rows.all():
        out[vendor_id][kind] |= {"paid": money(paid), "last_paid_on": last}
    for kinds in out.values():
        for totals in kinds.values():
            totals["outstanding"] = totals["billed"] - totals["paid"]
    return out


async def vendor_bills(db: AsyncSession, user: User, vendor: Company) -> dict:
    today, editable = requirements.ist_today(), await can_edit(db, user)
    rows = list(await db.scalars(select(VendorBill).where(VendorBill.company_id == vendor.id).order_by(VendorBill.bill_date.desc(), VendorBill.created_at.desc())))
    return {"items": await bills_out(db, rows, editable, today), "totals": (await money_totals(db, [vendor.id]))[vendor.id], "can_edit": editable and vendor.archived_at is None}


# --- performance (W6/W7) --------------------------------------------------------------------------------------------------------
def _rate(part: int, whole: int) -> Decimal | None:
    """A zero denominator is null ("—"), never 0% (the backlog's +/−/E)."""
    return (Decimal(part * 100) / whole).quantize(TENTH, rounding=ROUND_HALF_UP) if whole else None


def metrics(requirement_rows: list[dict], submission_rows: list[dict], payments: dict) -> dict:
    """Every figure is a count or an average over the drill-down rows passed in, so each ties out to them (W7)."""
    hours = [r["response_hours"] for r in requirement_rows if r["response_hours"] is not None]
    placed = sum(s["placed"] for s in submission_rows)
    interviewed, joined = sum(s["interviewed"] for s in submission_rows), sum(s["joined"] for s in submission_rows)
    return {
        "requirements": len(requirement_rows),
        "responded_requirements": len(hours),
        "avg_response_hours": (sum(hours, Decimal(0)) / len(hours)).quantize(TENTH, rounding=ROUND_HALF_UP) if hours else None,
        "submitted": len(submission_rows),
        "interviewed": interviewed,
        "placed": placed,
        "joined": joined,
        "interview_rate": _rate(interviewed, len(submission_rows)),
        "joining_rate": _rate(joined, placed),
        "payments": payments,
    }


async def _drill_down(db: AsyncSession, user: User, vendor_ids: list[UUID]) -> dict[UUID, tuple[list, list]]:
    """The requirements via each vendor in the caller's requirement scope, and the applications shared to that vendor on them, in four
    queries whatever the number of vendors."""
    out: dict[UUID, tuple[list, list]] = {v: ([], []) for v in vendor_ids}
    if not vendor_ids:
        return out
    jobs = list(await db.scalars(select(Job).where(Job.via_vendor_id.in_(vendor_ids), *await requirements.caller_scope(db, user)).order_by(Job.created_at.desc())))
    if not jobs:
        return out
    by_id = {j.id: j for j in jobs}
    to_vendor = (ProfileShare.recipient == "vendor", ProfileShare.job_id.in_(by_id), ProfileShare.company_id == Job.via_vendor_id)
    first_share = dict(
        (await db.execute(select(ProfileShare.job_id, func.min(ProfileShare.created_at)).join(Job, Job.id == ProfileShare.job_id).where(*to_vendor).group_by(ProfileShare.job_id))).all()
    )
    for job in jobs:
        first = first_share.get(job.id)
        hours = (Decimal((first - job.created_at).total_seconds()) / 3600).quantize(TENTH, rounding=ROUND_HALF_UP) if first else None
        out[job.via_vendor_id][0].append({"requirement": _requirement_ref(job), "created_at": job.created_at, "first_submission_at": first, "response_hours": hours})
    submitted = (
        await db.execute(
            select(ProfileShareItem.application_id, func.min(ProfileShare.created_at), JobApplication.job_id, JobApplication.status, Candidate.id, Candidate.candidate_code, Candidate.name)
            .join(ProfileShare, ProfileShare.id == ProfileShareItem.share_id)
            .join(Job, Job.id == ProfileShare.job_id)
            .join(JobApplication, JobApplication.id == ProfileShareItem.application_id)
            .join(Candidate, Candidate.id == ProfileShareItem.candidate_id)
            .where(*to_vendor)
            .group_by(ProfileShareItem.application_id, JobApplication.job_id, JobApplication.status, Candidate.id, Candidate.candidate_code, Candidate.name)
            .order_by(func.min(ProfileShare.created_at).desc(), Candidate.candidate_code)
        )
    ).all()
    entered = defaultdict(set)
    if submitted:
        history = await db.execute(
            select(JobApplicationStatusHistory.application_id, JobApplicationStatusHistory.to_status).where(
                JobApplicationStatusHistory.application_id.in_([r[0] for r in submitted]), JobApplicationStatusHistory.to_status.in_(("interview", "selected"))
            )
        )
        for app_id, status in history.all():
            entered[app_id].add(status)
    for app_id, at, job_id, status, cid, code, name in submitted:
        reached = entered[app_id] | {status}
        job = by_id[job_id]
        out[job.via_vendor_id][1].append(
            {
                "application_id": app_id,
                "candidate": {"id": cid, "code": code, "name": name},
                "requirement": _requirement_ref(job),
                "submitted_at": at,
                "interviewed": bool(reached & {*INTERVIEWED}),
                "placed": bool(reached & {*PLACED}),
                "joined": status in requirements.HIRED_APPLICATION_STATUSES,
            }
        )
    return out


def _vendor_row(vendor: Company) -> dict:
    return {"vendor": {"id": vendor.id, "code": vendor.company_code, "name": vendor.name}, "vendor_status_label": companies.VENDOR_STATUS_LABELS.get(vendor.vendor_status or "")}


async def performance_page(db: AsyncSession, user: User, limit: int, offset: int) -> dict:
    where = [companies.VENDOR_COMPANY, Company.merged_into_id.is_(None), *await companies.caller_scope(db, user)]
    total = await db.scalar(select(func.count()).select_from(Company).where(*where))
    vendors = list(await db.scalars(select(Company).where(*where).order_by(func.lower(Company.name), Company.id).limit(limit).offset(offset)))
    ids = [v.id for v in vendors]
    rows, payments = await _drill_down(db, user, ids), await money_totals(db, ids)
    items = [{**_vendor_row(v), "metrics": metrics(*rows[v.id], payments[v.id])} for v in vendors]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def performance_detail(db: AsyncSession, user: User, vendor: Company) -> dict:
    (requirement_rows, submission_rows), payments = (await _drill_down(db, user, [vendor.id]))[vendor.id], (await money_totals(db, [vendor.id]))[vendor.id]
    return {**_vendor_row(vendor), "metrics": metrics(requirement_rows, submission_rows, payments), "requirements": requirement_rows, "submissions": submission_rows}


# --- audit and log --------------------------------------------------------------------------------------------------------------
def audit(db: AsyncSession, user: User, action: str, bill: VendorBill, metadata: dict) -> None:
    """Same transaction as the write; ids, kind and amounts only -- never notes, references, reasons or names."""
    db.add(AuditLog(user_id=user.id, action=f"vendor_commercials.{action}", entity_type="vendor_bill", entity_id=str(bill.id), metadata_json={"company_id": str(bill.company_id), "kind": bill.kind, **metadata}))


def log(event: str, user: User, **ids) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), **{k: str(v) for k, v in ids.items()}}})
