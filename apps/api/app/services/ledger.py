"""mgmt-004 (spec ML1-ML16): the management ledger, the single money source of the Command Center (owner; frozen after mgmt-005).
mgmt-005 (spec MA1-MA12) adds `lines`: the manual entries UNION ALL the automatic money lines of other modules, computed on read.

Manual income and expense entries move draft -> submitted -> approved / rejected; only approved entries count (ML10), and an approved
entry is corrected only by a reversing entry (ML11). Every write adds an entry event and a `management_audit` row in the caller's
transaction; the routes in `api/management_ledger.py` commit once. Spec: docs/superpowers/specs/2026-10-12-mgmt-004-management-ledger-design.md.
"""

import hashlib
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Date, String, Uuid, case, cast, func, literal, literal_column, null, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import PAID_STATUSES
from app.models import (
    AgentCommission,
    Batch,
    BdmProfile,
    BdmTrip,
    BdmTripExpense,
    Department,
    LedgerCategory,
    LedgerEntry,
    LedgerEntryEvent,
    Payment,
    Program,
    Receipt,
    RecruiterInvoice,
    RecruiterPayment,
    SalaryMonthTotal,
    University,
    UniversityCommissionReceipt,
    User,
)
from app.services import management_audit
from app.services.agent_deposits import REFERENCE_TYPE as AGENT_DEPOSIT
from app.services.management_access import can_view_finance, require_management
from app.services.storage import storage
from app.services.telecaller_reports import SOURCE_LABELS

logger = logging.getLogger("app.management")
IST = ZoneInfo("Asia/Kolkata")
STORAGE_PREFIX = "ledger-receipts"
EDITABLE = ("draft", "rejected")
CENTS = Decimal("0.01")
VERTICAL_LABELS = {"abroad": "Abroad Education", "it": "IT Training", "recruitment": "Recruitment", "school": "School projects", "other": "Other", "shared": "Shared (company-wide)"}
# The fields an entry write may change, and the ones whose before/after values the audit keeps (MA3: finance kind, no PII).
FIELDS = ("entry_date", "category_id", "amount", "description", "vertical", "channel", "program_id", "batch_id")
VALUED = ("entry_date", "amount", "vertical", "status")

FINANCE_ONLY = "Finance access required"
PARTNER_ONLY = "Only a partner can approve or reject ledger entries"
OWN_ENTRY = "You can't approve or reject your own entry; another partner decides it"
NOT_FOUND = "Ledger entry not found"
LOCKED = "Only a draft or rejected entry can be changed"
NOT_SUBMITTABLE = "Only a draft or rejected entry can be submitted"
NOT_SUBMITTED = "Only a submitted entry can be approved or rejected"
NOT_REVERSIBLE = "Only an approved entry can be reversed"
REVERSAL_OF_REVERSAL = "A reversal can't itself be reversed"
ALREADY_REVERSED = "This entry already has a reversal"
NO_RECEIPT = "No receipt is attached to this entry"
CATEGORY_NOT_FOUND = "Category not found"
DUPLICATE_CATEGORY = "A category with this name already exists"


def today() -> date:
    return datetime.now(IST).date()


def now() -> datetime:
    return datetime.now(UTC)


def field_error(field: str, message: str) -> HTTPException:
    """A database rule's 422 in FastAPI's own shape, so the form puts the message on its field."""
    return HTTPException(422, [{"loc": ["body", field], "msg": message, "type": "value_error"}])


def require_finance(user: User) -> User:
    """ML16: partner and accountant only. Management roles without the finance tier (super_admin, M13) get their own message."""
    require_management(user)
    if not can_view_finance(user):
        raise HTTPException(403, FINANCE_ONLY)
    return user


def require_partner(user: User) -> None:
    if user.role != "partner":
        raise HTTPException(403, PARTNER_ONLY)


def log(event: str, user: User, entry_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "entry_id": str(entry_id), **extra}})


# --- categories (ML1-ML3) -----------------------------------------------------------------------------------------------------
async def load_category(db: AsyncSession, category_id, *, lock: bool = False) -> LedgerCategory:
    stmt = select(LedgerCategory).where(LedgerCategory.id == category_id)
    category = await db.scalar(stmt.with_for_update() if lock else stmt)
    if category is None:
        raise HTTPException(404, CATEGORY_NOT_FOUND)
    return category


