"""rec-007 (DEC-SCOPE-129, spec §2-§4): the Job Requirement's statuses, legacy shim, skills, scope, permissions and output.

Functions only; nothing here commits -- the route owns the transaction. Every `{requirement_id}` resolves through `load_scoped`, so an id
outside the caller's scope is the same 404 as a missing one (the rec-003 pattern). The employer and /workflows/it/jobs routes reuse the
status and skills functions, so every writer records history and keeps the `jobs.skills` mirror in step (J3, J7)."""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    JOB_EMPLOYMENT_TYPES,
    JOB_OPEN_STATUSES,
    JOB_PRIORITIES,
    JOB_SHIFTS,
    JOB_STATUSES,
    JOB_WORK_MODES,
    AuditLog,
    Company,
    Job,
    JobApplication,
    JobSkill,
    JobStatusHistory,
    RecJobCategory,
    RecruiterProfile,
    User,
)
from app.services import company_pipeline
from app.services import skills as skills_master
from app.services.bdm_appointments import IST
from app.services.recruiter import MANAGER_ROLE, ROLE, recruiter_context
from app.services.recruiter_companies import person, ref

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Job requirement not found"
EXPIRING_DAYS = 7  # J4 (Q-05)
HIRED_APPLICATION_STATUSES = ("joined",)  # rec-017 A1: the legacy "hired" is Joined (workflows.update_job_offer follows an accepted offer there)
STATUS_LABELS = {
    "new": "New", "requirement_received": "Requirement Received", "sourcing": "Sourcing", "shortlisting": "Shortlisting",
    "profiles_shared": "Profiles Shared", "interviewing": "Interviewing", "selected": "Selected", "joined": "Joined", "on_hold": "On Hold",
    "closed": "Closed", "cancelled": "Cancelled",
}
_ACTIVE = (*JOB_OPEN_STATUSES, "selected")
ENDED = ("closed", "cancelled")  # a requirement no longer live for the company stage (rec-005's `requirement_closed`)
TRANSITIONS = {  # spec §2; nothing ever returns to `new`, and `cancelled` is terminal
    "new": ("requirement_received", "on_hold", "closed", "cancelled"),
    **{s: (*(a for a in _ACTIVE if a != s), *(("joined",) if s == "selected" else ()), "on_hold", "closed", "cancelled") for s in _ACTIVE},
    "joined": ("closed",),
    "on_hold": (*_ACTIVE, "closed", "cancelled"),
    "closed": ("requirement_received",),
    "cancelled": (),
}
VOCABULARIES = {"work_mode": JOB_WORK_MODES, "shift": JOB_SHIFTS, "employment_type": JOB_EMPLOYMENT_TYPES, "priority": JOB_PRIORITIES}
REFUSALS = {
    "can_edit": "Only the recruiter on this requirement can edit it",
    "can_change_status": "Only the recruiter on this requirement can change its status",
    "can_reassign": "Only a placement manager can reassign this requirement",
}
DEFAULT_WEIGHT = {"required": 2, "preferred": 1}
LEGACY_WORDS = ("draft", "open", "closed")  # J3: what the employer and /workflows/it/jobs routes have always accepted


# --- statuses and the legacy shim (J1-J3) -------------------------------------------------------------------------------------------
def is_open(job: Job, today: date | None = None) -> bool:
    today = today or ist_today()
    return job.status in JOB_OPEN_STATUSES and (job.closes_on is None or job.closes_on >= today)


def ist_today() -> date:
    return datetime.now(IST).date()


def legacy_word(status: str) -> str:
    """The employer API's `status` (J3): draft / open / closed."""
    if status in ("new", "on_hold"):
        return "draft"
    return "open" if status in JOB_OPEN_STATUSES else "closed"


def legacy_target(current: str, word: str) -> str | None:
    """The §6 status a legacy draft/open/closed write means from `current`; None = already there (no change)."""
    if word == "draft":
        return None if current in ("new", "on_hold") else "on_hold"
    if word == "open":
        return None if current in JOB_OPEN_STATUSES else "requirement_received"
    return None if current in ("closed", "cancelled", "joined") else "closed"


def check_transition(current: str, target: str) -> None:
    if target == current:
        raise HTTPException(409, f"The requirement is already {STATUS_LABELS[current]}")
    if target not in TRANSITIONS[current]:
        raise HTTPException(409, f"A requirement cannot move from {STATUS_LABELS[current]} to {STATUS_LABELS[target]}")


