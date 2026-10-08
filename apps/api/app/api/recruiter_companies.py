"""rec-003 (DEC-SCOPE-121, spec §5): the recruiter company master -- the lead and the company are one `companies` row (R3).

Every `{company_id}` resolves through `services.recruiter_companies.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, change, audit, one commit here. Lists are {items, total, limit, offset}, ordered by name then id."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import Company, RecIndustry, RecLeadSource, User
from app.schemas import (
    REC_COMPANY_FIELDS,
    RecBdmOptionPage,
    RecCompanyAssign,
    RecCompanyCreate,
    RecCompanyEnvelope,
    RecCompanyPage,
    RecCompanyPriority,
    RecCompanyUpdate,
)
from app.services import recruiter_companies as svc
from app.services import recruiter_contacts
from app.services.recruiter import ROLE, recruiter_context

router = APIRouter(prefix="/recruiter/companies", tags=["recruiter-companies"])
Recruiter = aliased(User)
ASSIGNED_INVALID = "assigned must be me, unassigned or a recruiter id"
NAME_TAKEN = "A company with this name already exists"


def _assigned(user: User, assigned: str | None) -> list:
    if assigned is None:
        return []
    if assigned == "unassigned":
        return [Company.assigned_recruiter_user_id.is_(None)]
    if assigned == "me":
        if user.role != ROLE:
            raise HTTPException(422, ASSIGNED_INVALID)
        return [Company.assigned_recruiter_user_id == user.id]
    try:
        return [Company.assigned_recruiter_user_id == UUID(assigned)]
    except ValueError:
        raise HTTPException(422, ASSIGNED_INVALID) from None


async def _flush(db: AsyncSession) -> None:
    """A concurrent create of the same exact name loses to the unique constraint: the same 409 as the pre-check."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "companies_name_key" in str(exc.orig):
            raise HTTPException(409, NAME_TAKEN) from None
        raise


