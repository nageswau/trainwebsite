"""rec-024 (DEC-SCOPE-127, spec §1-§3): recruiter follow-ups on a company -- rules, the Today / Overdue / Upcoming lists and the output.

A follow-up belongs to its company (FU4): every read and write goes through rec-003's company scope (`caller_scope` / `load_scoped`), so
another recruiter's follow-up is the same 404 as a missing one and a reassigned company's follow-ups move with it. Writes need the
company's `can_edit` (FU3) and lock the company, then the follow-up. Later items (rec-008/019/021/022/023/030) create their automatic
follow-ups through `create` (FU1). Functions only; nothing here commits. Logs and audit carry ids, the reason key and field names --
never notes, outcomes or cancel reasons."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, Company, CompanyContact, Job, JobApplication, RecruiterFollowUp, User
from app.schemas import RecFollowUpCreate
from app.services import recruiter_companies as companies
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_follow_ups import check_due

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Follow-up not found"
STATE_REFUSALS = {"done": "This follow-up is already done", "cancelled": "This follow-up was cancelled"}
OPEN_CAP = 50  # FU8: an abuse bound per company, far above real use
OPEN_CAP_REACHED = f"This company already has {OPEN_CAP} open follow-ups"
CONTACT_INVALID = "Choose an active contact of this company"
JOB_INVALID = "Choose a requirement of this company"
APPLICATION_INVALID = "Choose an application to one of this company's requirements"
APPLICATION_MISMATCH = "The application is for another requirement"
VIEWS = ("today", "overdue", "upcoming")

FU = RecruiterFollowUp
IS_OPEN = FU.status == "open"
Recruiter, Creator, Completer = aliased(User), aliased(User), aliased(User)


def _rows():
    """One query: the follow-up, its company and recruiter, the contact, the requirement, the creator and completer -- no N+1."""
    return (
        select(FU, Company, Recruiter, CompanyContact, Job, Creator, Completer)
        .join(Company, Company.id == FU.company_id)
        .outerjoin(Recruiter, Recruiter.id == Company.assigned_recruiter_user_id)
        .outerjoin(CompanyContact, CompanyContact.id == FU.contact_id)
        .outerjoin(Job, Job.id == FU.job_id)
        .join(Creator, Creator.id == FU.created_by_user_id)
        .outerjoin(Completer, Completer.id == FU.completed_by_user_id)
    )


def _person(user: User | None) -> dict | None:
    return None if user is None else {"id": user.id, "full_name": user.full_name}


def _out(user: User, now: datetime, fu: FU, company: Company, recruiter, contact, job, creator, completer) -> dict:
    return {
        "id": fu.id, "reason": fu.reason, "due_at": fu.due_at, "notes": fu.notes, "status": fu.status, "outcome": fu.outcome,
        "overdue": fu.status == "open" and fu.due_at < now,
        "company": {"id": company.id, "code": company.company_code, "name": company.name, "assigned_recruiter": _person(recruiter)},
        "contact": None if contact is None else {"id": contact.id, "name": contact.name},
        "requirement": None if job is None else {"id": job.id, "title": job.title},
        "application_id": fu.application_id,
        "created_by": _person(creator), "created_at": fu.created_at, "completed_at": fu.completed_at, "completed_by": _person(completer),
        "cancelled_at": fu.cancelled_at, "cancel_reason": fu.cancel_reason,
        "can_change": fu.status == "open" and companies.permissions(user, company)["can_edit"],
    }


async def _page(db: AsyncSession, user: User, now: datetime, where: list, order: tuple, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(FU).join(Company, Company.id == FU.company_id).where(*where))
    rows = (await db.execute(_rows().where(*where).order_by(*order).limit(limit).offset(offset))).tuples().all()
    return {"items": [_out(user, now, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


def views(now: datetime) -> dict:
    """FU2, in IST: Today = due before tonight's midnight (due today + overdue, AC1); Overdue = past due; Upcoming = from tomorrow."""
    _, tonight = day_range(today_ist(now))
    return {"today": IS_OPEN & (FU.due_at < tonight), "overdue": IS_OPEN & (FU.due_at < now), "upcoming": IS_OPEN & (FU.due_at >= tonight)}


async def list_page(db: AsyncSession, user: User, due: str, now: datetime, limit: int, offset: int) -> dict:
    """The caller's lists, oldest due first; the counts are the three views' totals, so the tabs agree with the lists."""
    scope = await companies.caller_scope(db, user)
    conditions = views(now)
    out = await _page(db, user, now, [*scope, conditions[due]], (FU.due_at, FU.id), limit, offset)
    counts = (await db.execute(
        select(*(func.count().filter(c) for c in conditions.values())).select_from(FU).join(Company, Company.id == FU.company_id).where(*scope)
    )).one()
    return {**out, "day": today_ist(now), "counts": {view: n or 0 for view, n in zip(conditions, counts, strict=True)}}