async def change_status(db: AsyncSession, user: User | None, job: Job, target: str, note: str | None = None) -> str:
    """Validated move + history row + the company stage; returns the previous status."""
    check_transition(job.status, target)
    previous = job.status
    db.add(JobStatusHistory(job_id=job.id, from_status=previous, to_status=target, note=note, changed_by_user_id=user.id if user else None))
    job.status = target
    await drive_company_stage(db, user, job)
    return previous


async def record_created(db: AsyncSession, user: User, job: Job, note: str = "Created") -> None:
    db.add(JobStatusHistory(job_id=job.id, from_status=None, to_status=job.status, note=note, changed_by_user_id=user.id))
    await drive_company_stage(db, user, job)


async def drive_company_stage(db: AsyncSession, user: User | None, job: Job) -> None:
    """AC2 through rec-005's engine: a requirement reaching Requirement Received fires `requirement_received`; closing or cancelling the
    company's last live requirement fires `requirement_closed`. The company row is locked first (company_pipeline's contract), so two
    requirements closed at once serialise and the second one sees the first as closed. `apply_event` ignores a stage already past."""
    if job.status == "requirement_received":
        event = "requirement_received"
    elif job.status in ENDED:
        event = "requirement_closed"
    else:
        return
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update().execution_options(populate_existing=True))
    if event == "requirement_closed":
        await db.flush()  # this job's new status is visible to the count below
        live = await db.scalar(select(func.count()).select_from(Job).where(Job.company_id == company.id, Job.id != job.id, Job.status.not_in(ENDED)))
        if live:
            return
    await company_pipeline.apply_event(db, company, event, user)


# --- skills (J7) --------------------------------------------------------------------------------------------------------------------
async def _resolved(db: AsyncSession, names: list[str]) -> list[tuple[str, UUID | None]]:
    """(display name, skill id) per input, in order, duplicates (by resolved name) dropped."""
    out, seen = [], set()
    for raw in names:
        term = skills_master.normalise(raw)[:120]
        if not term:
            continue
        skill = await skills_master.resolve(db, term)
        name = skill.name if skill else term
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append((name, skill.id if skill else None))
    return out


async def set_skills(db: AsyncSession, job: Job, required: list[str] | None, preferred: list[str] | None) -> bool:
    """Replace the required and/or preferred list (None = keep that kind). A name in both lists is required. Rows are updated in place
    by name, so the (job, lower(name)) unique index never sees a delete-then-insert. Returns whether anything changed."""
    rows = {r.name.lower(): r for r in (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id))).all()}
    keep = {kind: [(r.name, r.skill_id) for r in sorted(rows.values(), key=lambda r: r.position) if r.kind == kind] for kind in DEFAULT_WEIGHT}
    wanted = {"required": await _resolved(db, required) if required is not None else keep["required"]}
    taken = {n.lower() for n, _ in wanted["required"]}
    wanted["preferred"] = [(n, s) for n, s in (await _resolved(db, preferred) if preferred is not None else keep["preferred"]) if n.lower() not in taken]
    return await _apply_skills(db, job, rows, wanted)


async def set_legacy_skills(db: AsyncSession, job: Job, names: list[str]) -> bool:
    """A legacy writer's flat list (employer, /workflows/it/jobs): names it keeps hold their kind; new names are required."""
    rows = {r.name.lower(): r for r in (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id))).all()}
    wanted = {"required": [], "preferred": []}
    for name, skill_id in await _resolved(db, names):
        existing = rows.get(name.lower())
        wanted[existing.kind if existing else "required"].append((name, skill_id))
    return await _apply_skills(db, job, rows, wanted)


async def _apply_skills(db: AsyncSession, job: Job, rows: dict, wanted: dict) -> bool:
    """Write `wanted` over `rows` and refresh the `jobs.skills` mirror (required first, then preferred)."""
    changed = False
    for kind, items in wanted.items():
        for position, (name, skill_id) in enumerate(items):
            row = rows.pop(name.lower(), None)
            if row is None:
                db.add(JobSkill(job_id=job.id, skill_id=skill_id, name=name, kind=kind, weight=DEFAULT_WEIGHT[kind], position=position))
                changed = True
                continue
            if (row.name, row.skill_id, row.kind, row.position) != (name, skill_id, kind, position):
                if row.kind != kind:
                    row.weight = DEFAULT_WEIGHT[kind]
                row.name, row.skill_id, row.kind, row.position = name, skill_id, kind, position
                changed = True
    for row in rows.values():
        await db.delete(row)
        changed = True
    job.skills = [name for kind in ("required", "preferred") for name, _ in wanted[kind]]
    return changed


