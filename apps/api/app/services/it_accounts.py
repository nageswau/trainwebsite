"""itc-017 (DEC-SCOPE-367) -- the IT accounts workspace's five read-only reports over IT enrolment fees. Spec:
docs/superpowers/specs/2026-11-03-itc-017-accounts-workspace-design.md.

Nothing is stored or copied: every figure is read from `Payment`, `Receipt`, `FeeAdjustment` and `FeeReminderLog`, and an enrolment's
balance is itc-013's one definition (`fee_accounts.balance_for`), so the workspace and each fee account always agree (AC2).

- collections   confirmed (paid / succeeded) fee rows grouped by IST day, month or course (F4: dated on the IST day of `paid_at`)
- outstanding   active enrolments with a positive balance, with the overdue part and a per-course summary (F5)
- overdue       owed installments due before today (IST, itc-016's rule), with the reminders sent
- receipts      every receipt of an IT enrolment fee (a corrected payment's receipt shows status `reversed`)
- adjustments   itc-015's credit notes, write-offs, refunds and reversals

Each report returns the page and the totals of the whole filtered list; `export` reuses the same query for the CSV rows.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FEE_ADJUSTMENT_KINDS, Batch, Enrollment, FeeAdjustment, FeeReminderLog, Payment, Program, Receipt, User
from app.services import fee_accounts, ledger

REPORTS = ("collections", "outstanding", "overdue", "receipts", "adjustments")
GROUPS = ("day", "month", "course")
STATES = ("enrolled_pending_payment", "partially_paid", "overdue")
MAX_DAYS = 366
EXPORT_CAP = 10_000
ACTIVE = "active"  # backlog Appendix B: outstanding is over active enrolments

NO_COURSE = "Choose a course from the list"
NO_BATCH = "Choose a batch from the list"
BATCH_OUTSIDE = "That batch is not in the chosen course"
DATE_ORDER = "The start date must be on or before the end date"
DATE_SPAN = f"Choose a date range of at most {MAX_DAYS} days"
TOO_MANY = f"The export is limited to {EXPORT_CAP:,} rows. Narrow the filters and try again."


@dataclass
class Filters:
    program_id: UUID | None = None
    batch_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    group: str = "day"
    mode: str | None = None
    kind: str | None = None
    state: str | None = None

    def echo(self) -> dict:
        return {k: (str(v) if v is not None else None) for k, v in vars(self).items()}


async def resolve(db: AsyncSession, f: Filters) -> Filters:
    """Fills the default range (this IST month to today) and refuses a filter that names nothing, with words a person can act on."""
    today = fee_accounts.india_today()
    f.date_to = f.date_to or today
    f.date_from = f.date_from or f.date_to.replace(day=1)
    if f.date_from > f.date_to:
        raise HTTPException(422, DATE_ORDER)
    if (f.date_to - f.date_from).days + 1 > MAX_DAYS:
        raise HTTPException(422, DATE_SPAN)
    if f.program_id is not None and await db.get(Program, f.program_id) is None:
        raise HTTPException(422, NO_COURSE)
    if f.batch_id is not None:
        batch = await db.get(Batch, f.batch_id)
        if batch is None:
            raise HTTPException(422, NO_BATCH)
        if f.program_id is not None and batch.program_id != f.program_id:
            raise HTTPException(422, BATCH_OUTSIDE)
    return f


async def choices(db: AsyncSession) -> dict:
    courses = (await db.execute(select(Program.id, Program.title).order_by(func.lower(Program.title)))).all()
    batches = (await db.execute(select(Batch.id, Batch.name, Batch.program_id).order_by(func.lower(Batch.name)))).all()
    return {"courses": [{"id": i, "title": t} for i, t in courses], "batches": [{"id": i, "name": n, "program_id": p} for i, n, p in batches]}


def _scope(f: Filters) -> list:
    return [*([Batch.program_id == f.program_id] if f.program_id else []), *([Batch.id == f.batch_id] if f.batch_id else [])]


def _fee_rows() -> list:
    return [Payment.division == "it", Payment.reference_type.in_(fee_accounts.FEE_REFERENCES)]


def _money(value) -> float:
    return round(float(value or 0), 2)


async def _paged(db: AsyncSession, stmt, limit: int, offset: int) -> tuple[list, int]:
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return (await db.execute(stmt.limit(limit).offset(offset))).all(), total or 0


# --- collections (AC1) -------------------------------------------------------------------------------------------------------------


async def collections(db: AsyncSession, f: Filters, limit: int, offset: int) -> dict:
    day = ledger.ist_day(func.coalesce(Payment.paid_at, Receipt.issued_at, Payment.updated_at))
    where = [*_fee_rows(), Payment.status.in_(fee_accounts.PAID), day >= f.date_from, day <= f.date_to, *_scope(f), *([Payment.payment_mode == f.mode] if f.mode else [])]

    def base(*cols):
        return (
            select(*cols)
            .select_from(Payment)
            .join(Enrollment, Enrollment.id == Payment.reference_id)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .outerjoin(Receipt, Receipt.payment_id == Payment.id)
            .where(*where)
        )

    if f.group == "course":
        keys, order = (Program.id, Program.title), (func.lower(Program.title), Program.id)
    else:
        key = day if f.group == "day" else func.date_trunc("month", day)
        keys, order = (key,), (key,)
    stmt = base(*keys, func.count(), func.sum(Payment.amount)).group_by(*keys).order_by(*order)
    rows, total = await _paged(db, stmt, limit, offset)
    items = []
    for *k, count, amount in rows:
        if f.group == "course":
            item_key, label = str(k[0]), k[1]
        elif f.group == "month":
            item_key, label = k[0].strftime("%Y-%m"), k[0].strftime("%B %Y")
        else:
            item_key, label = k[0].isoformat(), k[0].strftime("%d %b %Y")
        items.append({"key": item_key, "label": label, "payments": count, "amount": _money(amount)})
    count, amount = (await db.execute(base(func.count(), func.sum(Payment.amount)))).one()
    return {"items": items, "total": total, "totals": {"payments": count, "amount": _money(amount)}}


# --- outstanding (AC2) and overdue installments --------------------------------------------------------------------------------------


async def outstanding(db: AsyncSession, f: Filters, limit: int, offset: int) -> dict:
    stmt = (
        select(Enrollment.id, Enrollment.enrollment_code, User.id, User.full_name, User.student_code, Program.id, Program.title, Batch.name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .join(User, User.id == Enrollment.student_id)
        .where(Enrollment.status == ACTIVE, *_scope(f))
    )
    enrolments = (await db.execute(stmt)).all()
    ids = [row[0] for row in enrolments]
    figures = await fee_accounts.balance_for(db, ids)
    today = fee_accounts.india_today()
    owed = {}
    if ids:
        late = case((Payment.due_date < today, Payment.amount), else_=0)
        owed_stmt = (
            select(Payment.reference_id, func.sum(late), func.min(Payment.due_date))
            .where(*_fee_rows(), Payment.reference_id.in_(ids), Payment.status.in_(fee_accounts.OWED), Payment.amount > 0)
            .group_by(Payment.reference_id)
        )
        owed = {eid: (_money(overdue), next_due) for eid, overdue, next_due in (await db.execute(owed_stmt)).all()}
    items = []
    for eid, code, student_id, name, student_code, program_id, course, batch in enrolments:
        fig = figures[eid]
        overdue, next_due = owed.get(eid, (0.0, None))
        if fig["state"] == "not_billed" or fig["balance"] <= 0:
            continue
        if f.state == "overdue" and overdue <= 0 or f.state in ("enrolled_pending_payment", "partially_paid") and fig["state"] != f.state:
            continue
        items.append({
            "enrollment_id": eid, "enrollment_code": code, "student_id": student_id, "student_name": name, "student_code": student_code,
            "program_id": program_id, "course": course, "batch": batch, "total_payable": fig["total_payable"], "paid_confirmed": fig["paid_confirmed"],
            "balance": fig["balance"], "overdue_amount": overdue, "next_due_date": next_due, "state": fig["state"],
        })  # fmt: skip
    items.sort(key=lambda r: (-r["balance"], r["enrollment_code"]))
    by_course: dict = defaultdict(lambda: {"enrolments": 0, "balance": 0.0})
    for r in items:
        entry = by_course[(r["program_id"], r["course"])]
        entry["enrolments"] += 1
        entry["balance"] = round(entry["balance"] + r["balance"], 2)
    courses = sorted(({"program_id": str(pid), "title": title, **v} for (pid, title), v in by_course.items()), key=lambda c: (-c["balance"], c["title"].lower()))
    totals = {"enrolments": len(items), "balance": _money(sum(r["balance"] for r in items)), "overdue_amount": _money(sum(r["overdue_amount"] for r in items))}
    return {"items": items[offset : offset + limit], "total": len(items), "totals": totals, "by_course": courses}


async def overdue(db: AsyncSession, f: Filters, limit: int, offset: int) -> dict:
    today = fee_accounts.india_today()
    sent = select(FeeReminderLog.payment_id, func.count().label("n")).group_by(FeeReminderLog.payment_id).subquery()
    where = [*_fee_rows(), Payment.status.in_(fee_accounts.OWED), Payment.amount > 0, Payment.due_date < today, Enrollment.status == ACTIVE, *_scope(f)]

    def base(*cols):
        return (
            select(*cols)
            .select_from(Payment)
            .join(Enrollment, Enrollment.id == Payment.reference_id)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .join(User, User.id == Enrollment.student_id)
            .where(*where)
        )

    stmt = base(
        Payment.id, Payment.installment_no, Payment.amount, Payment.due_date, Enrollment.id.label("enrollment_id"), Enrollment.enrollment_code,
        User.id.label("student_id"), User.full_name, User.student_code, Program.title, Batch.name, func.coalesce(sent.c.n, 0).label("reminders"),
    ).outerjoin(sent, sent.c.payment_id == Payment.id).order_by(Payment.due_date, Enrollment.enrollment_code, Payment.installment_no, Payment.id)  # fmt: skip
    rows, total = await _paged(db, stmt, limit, offset)
    items = [
        {"payment_id": r.id, "enrollment_id": r.enrollment_id, "enrollment_code": r.enrollment_code, "student_id": r.student_id, "student_name": r.full_name,
         "student_code": r.student_code, "course": r.title, "batch": r.name, "installment_no": r.installment_no, "due_date": r.due_date,
         "days_overdue": (today - r.due_date).days, "amount": _money(r.amount), "reminders": r.reminders}
        for r in rows
    ]  # fmt: skip
    count, amount = (await db.execute(base(func.count(), func.sum(Payment.amount)))).one()
    return {"items": items, "total": total, "totals": {"installments": count, "amount": _money(amount)}}


# --- receipts register and adjustments ----------------------------------------------------------------------------------------------


async def receipts(db: AsyncSession, f: Filters, limit: int, offset: int) -> dict:
    day = ledger.ist_day(Receipt.issued_at)
    where = [*_fee_rows(), day >= f.date_from, day <= f.date_to, *_scope(f), *([Payment.payment_mode == f.mode] if f.mode else [])]

    def base(*cols):
        return (
            select(*cols)
            .select_from(Receipt)
            .join(Payment, Payment.id == Receipt.payment_id)
            .join(Enrollment, Enrollment.id == Payment.reference_id)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .join(User, User.id == Enrollment.student_id)
            .where(*where)
        )

    stmt = base(
        Receipt.receipt_no, day.label("issued_on"), User.full_name, User.student_code, Enrollment.enrollment_code, Program.title, Batch.name,
        Payment.amount, Payment.payment_mode, Payment.provider_reference, Payment.status,
    ).order_by(Receipt.issued_at.desc(), Receipt.receipt_no)  # fmt: skip
    rows, total = await _paged(db, stmt, limit, offset)
    items = [
        {"receipt_no": r.receipt_no, "issued_on": r.issued_on, "student_name": r.full_name, "student_code": r.student_code, "enrollment_code": r.enrollment_code,
         "course": r.title, "batch": r.name, "amount": _money(r.amount), "payment_mode": r.payment_mode, "reference": r.provider_reference, "status": r.status}
        for r in rows
    ]  # fmt: skip
    counted = case((Payment.status.in_(fee_accounts.PAID), Payment.amount), else_=0)  # a reversed payment's receipt is listed, not summed
    count, amount = (await db.execute(base(func.count(), func.sum(counted)))).one()
    return {"items": items, "total": total, "totals": {"receipts": count, "amount": _money(amount)}}


async def adjustments(db: AsyncSession, f: Filters, limit: int, offset: int) -> dict:
    day = ledger.ist_day(FeeAdjustment.created_at)
    where = [day >= f.date_from, day <= f.date_to, *_scope(f), *([FeeAdjustment.kind == f.kind] if f.kind else [])]

    def base(*cols):
        return (
            select(*cols)
            .select_from(FeeAdjustment)
            .join(Enrollment, Enrollment.id == FeeAdjustment.enrollment_id)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .join(User, User.id == Enrollment.student_id)
            .where(*where)
        )

    stmt = base(
        FeeAdjustment.document_no, day.label("created_on"), FeeAdjustment.kind, User.full_name, User.student_code, Enrollment.enrollment_code, Program.title,
        Batch.name, FeeAdjustment.amount, FeeAdjustment.payment_mode, FeeAdjustment.reference, FeeAdjustment.reason,
    ).order_by(FeeAdjustment.created_at.desc(), FeeAdjustment.id)  # fmt: skip
    rows, total = await _paged(db, stmt, limit, offset)
    items = [
        {"document_no": r.document_no, "created_on": r.created_on, "kind": r.kind, "student_name": r.full_name, "student_code": r.student_code,
         "enrollment_code": r.enrollment_code, "course": r.title, "batch": r.name, "amount": _money(r.amount), "payment_mode": r.payment_mode,
         "reference": r.reference, "reason": r.reason}
        for r in rows
    ]  # fmt: skip
    sums = dict((await db.execute(base(FeeAdjustment.kind, func.sum(FeeAdjustment.amount)).group_by(FeeAdjustment.kind))).all())
    return {"items": items, "total": total, "totals": {"count": total, **{k: _money(sums.get(k)) for k in FEE_ADJUSTMENT_KINDS}}}


RUN = {"collections": collections, "outstanding": outstanding, "overdue": overdue, "receipts": receipts, "adjustments": adjustments}

# --- CSV (F7): the columns of each report, in order -----------------------------------------------------------------------------------

_STUDENT = [("Student", "student_name"), ("Student ID", "student_code"), ("Enrolment", "enrollment_code"), ("Course", "course"), ("Batch", "batch")]
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "collections": [("Period or course", "label"), ("Payments", "payments"), ("Amount (INR)", "amount")],
    "outstanding": [*_STUDENT, ("Total payable (INR)", "total_payable"), ("Paid (INR)", "paid_confirmed"), ("Balance (INR)", "balance"),
                    ("Overdue (INR)", "overdue_amount"), ("Next due", "next_due_date"), ("State", "state")],
    "overdue": [*_STUDENT, ("Installment", "installment_no"), ("Due date", "due_date"), ("Days overdue", "days_overdue"), ("Amount (INR)", "amount"),
                ("Reminders sent", "reminders")],
    "receipts": [("Receipt", "receipt_no"), ("Issued on", "issued_on"), *_STUDENT, ("Amount (INR)", "amount"), ("Mode", "payment_mode"),
                 ("Reference", "reference"), ("Status", "status")],
    "adjustments": [("Document", "document_no"), ("Date", "created_on"), ("Kind", "kind"), *_STUDENT, ("Amount (INR)", "amount"),
                    ("Mode", "payment_mode"), ("Reference", "reference"), ("Reason", "reason")],
}  # fmt: skip
