"""rec-007 (DEC-SCOPE-126, spec §5): the Job Requirement -- `jobs` extended (R5), §6 fields, required/preferred skills, statuses + history.

Every `{requirement_id}` resolves through `services.recruiter_requirements.load_scoped` (out of scope = 404); every write is one
transaction -- scope, row lock, change, history/audit, one commit here. Lists are {items, total, limit, offset}, newest first."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import JOB_PRIORITIES, JOB_STATUSES, Company, Job, User
from app.schemas import REC_REQUIREMENT_FIELDS, RecRequirementAssign, RecRequirementCreate, RecRequirementStatusChange, RecRequirementUpdate
from app.services import recruiter_companies as companies
from app.services import recruiter_requirements as svc
from app.services.recruiter import ROLE, recruiter_context

router = APIRouter(prefix="/recruiter/requirements", tags=["recruiter-requirements"])
Recruiter = aliased(User)
ASSIGNED_INVALID = "assigned must be me, unassigned or a recruiter id"


def _assigned(user: User, assigned: str | None) -> list:
    if assigned is None:
        return []
    if assigned == "unassigned":
        return [Job.assigned_recruiter_user_id.is_(None)]
    if assigned == "me":
        if user.role != ROLE:
            raise HTTPException(422, ASSIGNED_INVALID)
        return [Job.assigned_recruiter_user_id == user.id]
    try:
        return [Job.assigned_recruiter_user_id == UUID(assigned)]
    except ValueError:
        raise HTTPException(422, ASSIGNED_INVALID) from None


@router.get("/statuses")
async def requirement_statuses(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.caller_scope(db, user)  # the same role gate as the list
    return svc.catalogue()


@router.get("")
async def list_requirements(
    q: str | None = SEARCH,
    status: Literal[JOB_STATUSES] | None = None,
    company_id: UUID | None = None,
    assigned: str | None = Query(None, max_length=36),
    priority: Literal[JOB_PRIORITIES] | None = None,
    job_category_id: UUID | None = None,
    deadline: Literal["expiring", "expired"] | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they can only narrow it. One query for the page (company + recruiter joined)."""
    filters = await svc.caller_scope(db, user)
    filters += _matching(like_pattern(q), Job.title, Job.requirement_code, Company.name)
    if status:
        filters.append(Job.status == status)
    if company_id:
        filters.append(Job.company_id == company_id)
    if priority:
        filters.append(Job.priority == priority)
    if job_category_id:
        filters.append(Job.job_category_id == job_category_id)
    if deadline:
        filters += svc.deadline_filter(deadline)
    filters += _assigned(user, assigned)
    total = await db.scalar(select(func.count()).select_from(Job).join(Company, Company.id == Job.company_id).where(*filters))
    stmt = (
        select(Job, Company, Recruiter)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(Recruiter, Recruiter.id == Job.assigned_recruiter_user_id)
        .where(*filters)
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return {"items": [svc.row_out(user, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201)
async def create_requirement(payload: RecRequirementCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A recruiter's requirement is their own and is for one of their companies; a manager or super_admin may name a recruiter from the
    team, else the company's recruiter gets it. It starts `new`."""
    svc.require_creator(user)
    if user.role == ROLE:
        await recruiter_context(db, user)
        if payload.assigned_recruiter_user_id not in (None, user.id):
            raise HTTPException(403, "Only a placement manager can choose the recruiter")
    company = await companies.load_scoped(db, user, payload.company_id)  # out of the caller's company scope = 404
    if company.archived_at is not None:
        raise HTTPException(409, "Restore this company before adding a requirement")
    values = payload.model_dump(include=set(REC_REQUIREMENT_FIELDS))
    values["description"] = values["description"] or ""
    values["requirement_date"] = values["requirement_date"] or svc.ist_today()  # J4: the received date, today unless given
    await svc.check_category(db, values, None)
    assignee = user.id if user.role == ROLE else company.assigned_recruiter_user_id
    if user.role != ROLE and payload.assigned_recruiter_user_id:
        assignee = (await companies.locked_recruiter_target(db, user, payload.assigned_recruiter_user_id)).id
    job = Job(
        **values,
        company_id=company.id,
        status="new",
        assigned_recruiter_user_id=assignee,
        created_by_user_id=user.id,
        skills=[],
    )
    db.add(job)
    await db.flush()
    await svc.set_skills(db, job, payload.required_skills or [], payload.preferred_skills or [])
    svc.record_created(db, user, job)
    svc.audit(db, user, "create", job.id, {"code": job.requirement_code, "company_id": str(company.id), "fields": sorted(k for k, v in values.items() if v not in (None, ""))})
    await db.commit()
    svc.log("recruiter_requirement_created", user, job.id)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.get("/{requirement_id}")
async def get_requirement(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await svc.load_scoped(db, user, requirement_id)
    return {"requirement": await svc.requirement_out(db, user, job, refresh=False)}


@router.patch("/{requirement_id}")
async def update_requirement(requirement_id: UUID, payload: RecRequirementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump)."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True)
    svc.require(user, job, "can_edit", "update")
    changes = payload.model_dump(exclude_unset=True, include=set(REC_REQUIREMENT_FIELDS))
    if "description" in changes:
        changes["description"] = changes["description"] or ""
    await svc.check_category(db, changes, job)
    changed = sorted(k for k, v in changes.items() if getattr(job, k) != v)
    for key in changed:
        setattr(job, key, changes[key])
    svc.check_ranges(job)
    if "vacancies" in changed:
        await svc.check_vacancies(db, job)
    fields = payload.model_fields_set
    if ("required_skills" in fields or "preferred_skills" in fields) and await svc.set_skills(
        db, job, payload.required_skills if "required_skills" in fields else None, payload.preferred_skills if "preferred_skills" in fields else None
    ):
        changed.append("skills")
    if changed:
        await db.flush()
        svc.audit(db, user, "update", job.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("recruiter_requirement_updated", user, job.id, fields=changed)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.post("/{requirement_id}/status")
async def change_requirement_status(requirement_id: UUID, payload: RecRequirementStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: every move is a history row (actor, note) in the same transaction; a move not in the table is a 409."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True)
    svc.require(user, job, "can_change_status", "status")
    previous = svc.change_status(db, user, job, payload.status, payload.note)
    svc.audit(db, user, "status", job.id, {"from": previous, "to": payload.status})
    await db.commit()
    svc.log("recruiter_requirement_status_changed", user, job.id, from_status=previous, to_status=payload.status)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.post("/{requirement_id}/assign")
async def assign_requirement(requirement_id: UUID, payload: RecRequirementAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await svc.load_scoped(db, user, requirement_id, lock=True)
    svc.require(user, job, "can_reassign", "assign")
    if payload.recruiter_user_id == job.assigned_recruiter_user_id:
        raise HTTPException(409, "Already assigned to this recruiter")
    target = await companies.locked_recruiter_target(db, user, payload.recruiter_user_id)
    previous = job.assigned_recruiter_user_id
    job.assigned_recruiter_user_id = target.id
    svc.audit(db, user, "assign", job.id, {"from_user_id": str(previous) if previous else None, "to_user_id": str(target.id)})
    await db.commit()
    svc.log("recruiter_requirement_assigned", user, job.id, to_user_id=str(target.id))
    return {"requirement": await svc.requirement_out(db, user, job)}
