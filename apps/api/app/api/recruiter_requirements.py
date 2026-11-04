"""rec-007 (DEC-SCOPE-129, spec §5): the Job Requirement -- `jobs` extended (R5), §6 fields, required/preferred skills, statuses + history.

Every `{requirement_id}` resolves through `services.recruiter_requirements.load_scoped` (out of scope = 404); every write is one
transaction -- scope, row lock, change, history/audit, one commit here. Lists are {items, total, limit, offset}, newest first."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user, require_permission
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import JOB_ASSIGNMENT_ROLES, JOB_PRIORITIES, JOB_STATUSES, Company, Job, JobApprovalSetting, JobSkill, User
from app.schemas import (
    REC_REQUIREMENT_FIELDS,
    JobApprovalSettingsUpdate,
    RecRequirementApprovalNote,
    RecRequirementAssign,
    RecRequirementCreate,
    RecRequirementOwnerAdd,
    RecRequirementReject,
    RecRequirementStatusChange,
    RecRequirementUpdate,
    RecRequirementVisibility,
    RecSkillWeights,
)
from app.services import applications, candidates, matching, recruitment_history
from app.services import recruiter_companies as companies
from app.services import recruiter_requirements as svc
from app.services import requirement_owners as owners
from app.services.recruiter import ROLE, recruiter_context
from app.services.stale_guard import require_fresh

router = APIRouter(prefix="/recruiter/requirements", tags=["recruiter-requirements"])
# hrc-007 (DEC-SCOPE-380 A9): the approval queue and the per-source settings, for `jobs.approve` holders.
approvals_router = APIRouter(prefix="/recruiter/requirement-approvals", tags=["recruiter-requirements"])
NO_APPROVE = "You cannot approve job requirements"
APPROVER = require_permission("jobs", "approve", NO_APPROVE)
PUBLISHER = require_permission("jobs", "publish", "You cannot change who sees job requirements")  # hrc-008 (V4)
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
    await svc.caller_scope(db, user, officers=True)  # the same role gate as the list (hrc-006: a placement officer reads its own)
    return svc.catalogue()


@router.get("/hiring-managers")
async def hiring_managers(q: str | None = SEARCH, limit: int = Query(20, ge=1, le=50), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-005 (V2): the hiring-manager picker -- active internal interviewers, for the roles that write requirements."""
    svc.require_creator(user)
    filters = [User.role == svc.HIRING_MANAGER_ROLE, User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)]
    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    rows = (await db.scalars(select(User).where(*filters).order_by(User.full_name, User.id).limit(limit))).all()
    return {"items": [{"id": u.id, "full_name": u.full_name, "email": u.email} for u in rows], "total": total or 0}


def _audit_override(db: AsyncSession, user: User, job: Job, codes: list[str], reason: str | None) -> None:
    """hrc-005 (V5, AC3): saved despite possible duplicates -- the reason and the matches, in the write's transaction."""
    if codes:
        svc.audit(db, user, "duplicate_override", job.id, {"match_count": len(codes), "match_codes": codes, "reason": reason})


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
    filters = await svc.caller_scope(db, user, officers=True)
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
    await svc.check_references(db, values, None)
    assignee = user.id if user.role == ROLE else company.assigned_recruiter_user_id
    if user.role != ROLE and payload.assigned_recruiter_user_id:
        assignee = (await companies.locked_recruiter_target(db, user, payload.assigned_recruiter_user_id)).id
    job = Job(
        **values,
        company_id=company.id,
        status="new",
        assigned_recruiter_user_id=assignee,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
        skills=[],
    )
    svc.settle_location(job)  # hrc-005 V3
    overrides = await svc.check_duplicates(db, job, payload.duplicate_reason)  # V5: a 409 unless a reason is given
    db.add(job)
    await db.flush()
    await svc.set_skills(db, job, payload.required_skills or [], payload.preferred_skills or [])
    await svc.record_created(db, user, job)
    svc.audit(db, user, "create", job.id, {"code": job.requirement_code, "company_id": str(company.id), "fields": sorted(k for k, v in values.items() if v not in (None, ""))})
    _audit_override(db, user, job, overrides, payload.duplicate_reason)
    await db.commit()
    svc.log("recruiter_requirement_created", user, job.id)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.get("/{requirement_id}")