async def name_taken(db: AsyncSession, kind: str, name: str, except_id=None) -> bool:
    stmt = select(LedgerCategory.id).where(LedgerCategory.kind == kind, func.lower(LedgerCategory.name) == name.lower())
    if except_id is not None:
        stmt = stmt.where(LedgerCategory.id != except_id)
    return await db.scalar(stmt.limit(1)) is not None


def category_out(category: LedgerCategory) -> dict:
    return {"id": category.id, "kind": category.kind, "nature": category.nature, "name": category.name, "active": category.active}


async def categories(db: AsyncSession, *, active_only: bool = False) -> list[dict]:
    stmt = select(LedgerCategory).order_by(LedgerCategory.kind.desc(), LedgerCategory.nature, func.lower(LedgerCategory.name))
    if active_only:
        stmt = stmt.where(LedgerCategory.active.is_(True))
    return [category_out(c) for c in (await db.scalars(stmt)).all()]


async def entry_category(db: AsyncSession, category_id, kind: str) -> LedgerCategory:
    """ML3/ML4: a category chosen for a new entry, or a change of category, must exist, be active and have the entry's kind."""
    category = await db.get(LedgerCategory, category_id)
    if category is None:
        raise field_error("category_id", "Choose a category from the list")
    if category.kind != kind:
        raise field_error("category_id", f"Choose an {kind} category")
    if not category.active:
        raise field_error("category_id", "This category is no longer in use; choose another")
    return category


async def resolve_tags(db: AsyncSession, kind: str, state: dict) -> None:
    """ML6, in place: a channel only on expenses; a batch must belong to the chosen course, and a batch alone sets its course."""
    if state.get("channel") and kind != "expense":
        raise field_error("channel", "A marketing channel is only for expenses")
    if state.get("program_id") and await db.get(Program, state["program_id"]) is None:
        raise field_error("program_id", "Choose a course from the list")
    if state.get("batch_id"):
        batch = await db.get(Batch, state["batch_id"])
        if batch is None:
            raise field_error("batch_id", "Choose a batch from the list")
        if state.get("program_id") and batch.program_id != state["program_id"]:
            raise field_error("batch_id", "This batch belongs to another course")
        state["program_id"] = batch.program_id


# --- entries ------------------------------------------------------------------------------------------------------------------
async def load_entry(db: AsyncSession, entry_id, *, lock: bool = False) -> LedgerEntry:
    stmt = select(LedgerEntry).where(LedgerEntry.id == entry_id)
    entry = await db.scalar(stmt.with_for_update() if lock else stmt)
    if entry is None:
        raise HTTPException(404, NOT_FOUND)
    return entry


async def live_reversal_id(db: AsyncSession, entry_id):
    return await db.scalar(select(LedgerEntry.id).where(LedgerEntry.reversal_of_id == entry_id, LedgerEntry.status != "rejected"))


def add_event(db: AsyncSession, user: User, entry: LedgerEntry, event: str, from_status: str | None, *, fields=(), reason: str | None = None, receipt_key: str | None = None) -> None:
    db.add(LedgerEntryEvent(entry_id=entry.id, actor_user_id=user.id, event=event, from_status=from_status, to_status=entry.status, fields=list(fields), reason=reason, receipt_key=receipt_key))


def audit(db: AsyncSession, user: User, verb: str, entity_id, fields=(), before: dict | None = None, after: dict | None = None) -> None:
    """ML14: field names always; before/after values for the valued fields named (MA3)."""
    values = {f: ((before or {}).get(f), (after or {}).get(f)) for f in fields if f in VALUED} or None
    management_audit.record(db, user, "mgmt.ledger", verb, str(entity_id), fields=list(fields), values=values)


def can(user: User, entry: LedgerEntry, reversed_by_id) -> dict:
    return {
        "edit": entry.status in EDITABLE,
        "submit": entry.status in EDITABLE,
        "decide": user.role == "partner" and entry.status == "submitted" and entry.created_by_user_id != user.id,
        "reverse": entry.status == "approved" and entry.reversal_of_id is None and reversed_by_id is None,
    }


