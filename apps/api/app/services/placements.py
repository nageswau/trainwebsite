"""pob-024 (DEC-SCOPE-432 P1-P14; design docs/superpowers/specs/2026-11-08-pob-024-placement-closure-design.md): the placement closure
record -- one per accepted offer (P1), its two joining confirmations (P5), the PO owner (P6), the invoice draft made on joining (P8/P9),
its issue as a rec-031 invoice (P10) or its discard (P11), and the daily due/overdue notices (P12/P13).

Read scope is the requirement's (rec-007 `caller_scope`: out of scope = the same 404 as missing). The commercial block (expected fee, the
draft, the invoice) is read and written only behind the rec-031 revenue gate (role + pob-001 `commercials.client.view`, P4); the package
behind hrc-001 `candidates.compensation.view` (P3). Hooks run inside the offer/joining transaction after its locks (application, offer, job,
company), and lock the placement last. Functions only; nothing here commits except the sweep. Audit and logs carry ids, field names and
amounts, never a name, a confirmation or a reason."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    Candidate,
    Company,
    Job,
    JobApplication,
    JobOffer,
    Placement,
    RecCandidateSource,
    RecruiterInvoice,
    RecruiterPayment,
    RecruiterProfile,
    User,
)
from app.notifications.events import notify
from app.schemas import PlacementInvoiceIssue, PlacementUpdate
from app.services import applications, permissions
from app.services import recruiter_contracts as contracts
from app.services import recruiter_requirements as requirements
from app.services import recruiter_revenue as revenue
from app.services.interviews import field_error
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.recruiter_companies import person

logger = logging.getLogger("app.recruiter")

STATUS_LABELS = {"pending": "Joining pending", "joined": "Joined", "did_not_join": "Did not join"}
INVOICE_LABELS = {"none": "No draft yet", "draft": "Draft to review", "issued": "Issued", "discarded": "Discarded"}
VIA_LABELS = {"call": "Call", "email": "Email", "whatsapp": "WhatsApp", "in_person": "In person", "other": "Other"}
VIEWS = {
    "pending": JobOffer.joining_status == "pending",
    "joined": JobOffer.joining_status == "joined",
    "did_not_join": JobOffer.joining_status == "did_not_join",
    "invoice_drafts": Placement.invoice_status == "draft",
}
CONFIRMATIONS = ("candidate_confirmation", "client_confirmation")
OWNER_SETTERS = (MANAGER_ROLE, "super_admin")
NOT_FOUND = "Placement not found"
READ_ONLY = "This candidate did not join, so the placement can't be changed"
NO_DRAFT = {"message": "This placement has no invoice draft to review", "code": "no_invoice_draft"}
NOT_OWNER_SETTER = "Only a Team Lead can change the PO owner"
DID_NOT_JOIN = "Did not join"
SWEEP_LIMIT = 200
DUE, OVERDUE = "it.recruitment.invoice_due", "it.recruitment.invoice_overdue"


def url(placement_id) -> str:
    return f"/recruiter/placements/{placement_id}"


# --- the hooks (P1, P8, P11) -----------------------------------------------------------------------------------------------------------
async def _fresh(db: AsyncSession, model, id_, *, lock: bool = False):
    stmt = select(model).where(model.id == id_).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def ensure(db: AsyncSession, actor: User | None, offer: JobOffer, application: JobApplication) -> Placement:
    """P1/P2: the offer's placement, created once (the caller holds the offer lock; the unique offer_id is the backstop)."""
    existing = await db.scalar(select(Placement).where(Placement.offer_id == offer.id).execution_options(populate_existing=True))
    if existing is not None:
        return existing
    job = await _fresh(db, Job, application.job_id)
    company = await _fresh(db, Company, job.company_id)
    placement = Placement(
        offer_id=offer.id,
        application_id=application.id,
        job_id=job.id,
        candidate_id=application.candidate_id,
        company_id=job.company_id,
        vendor_company_id=job.via_vendor_id,
        role=(offer.position or job.title)[:200],
        recruiter_user_id=job.assigned_recruiter_user_id,
        po_owner_user_id=company.assigned_recruiter_user_id,
        expected_fee=await revenue.offer_fee(db, job, offer.compensation, offer.currency, requirements.ist_today()),
        created_by_user_id=actor.id if actor else None,
    )
    db.add(placement)
    await db.flush()
    audit(db, actor, "created", placement, {"offer_id": str(offer.id), "expected_fee": _amount(placement.expected_fee)})
    return placement