@router.get("", response_model=RecCompanyPage)
async def list_companies(
    q: str | None = SEARCH,
    priority: RecCompanyPriority | None = None,
    lead_source_id: UUID | None = None,
    industry_id: UUID | None = None,
    city: str | None = Query(None, max_length=120),
    assigned: str | None = Query(None, max_length=36),
    include_archived: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they can only narrow it. One query: catalogue values + recruiter (no N+1)."""
    filters = await svc.caller_scope(db, user)
    if not include_archived:
        filters.append(Company.archived_at.is_(None))
    filters += _matching(like_pattern(q), Company.name, Company.company_code)
    filters += _matching(like_pattern(city), Company.city)
    if priority:
        filters.append(Company.priority == priority)
    if lead_source_id:
        filters.append(Company.lead_source_id == lead_source_id)
    if industry_id:
        filters.append(Company.industry_id == industry_id)
    filters += _assigned(user, assigned)
    total = await db.scalar(select(func.count()).select_from(Company).where(*filters))
    stmt = (
        select(Company, RecIndustry, RecLeadSource, Recruiter)
        .outerjoin(RecIndustry, RecIndustry.id == Company.industry_id)
        .outerjoin(RecLeadSource, RecLeadSource.id == Company.lead_source_id)
        .outerjoin(Recruiter, Recruiter.id == Company.assigned_recruiter_user_id)
        .where(*filters)
        .order_by(func.lower(Company.name), Company.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return {"items": [svc.row_out(user, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get("/bdm-options", response_model=RecBdmOptionPage)
async def bdm_options(q: str | None = SEARCH, limit: int = LIMIT, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The Assigned BDM picker: active `bdm` users, names only (R10). For the people who can create or edit a company."""
    svc.require_creator(user)
    filters = [User.role == "bdm", User.active.is_(True), *_matching(like_pattern(q), User.full_name)]
    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    rows = (await db.scalars(select(User).where(*filters).order_by(func.lower(User.full_name), User.id).limit(limit))).all()
    return {"items": [{"id": u.id, "full_name": u.full_name} for u in rows], "total": total or 0}


@router.post("", status_code=201, response_model=RecCompanyEnvelope)
async def create_company(payload: RecCompanyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1: a recruiter's company is their own; a manager or super_admin may name a recruiter from their team, else it is unassigned.
    A likely duplicate is a 409 the user must acknowledge with confirm_duplicate (D2)."""
    svc.require_creator(user)
    if user.role == ROLE:
        await recruiter_context(db, user)  # a recruiter without a profile is 403
        if payload.assigned_recruiter_user_id not in (None, user.id):
            raise HTTPException(403, "Only a placement manager can choose the recruiter")
    values = payload.model_dump(include=set(REC_COMPANY_FIELDS))
    await svc.check_references(db, values, None)
    target = None
    if user.role != ROLE and payload.assigned_recruiter_user_id:
        target = await svc.locked_recruiter_target(db, user, payload.assigned_recruiter_user_id)
    overrides = await svc.check_name(db, payload.name, payload.confirm_duplicate)
    company = Company(**values, created_by_user_id=user.id)
    if user.role == ROLE:
        company.assigned_recruiter_user_id = user.id
    db.add(company)
    await _flush(db)
    if target is not None:
        svc.record_assignment(db, user, company, target.id)
    svc.audit(db, user, "create", company.id, {"code": company.company_code, "fields": sorted(k for k, v in values.items() if v is not None)})
    if overrides:
        svc.audit(db, user, "duplicate_override", company.id, {"match_count": overrides})
    if payload.contact:  # rec-004 C7 "+ Add Recruiter": the first contact (primary) in the same transaction
        await recruiter_contacts.add(db, user, company, payload.contact)
    await db.commit()
    svc.log("recruiter_company_created", user, company.id, duplicate_override=bool(overrides), with_contact=payload.contact is not None)
    return {"company": await svc.company_out(db, user, company)}


@router.get("/{company_id}", response_model=RecCompanyEnvelope)
async def get_company(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    company = await svc.load_scoped(db, user, company_id)
    return {"company": await svc.company_out(db, user, company, refresh=False)}


@router.patch("/{company_id}", response_model=RecCompanyEnvelope)
async def update_company(company_id: UUID, payload: RecCompanyUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump). A changed name re-runs the
    duplicate check."""
    company = await svc.load_scoped(db, user, company_id, lock=True)
    svc.require(user, company, "can_edit", "update")
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
    await svc.check_references(db, changes, company)
    changed = sorted(k for k, v in changes.items() if getattr(company, k) != v)
    overrides = await svc.check_name(db, changes["name"], payload.confirm_duplicate, company.id) if "name" in changed else 0
    if changed:
        for key in changed:
            setattr(company, key, changes[key])
        await _flush(db)
        svc.audit(db, user, "update", company.id, {"fields": changed})
        if overrides:
            svc.audit(db, user, "duplicate_override", company.id, {"match_count": overrides})
    await db.commit()
    if changed:
        svc.log("recruiter_company_updated", user, company.id, fields=changed)
    return {"company": await svc.company_out(db, user, company)}


async def _set_archived(company_id: UUID, user: User, db: AsyncSession, archive: bool) -> dict:
    company = await svc.load_scoped(db, user, company_id, lock=True)
    action = "archive" if archive else "restore"
    svc.require(user, company, "can_archive" if archive else "can_restore", action)
    company.archived_at = datetime.now(UTC) if archive else None
    svc.audit(db, user, action, company.id)
    await db.commit()
    svc.log(f"recruiter_company_{action}d", user, company.id)
    return {"company": await svc.company_out(db, user, company)}


@router.post("/{company_id}/archive", response_model=RecCompanyEnvelope)
async def archive_company(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(company_id, user, db, True)


@router.post("/{company_id}/restore", response_model=RecCompanyEnvelope)
async def restore_company(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(company_id, user, db, False)


@router.post("/{company_id}/assign", response_model=RecCompanyEnvelope)
async def assign_company(company_id: UUID, payload: RecCompanyAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3: the manager (or super_admin) hands the company to a recruiter; the history row and the audit share the transaction."""
    company = await svc.load_scoped(db, user, company_id, lock=True)
    svc.require(user, company, "can_reassign", "assign")
    if payload.recruiter_user_id == company.assigned_recruiter_user_id:
        raise HTTPException(409, "Already assigned to this recruiter")
    target = await svc.locked_recruiter_target(db, user, payload.recruiter_user_id)
    previous = company.assigned_recruiter_user_id
    svc.record_assignment(db, user, company, target.id)
    svc.audit(db, user, "assign", company.id, {"from_user_id": str(previous) if previous else None, "to_user_id": str(target.id)})
    await db.commit()
    svc.log("recruiter_company_assigned", user, company.id, to_user_id=str(target.id))
    return {"company": await svc.company_out(db, user, company)}