async def entries_out(db: AsyncSession, user: User, rows: list[LedgerEntry]) -> list[dict]:
    """The page's related rows in one query each (categories, people, courses, batches, live reversals)."""
    if not rows:
        return []
    ids = [r.id for r in rows]
    cats = {c.id: c for c in (await db.scalars(select(LedgerCategory).where(LedgerCategory.id.in_({r.category_id for r in rows})))).all()}
    people_ids = {i for r in rows for i in (r.created_by_user_id, r.updated_by_user_id, r.decided_by_user_id) if i}
    people: dict = {u.id: {"id": u.id, "full_name": u.full_name} for u in (await db.scalars(select(User).where(User.id.in_(people_ids)))).all()}
    programs: dict = {p.id: {"id": p.id, "name": p.title} for p in (await db.scalars(select(Program).where(Program.id.in_({r.program_id for r in rows if r.program_id})))).all()}
    batches: dict = {b.id: {"id": b.id, "name": b.name} for b in (await db.scalars(select(Batch).where(Batch.id.in_({r.batch_id for r in rows if r.batch_id})))).all()}
    reversals = dict((await db.execute(select(LedgerEntry.reversal_of_id, LedgerEntry.id).where(LedgerEntry.reversal_of_id.in_(ids), LedgerEntry.status != "rejected"))).all())
    out = []
    for r in rows:
        category = cats[r.category_id]
        out.append(
            {
                "source": "manual",
                "id": r.id,
                "entry_date": r.entry_date,
                "kind": r.kind,
                "amount": r.amount,
                "description": r.description,
                "vertical": r.vertical,
                "category": {"id": category.id, "name": category.name, "active": category.active},
                "channel": r.channel,
                "program": programs.get(r.program_id),
                "batch": batches.get(r.batch_id),
                "status": r.status,
                "reversal_of_id": r.reversal_of_id,
                "reversed_by_id": reversals.get(r.id),
                "receipt": {"name": r.receipt_name, "content_type": r.receipt_content_type} if r.receipt_key else None,
                "created_by": people.get(r.created_by_user_id),
                "updated_by": people.get(r.updated_by_user_id),
                "decided_by": people.get(r.decided_by_user_id),
                "submitted_at": r.submitted_at,
                "decided_at": r.decided_at,
                "rejection_reason": r.rejection_reason,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "can": can(user, r, reversals.get(r.id)),
            }
        )
    return out


async def entry_detail(db: AsyncSession, user: User, entry: LedgerEntry) -> dict:
    await db.refresh(entry)
    (out,) = await entries_out(db, user, [entry])
    rows = (
        await db.execute(
            select(LedgerEntryEvent, User)
            .outerjoin(User, User.id == LedgerEntryEvent.actor_user_id)
            .where(LedgerEntryEvent.entry_id == entry.id)
            .order_by(LedgerEntryEvent.created_at, LedgerEntryEvent.id)
        )
    ).all()
    out["events"] = [
        {
            "id": e.id,
            "at": e.created_at,
            "actor": {"id": u.id, "full_name": u.full_name} if u else None,
            "event": e.event,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "fields": e.fields,
            "reason": e.reason,
        }
        for e, u in rows
    ]
    return out


def list_filters(*, month: str | None, kind: str | None, category_id, vertical: str | None, table=LedgerEntry.__table__) -> list:
    """ML15, without the status filter: the totals use the same clauses with status = approved (ML10). `table` is `ledger_entries` or
    the mgmt-005 `lines()` subquery, which has the same column names."""
    c = table.c
    where: list = []
    if month:
        year, number = (int(part) for part in month.split("-"))
        first = date(year, number, 1)
        where += [c.entry_date >= first, c.entry_date < (date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1))]
    if kind:
        where.append(c.kind == kind)
    if category_id:
        where.append(c.category_id == category_id)
    if vertical:
        where.append(c.vertical == vertical)
    return where