async def company_page(db: AsyncSession, user: User, company_id: UUID, now: datetime, limit: int, offset: int) -> dict:
    """A company's follow-ups: open ones by due time, then done / cancelled newest first."""
    order = (case((IS_OPEN, 0), else_=1), case((IS_OPEN, FU.due_at)).asc(), func.coalesce(FU.completed_at, FU.cancelled_at).desc(), FU.id)
    return await _page(db, user, now, [FU.company_id == company_id], order, limit, offset)


async def one(db: AsyncSession, user: User, fu_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows().where(FU.id == fu_id).execution_options(populate_existing=True))).tuples().one()
    return _out(user, now, *row)


async def check_links(db: AsyncSession, company_id: UUID, values: dict, stored: FU | None = None) -> None:
    """FU6: each link set or changed must belong to the company (a contact must also be active); an application and a requirement sent
    together must agree. Keeping a stored link is allowed (a since-deactivated contact stays)."""

    def changed(key: str) -> bool:
        return values.get(key) is not None and (stored is None or getattr(stored, key) != values[key])

    if changed("contact_id"):
        contact = await db.scalar(select(CompanyContact).where(CompanyContact.id == values["contact_id"], CompanyContact.company_id == company_id))
        if contact is None or not contact.active:
            raise HTTPException(422, CONTACT_INVALID)
    if changed("job_id") and await db.scalar(select(Job.id).where(Job.id == values["job_id"], Job.company_id == company_id)) is None:
        raise HTTPException(422, JOB_INVALID)
    job_id = values["job_id"] if "job_id" in values else (stored.job_id if stored else None)
    application_id = values["application_id"] if "application_id" in values else (stored.application_id if stored else None)
    if application_id is not None and (changed("application_id") or changed("job_id")):
        application_job = await db.scalar(
            select(JobApplication.job_id).join(Job, Job.id == JobApplication.job_id).where(JobApplication.id == application_id, Job.company_id == company_id)
        )
        if application_job is None:
            raise HTTPException(422, APPLICATION_INVALID)
        if job_id is not None and application_job != job_id:
            raise HTTPException(422, APPLICATION_MISMATCH)


async def create(db: AsyncSession, user: User, company: Company, payload: RecFollowUpCreate, now: datetime) -> FU:
    """The caller locked the company and checked `can_edit`. FU5 time; FU8 cap (counted under the company lock, so exact); FU6 links."""
    check_due(payload.due_at, now)
    if (await db.scalar(select(func.count()).select_from(FU).where(FU.company_id == company.id, IS_OPEN)) or 0) >= OPEN_CAP:
        raise HTTPException(409, OPEN_CAP_REACHED)
    values = payload.model_dump()
    await check_links(db, company.id, values)
    fu = FU(company_id=company.id, created_by_user_id=user.id, **values)
    db.add(fu)
    await db.flush()
    links = sorted(k for k in ("contact_id", "job_id", "application_id") if values[k] is not None)
    audit(db, user, "create", fu.id, {"company_id": str(company.id), "reason": fu.reason, "links": links})
    return fu


async def load_for_write(db: AsyncSession, user: User, fu_id: UUID, route: str) -> tuple[Company, FU]:
    """In scope (404) -> company lock -> `can_edit` (403, then 409 when archived) -> follow-up lock -> open (409)."""
    company_id = await db.scalar(select(FU.company_id).where(FU.id == fu_id))
    if company_id is None:
        raise HTTPException(404, NOT_FOUND)
    try:
        company = await companies.load_scoped(db, user, company_id, lock=True)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, NOT_FOUND) from None
        raise
    companies.require(user, company, "can_edit", route)
    fu = await db.scalar(select(FU).where(FU.id == fu_id).with_for_update().execution_options(populate_existing=True))
    if fu is None:  # never in practice (follow-ups are not deleted); narrows the type without an assert
        raise HTTPException(404, NOT_FOUND)
    if fu.status != "open":
        raise HTTPException(409, STATE_REFUSALS[fu.status])
    return company, fu


async def contact_next(db: AsyncSession, company_id: UUID) -> dict[UUID, datetime]:
    """FU9: each contact's earliest open follow-up -- one query for the company's contact list."""
    rows = await db.execute(
        select(FU.contact_id, func.min(FU.due_at)).where(FU.company_id == company_id, FU.contact_id.is_not(None), IS_OPEN).group_by(FU.contact_id)
    )
    return dict(rows.tuples().all())


def audit(db: AsyncSession, user: User, action: str, fu_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_follow_up.{action}", entity_type="recruiter_follow_up", entity_id=str(fu_id), metadata_json=metadata or {}))


def log(event: str, user: User, fu_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "follow_up_id": str(fu_id), **extra}})
