"""mgmt-033 (spec DD1-DD14): drill-down from a revenue figure to the transaction behind it -- EVID-017's "key difference" chains. Read-only;
every rupee is a counted income line of `ledger.lines()` for the chain's vertical, so level 0 is the parent dashboard's revenue and the
rows of every level add up to the figure above them (AC1). A line the data cannot place at a level falls in that level's `none` row (DD7).
Spec: docs/superpowers/specs/2026-10-14-mgmt-033-drill-down-design.md."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    AgentOrg,
    AgentOrgMember,
    AgentStudent,
    Batch,
    Candidate,
    Company,
    Country,
    Enrollment,
    Job,
    JobApplication,
    LedgerEntry,
    OverseasApplication,
    Payment,
    Program,
    RecruiterInvoice,
    RecruiterPayment,
    University,
    UniversityCommissionReceipt,
    User,
)  # fmt: skip
from app.services import ledger, management_audit
from app.services.management_access import can_view_university_commission
from app.services.management_expenses import month_key
from app.services.management_it_revenue import ENROLMENT_REFERENCES, period_range

NONE = "none"
NOT_FOUND = "Nothing to show for this selection in this period"
OUTCOME_STATUSES = ("selected", "joined")  # DD8/DD9: a job application at selection or joining
HUMANISED = frozenset({"Application status", "Offer"})  # record details stored as codes ("offer_received", "conditional")


@dataclass(frozen=True)
class Level:
    key: str
    label: str
    id: Any  # the SQL expression grouped on (a UUID; NULL = the unattributed row)
    name: Any  # its label
    none: str = ""  # the unattributed row's label ("" for the payment level, which is never NULL)


@dataclass(frozen=True)
class Shape:
    """One chain over a `ledger.lines()` table: the joined source, its levels, the record's detail columns and the outcomes' key."""

    joined: Any
    levels: tuple[Level, ...]
    details: tuple[tuple[str, Any], ...]
    outcome_key: Any = None


def _abroad(table) -> Shape:
    c = table.c
    staff, student = aliased(User), aliased(User)
    agent_user_id = func.coalesce(OverseasApplication.agent_id, AgentStudent.agent_id)
    joined = (
        table.outerjoin(Payment, and_(c.source == "payment", Payment.id == c.id))
        .outerjoin(OverseasApplication, OverseasApplication.id == Payment.reference_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.user_id == agent_user_id)
        .outerjoin(AgentOrg, AgentOrg.id == AgentOrgMember.org_id)
        .outerjoin(UniversityCommissionReceipt, and_(c.source == "university_commission", UniversityCommissionReceipt.id == c.id))
        .outerjoin(University, University.id == func.coalesce(OverseasApplication.university_id, UniversityCommissionReceipt.university_id))
        .outerjoin(Country, Country.id == University.country_id)
        .outerjoin(staff, staff.id == func.coalesce(agent_user_id, OverseasApplication.counselor_id))  # DD6: agency staff, else counselor
        .outerjoin(student, student.id == Payment.user_id)
    )
    application = func.coalesce(func.nullif(OverseasApplication.application_reference, ""), func.concat(University.name, " · ", OverseasApplication.intake))
    return Shape(
        joined,
        (
            Level("country", "Country", Country.id, Country.name, "Unknown country"),
            Level("university", "University", University.id, University.name, "Unknown university"),
            Level("agent", "Agency", AgentOrg.id, AgentOrg.name, "No agency"),
            Level("staff", "Staff", staff.id, staff.full_name, "No staff recorded"),
            Level("student", "Student", student.id, student.full_name, "No student"),
            Level("application", "Application", OverseasApplication.id, application, "No application linked"),
            Level("payment", "Payment", c.id, c.description),
        ),
        (("Application status", OverseasApplication.status), ("Intake", OverseasApplication.intake), ("Offer", OverseasApplication.offer_type)),
    )


def _it(table) -> Shape:
    c = table.c
    trainer, student = aliased(User), aliased(User)
    batch_id = func.coalesce(Enrollment.batch_id, LedgerEntry.batch_id)
    joined = (
        table.outerjoin(Payment, and_(c.source == "payment", Payment.id == c.id))
        .outerjoin(Enrollment, and_(Payment.reference_type.in_(ENROLMENT_REFERENCES), Enrollment.id == Payment.reference_id))
        .outerjoin(LedgerEntry, and_(c.source == "manual", LedgerEntry.id == c.id))
        .outerjoin(Batch, Batch.id == batch_id)
        .outerjoin(Program, Program.id == func.coalesce(Batch.program_id, LedgerEntry.program_id))
        .outerjoin(trainer, trainer.id == Batch.trainer_id)
        .outerjoin(student, student.id == Payment.user_id)
    )
    return Shape(
        joined,
        (
            Level("course", "Course", Program.id, Program.title, "No course linked"),
            Level("batch", "Batch", Batch.id, Batch.name, "No batch"),
            Level("trainer", "Trainer", trainer.id, trainer.full_name, "No trainer assigned"),
            Level("student", "Student", student.id, student.full_name, "No student"),
            Level("payment", "Payment", c.id, c.description),
        ),
        (("Enrolment", Enrollment.enrollment_code), ("Instalment", Payment.installment_no)),
        Payment.user_id,
    )


def _recruitment(table) -> Shape:
    c = table.c
    recruiter = aliased(User)
    joined = (
        table.outerjoin(RecruiterPayment, and_(c.source == "recruiter_payment", RecruiterPayment.id == c.id))
        .outerjoin(RecruiterInvoice, RecruiterInvoice.id == RecruiterPayment.invoice_id)
        .outerjoin(Job, Job.id == RecruiterInvoice.job_id)
        .outerjoin(Company, Company.id == Job.company_id)
        .outerjoin(recruiter, recruiter.id == func.coalesce(Job.assigned_recruiter_user_id, Company.assigned_recruiter_user_id))
    )
    return Shape(
        joined,
        (
            Level("company", "Company", Company.id, Company.name, "No company linked"),
            Level("recruiter", "Recruiter", recruiter.id, recruiter.full_name, "No recruiter assigned"),
            Level("job", "Requirement", Job.id, func.concat(Job.title, " · ", Job.requirement_code), "No requirement linked"),
            Level("payment", "Payment", c.id, c.description),
        ),
        (("Invoice", RecruiterInvoice.invoice_number), ("Payment reference", RecruiterPayment.reference)),
        Job.id,
    )


@dataclass(frozen=True)
class Chain:
    label: str
    vertical: str
    shape: Callable[[Any], Shape]
    audited_from: int  # DD11: the level (index) listing individual students; reads from there down are audited


CHAINS = {
    "abroad": Chain("Abroad Education revenue", "abroad", _abroad, 4),
    "it": Chain("IT Training revenue", "it", _it, 3),
    "recruitment": Chain("Recruitment revenue", "recruitment", _recruitment, 3),
}


def parse_path(raw: str | None, depth: int) -> list[UUID | None]:
    """DD12: comma-separated keys in level order, each a UUID or `none`; at most `depth` of them; never `none` for the payment."""
    if not raw:
        return []
    keys = raw.split(",")
    if len(keys) > depth:
        raise HTTPException(422, "The drill-down path is too long")
    path: list[UUID | None] = []
    for key in keys:
        try:
            path.append(None if key == NONE else UUID(key))
        except ValueError:
            raise HTTPException(422, "The drill-down path is not valid") from None
    if len(path) == depth and path[-1] is None:
        raise HTTPException(422, "Choose a payment")
    return path


def _key(value) -> str:
    return NONE if value is None else str(value)


def _money(value) -> Decimal:
    return Decimal(value).quantize(ledger.CENTS)


def _label(value) -> str:
    return str(value).replace("_", " ").capitalize()


async def drill(db: AsyncSession, user: User, chain_key: str, month_start: date, period: str, raw_path: str | None, *, limit: int, offset: int) -> dict:
    chain = CHAINS.get(chain_key)
    if chain is None:
        raise HTTPException(404, "Unknown drill-down")
    table = ledger.lines()
    c = table.c
    shape = chain.shape(table)
    levels = shape.levels
    path = parse_path(raw_path, len(levels))
    start, end = period_range(month_start, period)
    where = [c.vertical == chain.vertical, c.kind == "income", c.counted, c.entry_date >= start, c.entry_date < end]  # DD2
    if chain_key == "abroad" and not can_view_university_commission(user):
        where.append(c.source != "university_commission")  # DD5 (M3): never read, so no figure can carry it
    for level, value in zip(levels, path, strict=False):
        where.append(level.id.is_(None) if value is None else level.id == value)

    total, count = (await db.execute(select(func.coalesce(func.sum(c.signed_amount), 0), func.count()).select_from(shape.joined).where(*where))).one()
    breadcrumbs: list[dict] = []
    if path:
        if count == 0:
            raise HTTPException(404, NOT_FOUND)  # DD12: a tampered or stale path
        names = (await db.execute(select(*(level.name for level in levels[: len(path)])).select_from(shape.joined).where(*where).limit(1))).one()
        breadcrumbs = [
            {"level": level.key, "level_label": level.label, "key": _key(value), "name": level.none if value is None else name}
            for level, value, name in zip(levels[: len(path)], path, names, strict=True)
        ]
    out: dict = {
        "chain": chain_key,
        "chain_label": chain.label,
        "month": month_key(month_start),
        "period": period,
        "label": f"Financial year {start.year}-{(start.year + 1) % 100:02d} to date" if period == "year" else month_start.strftime("%B %Y"),
        "start": start,
        "end": end - timedelta(days=1),
        "total": _money(total),
        "count": count,
        "breadcrumbs": breadcrumbs,
        "level": None,
        "rows": [],
        "total_rows": 0,
        "limit": limit,
        "offset": offset,
        "record": None,
    }
    if len(path) == len(levels):
        out["record"] = await _record(db, chain_key, table, shape, where)
        read = "record"
    else:
        level = levels[len(path)]
        amount = func.sum(c.signed_amount)
        rows = (
            await db.execute(
                select(level.id, func.min(level.name), amount, func.count(), func.max(c.entry_date), func.count().over())
                .select_from(shape.joined)
                .where(*where)
                .group_by(level.id)
                .order_by(amount.desc(), func.min(level.name), level.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        out["level"] = {"key": level.key, "label": level.label}
        out["rows"] = [{"key": _key(key), "name": level.none if key is None else name, "amount": _money(amt), "count": n, "latest": latest} for key, name, amt, n, latest, _ in rows]
        out["total_rows"] = rows[0][-1] if rows else await _groups(db, shape, level, where)
        read = level.key
    if len(path) >= chain.audited_from:  # DD11: individual students, applications or payments were read
        management_audit.record(db, user, "mgmt.drill", "view", _key(path[-1]), fields=(chain_key, read))
        await db.commit()
    return out


async def _groups(db: AsyncSession, shape: Shape, level: Level, where: list) -> int:
    """The row count when `offset` is past the last row (the windowed count then comes back with no row)."""
    grouped = select(level.id).select_from(shape.joined).where(*where).group_by(level.id).subquery()
    return await db.scalar(select(func.count()).select_from(grouped)) or 0


async def _record(db: AsyncSession, chain_key: str, table, shape: Shape, where: list) -> dict:
    """DD9: the chosen line read-only, with the chain's details and outcomes. Names only, no contact details (DD10)."""
    c = table.c
    details = [expr for _, expr in shape.details]
    outcome = [] if shape.outcome_key is None else [shape.outcome_key]
    line = (await db.execute(select(c.source, c.id, c.entry_date, c.signed_amount, c.currency, c.description, *details, *outcome).select_from(shape.joined).where(*where).limit(1))).one()
    source, line_id, entry_date, amount, currency, description, *values = line
    outcome_key = values.pop() if outcome else None
    record = {
        "source": source,
        "id": line_id,
        "entry_date": entry_date,
        "amount": _money(amount),
        "currency": currency,
        "description": description,
        "details": [{"label": label, "value": _label(value) if label in HUMANISED else str(value)} for (label, _), value in zip(shape.details, values, strict=True) if value is not None],
        "outcomes": None,
    }
    if chain_key == "it" and outcome_key is not None:  # DD9: the student's placement outcomes
        placements = await db.execute(
            select(func.concat(Job.title, " · ", Company.name), JobApplication.status)
            .join(Job, Job.id == JobApplication.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(JobApplication.student_id == outcome_key, JobApplication.status.in_(OUTCOME_STATUSES))
            .order_by(JobApplication.stage_changed_at.desc())
        )
        record["outcomes"] = {"title": "Placement", "items": [{"name": name, "detail": None, "status": _label(status)} for name, status in placements.all()]}
    elif chain_key == "recruitment" and outcome_key is not None:  # DD8: the requirement's selections and joinings
        candidates = await db.execute(
            select(Candidate.name, Candidate.candidate_code, JobApplication.status)
            .join(Candidate, Candidate.id == JobApplication.candidate_id)
            .where(JobApplication.job_id == outcome_key, JobApplication.status.in_(OUTCOME_STATUSES))
            .order_by(JobApplication.status, Candidate.name)
        )
        record["outcomes"] = {"title": "Selections and joinings", "items": [{"name": name, "detail": code, "status": _label(status)} for name, code, status in candidates.all()]}
    return record