async def totals(db: AsyncSession, where: list) -> dict:
    """ML10: approved entries only; a reversal counts as the negative of its amount."""
    signed = case((LedgerEntry.reversal_of_id.is_(None), LedgerEntry.amount), else_=-LedgerEntry.amount)
    sums: dict = dict((await db.execute(select(LedgerEntry.kind, func.coalesce(func.sum(signed), 0)).where(*where, LedgerEntry.status == "approved").group_by(LedgerEntry.kind))).all())
    income, expense = (Decimal(sums.get(k, 0)).quantize(CENTS) for k in ("income", "expense"))
    return {"income": income, "expense": expense, "net": (income - expense).quantize(CENTS)}


async def page(db: AsyncSession, user: User, where: list, status: str | None, limit: int, offset: int) -> dict:
    rows_where = [*where, *([LedgerEntry.status == status] if status else [])]
    total = await db.scalar(select(func.count()).select_from(LedgerEntry).where(*rows_where))
    rows = (await db.scalars(select(LedgerEntry).where(*rows_where).order_by(LedgerEntry.entry_date.desc(), LedgerEntry.created_at.desc(), LedgerEntry.id).limit(limit).offset(offset))).all()
    return {"items": await entries_out(db, user, list(rows)), "total": total, "limit": limit, "offset": offset, "totals": await totals(db, where)}


# --- automatic lines (mgmt-005, MA1-MA11) -------------------------------------------------------------------------------------
CURRENCY = "INR"
PAYMENT_VERTICAL = case((Payment.division == "it", "it"), (Payment.division == "overseas", "abroad"), else_="other")  # MA5 (Q-08)
PAYMENT_KIND = case((Payment.reference_type.in_(("enrollment_fee", "enrollment")), "Enrolment fee"), (Payment.reference_type == "service_fee", "Service fee"), else_="Payment")
TRIP_VERTICAL = case((BdmProfile.bdm_type == "college", "it"), (BdmProfile.bdm_type == "agent", "abroad"), (BdmProfile.bdm_type == "school", "school"), else_="shared")
AUTO_FIELDS = ("source", "id", "entry_date", "kind", "vertical", "category_label", "amount", "currency", "description", "counted")


def ist_day(moment):
    """MA2: the IST calendar day of a timestamptz."""
    return cast(func.timezone(IST.key, moment), Date)


def _auto(source: str, *, id, entry_date, kind: str, vertical, label, amount, currency, description, created_at):
    """One automatic source in the `lines` column shape: no ledger category, no status; it counts when it is in rupees (MA8)."""
    return select(
        literal(source, String).label("source"),
        id.label("id"),
        entry_date.label("entry_date"),
        literal(kind, String).label("kind"),
        vertical.label("vertical"),
        cast(null(), Uuid).label("category_id"),
        label.label("category_label"),
        cast(null(), String).label("status"),
        amount.label("amount"),
        amount.label("signed_amount"),
        currency.label("currency"),
        description.label("description"),
        (currency == CURRENCY).label("counted"),
        created_at.label("created_at"),
    )