async def get_requirement(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await svc.load_scoped(db, user, requirement_id, officers=True)
    return {"requirement": await svc.requirement_out(db, user, job, refresh=False)}


@router.get("/{requirement_id}/history")
async def requirement_history(requirement_id: UUID, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = OFFSET,
                              user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-004 (DEC-SCOPE-376 B1/B6): the requirement's and its JD's changes with before/after values, for its readers (scope = 404)."""
    job = await svc.load_scoped(db, user, requirement_id, officers=True)
    response.headers.update(NO_STORE)
    return await recruitment_history.history(db, "job", job.id, ("recruiter_requirement.", "job_description."), limit=limit, offset=offset)


@router.patch("/{requirement_id}")
async def update_requirement(requirement_id: UUID, payload: RecRequirementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump)."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True, officers=True)
    svc.require(user, job, "can_edit", "update")
    await require_fresh(db, stored=job.updated_at, expected=payload.expected_updated_at, entity=("job", job.id), action_prefix="recruiter_requirement.",
                        since=payload.expected_updated_at, current=lambda: svc.requirement_out(db, user, job, refresh=False))
    changes = payload.model_dump(exclude_unset=True, include=set(REC_REQUIREMENT_FIELDS))
    if "description" in changes:
        changes["description"] = changes["description"] or ""
    await svc.check_references(db, changes, job)
    changed = sorted(k for k, v in changes.items() if getattr(job, k) != v)
    old_location, old_place = job.location, svc.place_text(job.city, job.state, job.country)
    fields = payload.model_fields_set
    skills_sent = "required_skills" in fields or "preferred_skills" in fields
    before = await svc.audited_values(db, job, changed, skills=skills_sent)  # hrc-004: the stored values, for the audit diff
    for key in changed:
        setattr(job, key, changes[key])
    if {"location", "city", "state", "country"} & set(changed):  # hrc-005 V3: a derived location follows its parts; a typed one stays
        svc.settle_location(job, None if "location" in changed else old_place)
        if job.location != old_location and "location" not in changed:
            before["location"] = old_location
            changed.append("location")
    overrides = await svc.check_duplicates(db, job, payload.duplicate_reason, job.id) if svc.DUPLICATE_FIELDS & set(changed) else []
    svc.check_ranges(job)
    if "vacancies" in changed:
        await svc.check_vacancies(db, job)
    if skills_sent and await svc.set_skills(
        db, job, payload.required_skills if "required_skills" in fields else None, payload.preferred_skills if "preferred_skills" in fields else None
    ):
        changed.append("skills")
    if changed:
        job.updated_at = func.now()  # hrc-003 S1: a skills-only change (a child table) moves the token too
        job.updated_by_user_id = user.id  # hrc-005 V6
        await db.flush()
        after = await svc.audited_values(db, job, [k for k in changed if k != "skills"], skills=skills_sent)
        svc.audit(db, user, "update", job.id, {"fields": changed, "changes": recruitment_history.diff(before, after)})
        _audit_override(db, user, job, overrides, payload.duplicate_reason)
    await db.commit()
    if changed:
        svc.log("recruiter_requirement_updated", user, job.id, fields=changed)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.post("/{requirement_id}/status")
async def change_requirement_status(requirement_id: UUID, payload: RecRequirementStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: every move is a history row (actor, note) in the same transaction; a move not in the table is a 409."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True, officers=True)
    svc.require(user, job, "can_change_status", "status")
    previous = await svc.change_status(db, user, job, payload.status, payload.note)
    job.updated_by_user_id = user.id
    svc.audit(db, user, "status", job.id, {"from": previous, "to": payload.status, "changes": {"status": [previous, payload.status]}})
    await db.commit()
    svc.log("recruiter_requirement_status_changed", user, job.id, from_status=previous, to_status=payload.status)
    return {"requirement": await svc.requirement_out(db, user, job)}


# --- hrc-007 (DEC-SCOPE-380): submit, approve, reject ------------------------------------------------------------------------------
@router.post("/{requirement_id}/submit")
async def submit_requirement(requirement_id: UUID, payload: RecRequirementApprovalNote, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A6: the requirement's writer sends a Draft / On Hold job for approval (409 when its source needs none)."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True, officers=True)
    svc.require(user, job, "can_edit", "submit")
    await svc.submit(db, user, job, payload.note)  # history + audit
    await db.commit()
    svc.log("recruiter_requirement_submitted", user, job.id)
    return {"requirement": await svc.requirement_out(db, user, job)}


async def _decide(db: AsyncSession, user: User, requirement_id: UUID, approve: bool, note: str | None) -> dict:
    """A8: grant (the dependency, 403) -> exists (404) -> pending (409) -> not one's own (403); one transaction."""
    job = await svc.load_for_approver(db, requirement_id)
    previous = await svc.decide(db, user, job, approve, note)
    action = "approve" if approve else "reject"
    svc.audit(db, user, action, job.id, {"from": previous, "to": job.status, "note": note, "changes": {"status": [previous, job.status]}})
    await db.commit()
    svc.log(f"recruiter_requirement_{action}d", user, job.id)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.post("/{requirement_id}/approve")
async def approve_requirement(requirement_id: UUID, payload: RecRequirementApprovalNote, user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, requirement_id, True, payload.note)


@router.post("/{requirement_id}/reject")
async def reject_requirement(requirement_id: UUID, payload: RecRequirementReject, user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, requirement_id, False, payload.reason)


# --- hrc-008 (DEC-SCOPE-385 V7): who sees the job --------------------------------------------------------------------------------------
@router.put("/{requirement_id}/visibility")
async def change_requirement_visibility(requirement_id: UUID, payload: RecRequirementVisibility, user: User = Depends(PUBLISHER), db: AsyncSession = Depends(get_db)):
    """Grant (the dependency, 403) -> exists (404, any job: the grant is division-wide like `jobs.approve`) -> an active pool (422)."""
    job = await svc.load_for_approver(db, requirement_id)
    changes = await svc.set_visibility(db, user, job, payload.visibility, payload.segment_pool_id)
    await db.commit()
    if changes:
        svc.log("recruiter_requirement_visibility_changed", user, job.id, visibility=job.visibility)
    return {"requirement": await svc.requirement_out(db, user, job)}


@approvals_router.get("")
async def approval_queue(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    """A9: every pending job, oldest submission first; `can_decide` is false on the caller's own."""
    pending = Job.status == "pending_approval"
    total = await db.scalar(select(func.count()).select_from(Job).where(pending))
    Submitter = aliased(User)
    stmt = (
        select(Job, Company, Recruiter, Submitter)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(Recruiter, Recruiter.id == Job.assigned_recruiter_user_id)
        .outerjoin(Submitter, Submitter.id == Job.submitted_by_user_id)
        .where(pending)
        .order_by(Job.submitted_at.asc().nulls_last(), Job.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        {**svc.row_out(user, job, company, recruiter), "description": job.description, "submitted_by": companies.person(submitter),
         "submitted_at": job.submitted_at, "can_decide": not svc.is_own(user, job)}
        for job, company, recruiter, submitter in (await db.execute(stmt)).all()
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@approvals_router.get("/settings")
async def approval_settings(user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    return {"settings": await svc.approval_settings(db), "can_edit": user.role == "super_admin"}


@approvals_router.put("/settings")
async def update_approval_settings(payload: JobApprovalSettingsUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A4/A10: super_admin only. Turning a source off never opens its pending jobs."""
    if user.role != "super_admin":
        raise HTTPException(403, "Only a super admin can change the approval settings")
    before = await svc.approval_settings(db)
    sent = payload.model_dump(exclude_unset=True, exclude_none=True)
    changed = {k: v for k, v in sent.items() if before[k] != v}
    for source, required in changed.items():
        row = await db.get(JobApprovalSetting, source, with_for_update=True)
        if row is None:
            db.add(JobApprovalSetting(source=source, required=required, updated_by_user_id=user.id))
        else:
            row.required, row.updated_by_user_id = required, user.id
    if changed:
        svc.audit_settings(db, user, {k: [before[k], v] for k, v in changed.items()})
    await db.commit()
    return {"settings": await svc.approval_settings(db), "can_edit": True}


@router.get("/{requirement_id}/matches")
async def requirement_matches(
    requirement_id: UUID,
    limit: int = Query(matching.PAGE_SIZE, ge=1, le=50),
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """rec-016 (DEC-SCOPE-157 M7): candidate readers within the requirement's scope -- the role check first (403), then scope (404)."""
    candidates.require_reader(user)
    job = await svc.load_scoped(db, user, requirement_id)
    result = await matching.matches(db, job, limit=limit, offset=offset)
    matching.log(user, job, result["total"])
    return {
        **result,
        "can_shortlist": applications.can_write(user) and job.status not in svc.ENDED,  # rec-017's add rules
        "can_edit_weights": svc.permissions(user, job)["can_edit"],
    }


@router.put("/{requirement_id}/skill-weights")
async def set_skill_weights(requirement_id: UUID, payload: RecSkillWeights, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """rec-016 (M1): one transaction -- scope, row lock, `can_edit`, the changed weights and one audit row (ids only), one commit.
    hrc-017 (T6): an item may also set `min_level` (omitted = unchanged, null = any level) on a Skills-Master skill; the audit row then
    carries the level diff by skill name."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True)
    svc.require(user, job, "can_edit", "skill_weights")
    rows = {r.id: r for r in (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id))).all()}
    if any(w.id not in rows for w in payload.weights):
        raise HTTPException(422, "Choose skills of this requirement")
    levels = {w.id: w.min_level for w in payload.weights if "min_level" in w.model_fields_set and rows[w.id].min_level != w.min_level}
    if any(level and rows[i].skill_id is None for i, level in levels.items()):
        raise HTTPException(422, "Only a skill in the Skills Master can have a minimum level")
    changed = sorted(str(w.id) for w in payload.weights if rows[w.id].weight != w.weight or w.id in levels)
    changes = {f"{rows[i].name} minimum level": [rows[i].min_level, level] for i, level in levels.items()}
    for w in payload.weights:
        rows[w.id].weight = w.weight
        rows[w.id].min_level = levels.get(w.id, rows[w.id].min_level)
    if changed:
        svc.audit(db, user, "weights", job.id, {"skills": changed, **({"changes": changes} if changes else {})})
    await db.commit()
    if changed:
        svc.log("recruiter_requirement_weights_changed", user, job.id, skills=len(changed))
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.post("/{requirement_id}/assign")
async def assign_requirement(requirement_id: UUID, payload: RecRequirementAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await svc.load_scoped(db, user, requirement_id, lock=True)
    svc.require(user, job, "can_reassign", "assign")
    if payload.recruiter_user_id == job.assigned_recruiter_user_id:
        raise HTTPException(409, "Already assigned to this recruiter")
    target = await companies.locked_recruiter_target(db, user, payload.recruiter_user_id)
    previous = job.assigned_recruiter_user_id
    await owners.set_primary(db, user, job, target.id)  # hrc-006 (O7): history; a collaborator promoted gives up that role
    job.updated_by_user_id = user.id
    svc.audit(db, user, "assign", job.id, {"from_user_id": str(previous) if previous else None, "to_user_id": str(target.id),
                                           "changes": {"recruiter": [await svc.recruiter_name(db, previous), target.full_name]}})
    await db.commit()
    svc.log("recruiter_requirement_assigned", user, job.id, to_user_id=str(target.id))
    return {"requirement": await svc.requirement_out(db, user, job)}


# --- hrc-006 (DEC-SCOPE-384 O3-O11): co-owners and the ownership history ---------------------------------------------------------
@router.get("/{requirement_id}/assignment-options")
async def assignment_options(requirement_id: UUID, role: Literal[JOB_ASSIGNMENT_ROLES], q: str | None = SEARCH, limit: int = Query(20, ge=1, le=50),
                             user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    """The owner picker, for those who manage the owners: eligible active people not already on the requirement."""
    job = await svc.load_scoped(db, user, requirement_id, officers=True)
    svc.require(user, job, "can_manage_owners", "assignment_options")
    return await owners.options(db, job, role, _matching(like_pattern(q), User.full_name, User.email), limit)


@router.get("/{requirement_id}/assignment-history")
async def assignment_history(requirement_id: UUID, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = OFFSET,
                             user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    """AC3: every add, remove and primary change with actor and time, newest first, for the requirement's readers."""
    job = await svc.load_scoped(db, user, requirement_id, officers=True)
    response.headers.update(NO_STORE)
    return await owners.history(db, job.id, limit=limit, offset=offset)


@router.post("/{requirement_id}/assignments", status_code=201)
async def add_owner(requirement_id: UUID, payload: RecRequirementOwnerAdd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One transaction: scope, the job row lock, who may manage (403), cancelled (409), the target (O3), history and audit."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True, officers=True)
    svc.require(user, job, "can_manage_owners", "assignment_add")
    target = await owners.add(db, user, job, payload.user_id, payload.role)
    job.updated_by_user_id = user.id
    svc.audit(db, user, "owner_added", job.id, {"user_id": str(target.id), "role": payload.role, "changes": {owners.ROLE_LABELS[payload.role]: [None, target.full_name]}})
    await db.commit()
    svc.log("recruiter_requirement_owner_added", user, job.id, user_id=str(target.id), role=payload.role)
    return {"requirement": await svc.requirement_out(db, user, job)}


@router.delete("/{requirement_id}/assignments/{user_id}")
async def remove_owner(requirement_id: UUID, user_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """O6: never the primary (409); someone not on the requirement is 404."""
    job = await svc.load_scoped(db, user, requirement_id, lock=True, officers=True)
    svc.require(user, job, "can_manage_owners", "assignment_remove")
    target, role = await owners.remove(db, user, job, user_id)
    job.updated_by_user_id = user.id
    svc.audit(db, user, "owner_removed", job.id, {"user_id": str(user_id), "role": role, "changes": {owners.ROLE_LABELS[role]: [target.full_name, None]}})
    await db.commit()
    svc.log("recruiter_requirement_owner_removed", user, job.id, user_id=str(user_id), role=role)
    return {"requirement": await svc.requirement_out(db, user, job)}