# --- scope and permissions (spec §4) ------------------------------------------------------------------------------------------------
def _companies_of(*conditions):
    return select(Company.id).where(*conditions)


async def caller_scope(db: AsyncSession, user: User) -> list:
    """Read scope as SQL filters. Sub-selects only, so `FOR UPDATE` never locks a company or profile row."""
    if user.role == ROLE:
        await recruiter_context(db, user)
        return [or_(Job.assigned_recruiter_user_id == user.id, Job.company_id.in_(_companies_of(Company.assigned_recruiter_user_id == user.id)))]
    if user.role == MANAGER_ROLE:
        team = select(RecruiterProfile.user_id).where(RecruiterProfile.reporting_manager_user_id == user.id)
        unassigned = and_(Job.assigned_recruiter_user_id.is_(None), Job.company_id.in_(_companies_of(Company.assigned_recruiter_user_id.is_(None))))
        return [or_(Job.assigned_recruiter_user_id.in_(team), Job.company_id.in_(_companies_of(Company.assigned_recruiter_user_id.in_(team))), unassigned)]
    if user.role == "super_admin":
        return []
    if user.role == "bdm":  # R10: the assigned BDM of the company reads
        return [Job.company_id.in_(_companies_of(Company.assigned_bdm_user_id == user.id))]
    raise HTTPException(403, "Recruiter role required")


async def load_scoped(db: AsyncSession, user: User, job_id: UUID, *, lock: bool = False) -> Job:
    """With `lock`, the row is locked by id first and scope is checked in a fresh statement (the rec-003 / bdm-025 rule)."""
    stmt = select(Job).where(Job.id == job_id, *await caller_scope(db, user))
    if lock:
        await db.execute(select(Job.id).where(Job.id == job_id).with_for_update())
        stmt = stmt.execution_options(populate_existing=True)
    job = await db.scalar(stmt)
    if job is None:
        raise HTTPException(404, NOT_FOUND)
    return job


def permissions(user: User, job: Job) -> dict[str, bool]:
    writer = user.role in (ROLE, "super_admin")
    return {
        "can_edit": writer and job.status != "cancelled",
        "can_change_status": writer and bool(TRANSITIONS[job.status]),
        "can_reassign": user.role in (MANAGER_ROLE, "super_admin") and job.status != "cancelled",
    }


def require(user: User, job: Job, action: str, route: str) -> None:
    """403 for the wrong role first (logged), then 409 for the wrong state."""
    allowed = user.role in ((MANAGER_ROLE, "super_admin") if action == "can_reassign" else (ROLE, "super_admin"))
    if not allowed:
        logger.warning("recruiter_requirement_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "route": route}})
        raise HTTPException(403, REFUSALS[action])
    if not permissions(user, job)[action]:
        raise HTTPException(409, "This requirement is cancelled" if job.status == "cancelled" else "This requirement cannot change status")


def require_creator(user: User) -> None:
    if user.role not in (ROLE, MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, "Your role cannot add job requirements")


async def check_category(db: AsyncSession, values: dict, stored: Job | None) -> None:
    """The job category must be active when it is set or changed (FOR SHARE); keeping a since-deactivated one is allowed."""
    new = values.get("job_category_id")
    if new is None or (stored is not None and stored.job_category_id == new):
        return
    row = await db.scalar(select(RecJobCategory).where(RecJobCategory.id == new).with_for_update(read=True))
    if row is None or not row.active:
        raise HTTPException(422, "Choose an active job category")


def check_ranges(job: Job) -> None:
    """The merged (stored + sent) values; the schema already rejected a bad pair sent together."""
    for low, high, label in (("experience_min_months", "experience_max_months", "experience"), ("salary_min", "salary_max", "salary")):
        a, b = getattr(job, low), getattr(job, high)
        if a is not None and b is not None and a > b:
            raise HTTPException(422, f"Minimum {label} cannot be more than the maximum")


async def joined_count(db: AsyncSession, job_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.job_id == job_id, JobApplication.status.in_(HIRED_APPLICATION_STATUSES))) or 0


async def check_vacancies(db: AsyncSession, job: Job) -> None:
    if job.vacancies is not None and job.vacancies < (joined := await joined_count(db, job.id)):
        raise HTTPException(409, f"Vacancies cannot be fewer than the {joined} candidate(s) already joined")