def lines():
    """MA1: the manual entries UNION ALL the automatic sources (five from mgmt-005, salaries from mgmt-011), one subquery with `ledger_entries`' filter column names. A manual
    entry counts once approved (a reversal negatively, ML10); an automatic line counts when in rupees. Nothing is copied or stored."""
    manual = select(
        literal("manual", String).label("source"),
        LedgerEntry.id,
        LedgerEntry.entry_date,
        LedgerEntry.kind,
        LedgerEntry.vertical,
        LedgerEntry.category_id,
        LedgerCategory.name.label("category_label"),
        LedgerEntry.status,
        LedgerEntry.amount,
        case((LedgerEntry.reversal_of_id.is_(None), LedgerEntry.amount), else_=-LedgerEntry.amount).label("signed_amount"),
        literal(CURRENCY, String).label("currency"),
        LedgerEntry.description,
        (LedgerEntry.status == "approved").label("counted"),
        LedgerEntry.created_at,
    ).join(LedgerCategory, LedgerCategory.id == LedgerEntry.category_id)
    payments = (
        _auto(
            "payment",
            id=Payment.id,
            entry_date=ist_day(func.coalesce(Receipt.issued_at, Payment.updated_at)),  # MA2: a paid payment never moves again (AGN-011 D2)
            kind="income",
            vertical=PAYMENT_VERTICAL,
            label=case((PAYMENT_VERTICAL == "it", "IT training"), (PAYMENT_VERTICAL == "abroad", "Abroad education"), else_="Other"),
            amount=Payment.amount,
            currency=Payment.currency,
            description=func.concat(
                PAYMENT_KIND,
                case((Payment.installment_no.is_not(None), func.concat(" · instalment ", cast(Payment.installment_no, String)))),
                case((Receipt.receipt_no.is_not(None), func.concat(" · receipt ", Receipt.receipt_no))),
            ),
            created_at=Payment.created_at,
        )
        .outerjoin(Receipt, Receipt.payment_id == Payment.id)
        .where(Payment.status.in_(PAID_STATUSES), Payment.reference_type != AGENT_DEPOSIT)
    )
    commissions = _auto(
        "agent_commission",
        id=AgentCommission.id,
        entry_date=ist_day(func.coalesce(AgentCommission.paid_at, AgentCommission.updated_at)),
        kind="expense",
        vertical=literal("abroad", String),
        label=literal("Agent commissions", String),
        amount=AgentCommission.amount,
        currency=AgentCommission.currency,
        description=func.concat("Agent commission", case((AgentCommission.claim_reference.is_not(None), func.concat(" · claim ", AgentCommission.claim_reference)))),
        created_at=AgentCommission.created_at,
    ).where(AgentCommission.status == "paid", AgentCommission.amount > 0)
    trips = (
        _auto(
            "trip_expense",
            id=BdmTripExpense.id,
            entry_date=BdmTripExpense.expense_date,
            kind="expense",
            vertical=TRIP_VERTICAL,
            label=literal("Travel", String),
            amount=BdmTripExpense.amount,
            currency=BdmTrip.currency,
            description=func.concat("Trip ", BdmTrip.code, " · ", BdmTripExpense.category),
            created_at=BdmTripExpense.created_at,
        )
        .join(BdmTrip, BdmTrip.id == BdmTripExpense.trip_id)
        .outerjoin(BdmProfile, BdmProfile.user_id == BdmTrip.bdm_user_id)
        .where(BdmTrip.approval_status == "approved")
    )
    recruiter = _auto(
        "recruiter_payment",
        id=RecruiterPayment.id,
        entry_date=RecruiterPayment.received_on,
        kind="income",
        vertical=literal("recruitment", String),
        label=literal("Recruitment", String),
        amount=RecruiterPayment.amount,
        currency=literal(CURRENCY, String),  # rec-031 invoices are in rupees
        description=func.concat("Invoice ", RecruiterInvoice.invoice_number, " payment"),
        created_at=RecruiterPayment.created_at,
    ).join(RecruiterInvoice, RecruiterInvoice.id == RecruiterPayment.invoice_id)
    universities = _auto(
        "university_commission",
        id=UniversityCommissionReceipt.id,
        entry_date=UniversityCommissionReceipt.received_on,
        kind="income",
        vertical=literal("abroad", String),
        label=literal("University commission", String),
        amount=UniversityCommissionReceipt.amount,
        currency=UniversityCommissionReceipt.currency,
        description=func.concat(University.name, " · ", UniversityCommissionReceipt.reference),
        created_at=UniversityCommissionReceipt.created_at,
    ).join(University, University.id == UniversityCommissionReceipt.university_id)
    salary_cost = SalaryMonthTotal.paid + SalaryMonthTotal.incentives + SalaryMonthTotal.commissions + SalaryMonthTotal.employer_cost
    salaries = _auto(  # mgmt-011 SM8: a saved department month, dated its last day; the manual "Salaries" category is inactive (SM9)
        "salary",
        id=SalaryMonthTotal.id,
        entry_date=cast(SalaryMonthTotal.month + literal_column("INTERVAL '1 month - 1 day'"), Date),
        kind="expense",
        vertical=literal("shared", String),
        label=literal("Salaries", String),
        amount=salary_cost,
        currency=literal(CURRENCY, String),
        description=func.concat("Salaries · ", Department.name),
        created_at=SalaryMonthTotal.created_at,
    ).join(Department, Department.id == SalaryMonthTotal.department_id).where(salary_cost > 0)
    return union_all(manual, payments, commissions, trips, recruiter, universities, salaries).subquery("ledger_lines")