async def on_joined(db: AsyncSession, actor: User, offer: JobOffer, application: JobApplication, job: Job) -> None:
    """P8/P9: exactly one draft -- re-priced on today's terms, due on the joining date (+ the requirement's days when its trigger says so)."""
    placement = await _fresh(db, Placement, (await ensure(db, actor, offer, application)).id, lock=True)
    if placement.invoice_status != "none":
        return
    placement.expected_fee = await revenue.offer_fee(db, job, offer.compensation, offer.currency, requirements.ist_today())
    days = job.payment_days if job.payment_trigger == "days_after_joining" and job.payment_days else 0
    placement.invoice_status = "draft"
    placement.draft_amount = placement.expected_fee if placement.expected_fee else None
    placement.draft_due_date = offer.actual_joining_date + timedelta(days=days)
    placement.draft_created_at = datetime.now(UTC)
    audit(db, actor, "draft_created", placement, {"amount": _amount(placement.draft_amount), "due_date": placement.draft_due_date.isoformat()})


async def on_did_not_join(db: AsyncSession, actor: User, offer: JobOffer) -> None:
    """P11: an open draft is discarded."""
    placement_id = await db.scalar(select(Placement.id).where(Placement.offer_id == offer.id))
    if placement_id is None:
        return
    placement = await _fresh(db, Placement, placement_id, lock=True)
    if placement.invoice_status == "draft":
        _discard(db, actor, placement, DID_NOT_JOIN)


def _discard(db: AsyncSession, actor: User, placement: Placement, reason: str) -> None:
    placement.invoice_status, placement.draft_discard_reason = "discarded", reason
    audit(db, actor, "draft_discarded", placement, {"amount": _amount(placement.draft_amount)})