# --- output --------------------------------------------------------------------------------------------------------------------------
def deadline_state(job: Job, today: date | None = None) -> str | None:
    """J4 / Appendix B D14: computed, never a status."""
    if job.status not in JOB_OPEN_STATUSES or job.closes_on is None:
        return None
    today = today or ist_today()
    if job.closes_on < today:
        return "expired"
    return "expiring" if job.closes_on <= today + timedelta(days=EXPIRING_DAYS) else None


def deadline_filter(state: str) -> list:
    today = ist_today()
    if state == "expired":
        return [Job.status.in_(JOB_OPEN_STATUSES), Job.closes_on < today]
    return [Job.status.in_(JOB_OPEN_STATUSES), Job.closes_on >= today, Job.closes_on <= today + timedelta(days=EXPIRING_DAYS)]


def _company(company: Company) -> dict:
    return {"id": company.id, "code": company.company_code, "name": company.name}


def row_out(user: User, job: Job, company: Company, recruiter: User | None) -> dict:
    return {
        "id": job.id,
        "code": job.requirement_code,
        "title": job.title,
        "company": _company(company),
        "location": job.location,
        "status": job.status,
        "status_label": STATUS_LABELS[job.status],
        "priority": job.priority,
        "vacancies": job.vacancies,
        "closes_on": job.closes_on,
        "requirement_date": job.requirement_date,
        "deadline_state": deadline_state(job),
        "assigned_recruiter": person(recruiter),
        "permissions": permissions(user, job),
    }


async def requirement_out(db: AsyncSession, user: User, job: Job, *, refresh: bool = True) -> dict:
    """The detail every route returns. Refreshes first: server defaults (updated_at) are expired after a flush."""
    if refresh:
        await db.refresh(job)
    company = await db.get(Company, job.company_id)
    skills = (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id).order_by(JobSkill.kind.desc(), JobSkill.position))).all()
    history = (await db.scalars(select(JobStatusHistory).where(JobStatusHistory.job_id == job.id).order_by(JobStatusHistory.created_at.desc(), JobStatusHistory.id))).all()
    user_ids = {job.assigned_recruiter_user_id, job.created_by_user_id} | {h.changed_by_user_id for h in history}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids - {None})))).all()}
    category = await db.get(RecJobCategory, job.job_category_id) if job.job_category_id else None
    return {
        **row_out(user, job, company, people.get(job.assigned_recruiter_user_id)),
        "description": job.description,
        "department": job.department,
        "job_category": ref(category),
        "qualification": job.qualification,
        "experience_min_months": job.experience_min_months,
        "experience_max_months": job.experience_max_months,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "work_mode": job.work_mode,
        "shift": job.shift,
        "employment_type": job.employment_type,
        "joining_requirement": job.joining_requirement,
        "skills": [
            {"id": s.id, "name": s.name, "kind": s.kind, "weight": s.weight, "skill_id": s.skill_id, "matched": s.skill_id is not None} for s in skills
        ],
        "joined_count": await joined_count(db, job.id),
        "allowed_statuses": [{"key": s, "label": STATUS_LABELS[s]} for s in TRANSITIONS[job.status]],
        "status_history": [
            {
                "from_status": h.from_status,
                "from_label": STATUS_LABELS.get(h.from_status) if h.from_status else None,
                "to_status": h.to_status,
                "to_label": STATUS_LABELS.get(h.to_status, h.to_status),
                "note": h.note,
                "changed_by": person(people.get(h.changed_by_user_id)),
                "created_at": h.created_at,
            }
            for h in history
        ],
        "created_by": person(people.get(job.created_by_user_id)),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def catalogue() -> dict:
    """GET /statuses: everything the form needs, so the web never hard-codes the transitions."""
    return {
        "statuses": [{"key": s, "label": STATUS_LABELS[s], "open": s in JOB_OPEN_STATUSES, "next": list(TRANSITIONS[s])} for s in JOB_STATUSES],
        "vocabularies": {k: list(v) for k, v in VOCABULARIES.items()},
        "expiring_days": EXPIRING_DAYS,
    }


def audit(db: AsyncSession, user: User, action: str, job_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names and statuses only."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_requirement.{action}", entity_type="job", entity_id=str(job_id), metadata_json=metadata or {}))


def log(event: str, user: User, job_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job_id), **extra}})