async def lines_totals(db: AsyncSession, table, where: list) -> dict:
    """MA11: the counted lines (approved manual entries + rupee automatic lines) over every filter but status, plus the automatic
    lines in another currency, per currency and kind (MA8)."""
    c = table.c
    sums: dict = dict((await db.execute(select(c.kind, func.coalesce(func.sum(c.signed_amount), 0)).where(*where, c.counted).group_by(c.kind))).all())
    income, expense = (Decimal(sums.get(k, 0)).quantize(CENTS) for k in ("income", "expense"))
    other = await db.execute(
        select(c.currency, c.kind, func.sum(c.amount), func.count()).where(*where, c.source != "manual", c.counted.is_(False)).group_by(c.currency, c.kind).order_by(c.currency, c.kind)
    )
    not_counted = [{"currency": cur, "kind": kind, "amount": Decimal(amount).quantize(CENTS), "count": count} for cur, kind, amount, count in other.all()]
    return {"income": income, "expense": expense, "net": (income - expense).quantize(CENTS), "not_counted": not_counted}


async def lines_page(db: AsyncSession, user: User, filters: dict, status: str | None, limit: int, offset: int) -> dict:
    """MA9-MA11: the mixed list, newest first. `category` and `status` are manual fields, so with either set the automatic lines (NULL
    there) drop out through the same clauses (MA10). Manual rows keep mgmt-004's full shape."""
    table = lines()
    c = table.c
    where = list_filters(**filters, table=table)
    rows_where = [*where, *([c.status == status] if status else [])]
    total = await db.scalar(select(func.count()).select_from(table).where(*rows_where))
    rows = (await db.execute(select(table).where(*rows_where).order_by(c.entry_date.desc(), c.created_at.desc(), c.id).limit(limit).offset(offset))).all()
    manual_ids = [r.id for r in rows if r.source == "manual"]
    entries = (await db.scalars(select(LedgerEntry).where(LedgerEntry.id.in_(manual_ids)))).all() if manual_ids else []
    manual = {e["id"]: e for e in await entries_out(db, user, list(entries))}
    items = [manual[r.id] if r.source == "manual" else {k: getattr(r, k) for k in AUTO_FIELDS} for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset, "totals": await lines_totals(db, table, where)}


async def options(db: AsyncSession) -> dict:
    programs = (await db.scalars(select(Program).where(Program.active.is_(True)).order_by(func.lower(Program.title), Program.id))).all()
    batches = (await db.scalars(select(Batch).where(Batch.program_id.in_([p.id for p in programs])).order_by(Batch.start_date.desc(), Batch.name))).all()
    by_program: dict = {}
    for batch in batches:
        by_program.setdefault(batch.program_id, []).append({"id": batch.id, "name": batch.name})
    return {
        "categories": await categories(db, active_only=True),
        "channels": [{"value": k, "label": v} for k, v in SOURCE_LABELS.items()],
        "verticals": [{"value": k, "label": v} for k, v in VERTICAL_LABELS.items()],
        "programs": [{"id": p.id, "name": p.title, "batches": by_program.get(p.id, [])} for p in programs],
    }


# --- receipts (ML13) ----------------------------------------------------------------------------------------------------------
def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("ledger_receipt_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete a receipt stored for a write that did not commit; a failure leaves an orphan, logged by key digest."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("ledger_receipt_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read_receipt(entry: LedgerEntry) -> tuple[bytes, str]:
    if entry.receipt_key is None:
        raise HTTPException(404, NO_RECEIPT)
    try:
        return storage.read_bytes(entry.receipt_key), entry.receipt_content_type or "application/octet-stream"
    except FileNotFoundError:
        logger.warning("ledger_receipt_missing", extra={"extra_fields": {"entry_id": str(entry.id), "key_digest": _digest(entry.receipt_key)}})
        raise HTTPException(404, NO_RECEIPT) from None