# --- reads ----------------------------------------------------------------------------------------------------------------------------
async def load(db: AsyncSession, user: User, placement_id: UUID, *, lock: bool = False) -> tuple[Placement, JobOffer]:
    """P14: in the requirement's scope (other roles 403, out of scope 404). With `lock`, the row is locked by id first and scope is checked
    in a fresh statement (the rec-003 rule)."""
    scope = await requirements.caller_scope(db, user)
    if lock:
        await db.execute(select(Placement.id).where(Placement.id == placement_id).with_for_update())
    stmt = select(Placement, JobOffer).join(JobOffer, JobOffer.id == Placement.offer_id).join(Job, Job.id == Placement.job_id)
    row = (await db.execute(stmt.where(Placement.id == placement_id, *scope).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


async def id_for_offer(db: AsyncSession, offer_id: UUID) -> UUID | None:
    return await db.scalar(select(Placement.id).where(Placement.offer_id == offer_id))


async def commercial(db: AsyncSession, user: User) -> bool:
    """P4: the rec-031 revenue gate as a yes/no."""
    return user.role in revenue.READERS and await contracts.sees_commercials(db, user)


def _amount(value) -> str | None:
    return None if value is None else str(revenue.money(value))


def _confirmation(placement: Placement, side: str) -> dict | None:
    by, on, via = (getattr(placement, f"{side}_confirmed_{k}") for k in ("by", "on", "via"))
    if on is None:
        return None
    return {"by": by, "on": on, "via": via, "via_label": VIA_LABELS.get(via, via)}


async def out(db: AsyncSession, user: User, placement: Placement, offer: JobOffer) -> dict:
    application = await _fresh(db, JobApplication, placement.application_id)
    candidate, job, company = await _fresh(db, Candidate, placement.candidate_id), await _fresh(db, Job, placement.job_id), await _fresh(db, Company, placement.company_id)
    vendor = await _fresh(db, Company, placement.vendor_company_id) if placement.vendor_company_id else None
    people = {u.id: u for u in await db.scalars(select(User).where(User.id.in_({placement.recruiter_user_id, placement.po_owner_user_id} - {None})))}
    source = await db.scalar(select(RecCandidateSource.name).where(RecCandidateSource.id == (application.submitted_source_id or candidate.source_id)))
    sees = await commercial(db, user)
    commercials = None
    if sees:
        invoice = await _fresh(db, RecruiterInvoice, placement.invoice_id) if placement.invoice_id else None
        commercials = {
            "expected_fee": _amount(placement.expected_fee),
            "invoice": {
                "status": placement.invoice_status,
                "status_label": INVOICE_LABELS[placement.invoice_status],
                "draft_amount": _amount(placement.draft_amount),
                "draft_due_date": placement.draft_due_date,
                "draft_created_at": placement.draft_created_at,
                "discard_reason": placement.draft_discard_reason,
                "invoice": await revenue.invoice_out(db, user, invoice) if invoice else None,
            },
        }
    package = None
    if offer.compensation is not None and await permissions.user_has_grant(db, user, "candidates.compensation", "view"):
        package = {"compensation": _amount(offer.compensation), "currency": offer.currency}
    status = offer.joining_status or "pending"
    return {
        "id": placement.id,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "role": placement.role,
        "offer_id": offer.id,
        "application": {"id": application.id, "code": application.application_code},
        "candidate": {"id": candidate.id, "code": candidate.candidate_code, "name": candidate.name},
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company": {"id": company.id, "name": company.name},
        "vendor": {"id": vendor.id, "name": vendor.name} if vendor else None,
        "recruiter": person(people.get(placement.recruiter_user_id)),
        "po_owner": person(people.get(placement.po_owner_user_id)),
        "source": source,
        "package": package,
        "joining": {"expected_joining_date": offer.joining_date, "actual_joining_date": offer.actual_joining_date},
        "candidate_confirmation": _confirmation(placement, "candidate"),
        "client_confirmation": _confirmation(placement, "client"),
        "commercials": commercials,
        "permissions": {
            "can_edit": applications.can_write(user) and status != "did_not_join",
            "can_change_owner": user.role in OWNER_SETTERS and status != "did_not_join",
            "can_invoice": sees and placement.invoice_status == "draft",
        },
        "created_at": placement.created_at,
    }


async def list_page(db: AsyncSession, user: User, view: str, limit: int, offset: int) -> dict:
    """The caller's placements in one view; the counts are every view's total."""
    scope = await requirements.caller_scope(db, user)
    base = select(Placement).join(JobOffer, JobOffer.id == Placement.offer_id).join(Job, Job.id == Placement.job_id).where(*scope)
    counts = (await db.execute(base.with_only_columns(*(func.count().filter(c) for c in VIEWS.values())))).one()
    rows = (
        await db.execute(
            base.with_only_columns(Placement, JobOffer, Candidate, Job, Company)
            .join(Candidate, Candidate.id == Placement.candidate_id)
            .join(Company, Company.id == Placement.company_id)
            .where(VIEWS[view])
            .order_by(Placement.created_at.desc(), Placement.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    sees = await commercial(db, user)
    items = [
        {
            "id": p.id,
            "status": o.joining_status or "pending",
            "status_label": STATUS_LABELS.get(o.joining_status or "pending"),
            "role": p.role,
            "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
            "requirement": {"id": j.id, "code": j.requirement_code, "title": j.title},
            "company": {"id": co.id, "name": co.name},
            "joined_on": o.actual_joining_date,
            "invoice_status": p.invoice_status if sees else None,
            "invoice_status_label": INVOICE_LABELS[p.invoice_status] if sees else None,
        }
        for p, o, c, j, co in rows
    ]
    totals = dict(zip(VIEWS, counts, strict=True))
    return {"items": items, "total": totals[view] or 0, "limit": limit, "offset": offset, "counts": {k: v or 0 for k, v in totals.items()}}


# --- writes ---------------------------------------------------------------------------------------------------------------------------
async def update(db: AsyncSession, user: User, placement: Placement, offer: JobOffer, payload: PlacementUpdate) -> list[str]:
    """P5/P6: only the keys sent; returns the changed field names (none = no audit)."""
    sent = payload.model_fields_set
    if sent & set(CONFIRMATIONS):
        applications.require_writer(user, placement.id, "placement_update")
    if "po_owner_user_id" in sent and user.role not in OWNER_SETTERS:
        raise HTTPException(403, NOT_OWNER_SETTER)
    if offer.joining_status == "did_not_join":
        raise HTTPException(409, READ_ONLY)
    today = requirements.ist_today()
    changed = []
    for side in ("candidate", "client"):
        key = f"{side}_confirmation"
        if key not in sent:
            continue
        value = getattr(payload, key)
        if value is not None and value.by is None:
            raise field_error(f"{key}.by", "Enter who confirmed")
        if value is not None and value.on > today:
            raise field_error(f"{key}.on", "The confirmation date cannot be in the future", value.on.isoformat())
        new = (value.by, value.on, value.via) if value else (None, None, None)
        if new != tuple(getattr(placement, f"{side}_confirmed_{k}") for k in ("by", "on", "via")):
            for k, v in zip(("by", "on", "via"), new, strict=True):
                setattr(placement, f"{side}_confirmed_{k}", v)
            changed.append(key)
    if "po_owner_user_id" in sent and payload.po_owner_user_id != placement.po_owner_user_id:
        if payload.po_owner_user_id is not None:
            owner = await db.scalar(select(User).where(User.id == payload.po_owner_user_id))
            if owner is None or owner.role != ROLE or not owner.active:
                raise field_error("po_owner_user_id", "Choose an active placement officer")
        placement.po_owner_user_id = payload.po_owner_user_id
        changed.append("po_owner_user_id")
    if changed:
        audit(db, user, "updated", placement, {"fields": changed})
    return changed


async def require_invoicer(db: AsyncSession, user: User) -> None:
    revenue.require_reader(user)
    await revenue.require_commercials(db, user, "placement_invoice")


async def issue(db: AsyncSession, user: User, placement: Placement, payload: PlacementInvoiceIssue) -> RecruiterInvoice:
    """P10: the draft becomes a rec-031 invoice on the requirement; the notice markers re-arm for its own due date."""
    await require_invoicer(db, user)
    if placement.invoice_status != "draft":
        raise HTTPException(409, NO_DRAFT)
    job = await _fresh(db, Job, placement.job_id)
    invoice = await revenue.add_invoice(db, user, job, payload.invoice_number, payload.invoice_date, payload.due_date, payload.amount, payload.note)
    placement.invoice_status, placement.invoice_id = "issued", invoice.id
    placement.due_notified_at = placement.overdue_notified_at = None
    audit(db, user, "draft_issued", placement, {"invoice_id": str(invoice.id), "amount": _amount(invoice.amount), "draft_amount": _amount(placement.draft_amount)})
    return invoice


async def discard(db: AsyncSession, user: User, placement: Placement, reason: str) -> None:
    await require_invoicer(db, user)
    if placement.invoice_status != "draft":
        raise HTTPException(409, NO_DRAFT)
    _discard(db, user, placement, reason)


# --- P12/P13: the daily notices -------------------------------------------------------------------------------------------------------
async def _recipients(db: AsyncSession, placement: Placement, managers: list[User]) -> list[User]:
    """The recruiter and PO owners and their Team Leads; every active Team Lead when none is found."""
    owners = {placement.recruiter_user_id, placement.po_owner_user_id} - {None}
    leads = set(await db.scalars(select(RecruiterProfile.reporting_manager_user_id).where(RecruiterProfile.user_id.in_(owners)))) - {None}
    people = list(await db.scalars(select(User).where(User.id.in_(owners | leads), User.active)))
    return people if leads else people + managers


async def run_invoice_notices(now: datetime | None = None) -> dict[str, int]:
    """A draft, or an issued invoice still owed, whose due date has come gets `invoice_due` once; past due and still owed, `invoice_overdue`
    once. A bounded batch with `FOR UPDATE SKIP LOCKED`; the markers are written in the notices' transaction (both or neither)."""
    now = now or datetime.now(UTC)
    today = now.astimezone(requirements.IST).date()
    received = select(func.coalesce(func.sum(RecruiterPayment.amount), 0)).where(RecruiterPayment.invoice_id == RecruiterInvoice.id).correlate(RecruiterInvoice).scalar_subquery()
    due = case((Placement.invoice_status == "draft", Placement.draft_due_date), else_=RecruiterInvoice.due_date)
    owing = or_(Placement.invoice_status == "draft", and_(RecruiterInvoice.cancelled_at.is_(None), received < RecruiterInvoice.amount))
    unsent = or_(Placement.due_notified_at.is_(None), and_(Placement.overdue_notified_at.is_(None), due < today))
    counts = {"due": 0, "overdue": 0}
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Placement, due)
                .outerjoin(RecruiterInvoice, RecruiterInvoice.id == Placement.invoice_id)
                .where(Placement.invoice_status.in_(("draft", "issued")), owing, due <= today, unsent)
                .order_by(due, Placement.id)
                .limit(SWEEP_LIMIT)
                .with_for_update(of=Placement, skip_locked=True)
            )
        ).all()
        managers = list(await db.scalars(select(User).where(User.role == MANAGER_ROLE, User.active))) if rows else []
        for placement, due_on in rows:
            recipients = await _recipients(db, placement, managers)
            if placement.due_notified_at is None:
                await notify(db, recipients, DUE, placement.id, action_url=url(placement.id))
                placement.due_notified_at, counts["due"] = now, counts["due"] + 1
            if due_on < today and placement.overdue_notified_at is None:
                await notify(db, recipients, OVERDUE, placement.id, action_url=url(placement.id))
                placement.overdue_notified_at, counts["overdue"] = now, counts["overdue"] + 1
        await db.commit()
    logger.info("placement_invoice_notices_sweep", extra={"extra_fields": counts})
    return counts


# --- audit and log --------------------------------------------------------------------------------------------------------------------
def audit(db: AsyncSession, user: User | None, action: str, placement: Placement, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=f"placement.{action}", entity_type="placement", entity_id=str(placement.id), metadata_json=metadata))


def log(event: str, user: User, placement_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "placement_id": str(placement_id), **{k: str(v) for k, v in extra.items()}}})
