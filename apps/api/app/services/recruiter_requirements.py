"""rec-007 (DEC-SCOPE-129, spec §2-§4): the Job Requirement's statuses, legacy shim, skills, scope, permissions and output.

Functions only; nothing here commits -- the route owns the transaction. Every `{requirement_id}` resolves through `load_scoped`, so an id
outside the caller's scope is the same 404 as a missing one (the rec-003 pattern). The employer and /workflows/it/jobs routes reuse the
status and skills functions, so every writer records history and keeps the `jobs.skills` mirror in step (J3, J7)."""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    JOB_APPROVAL_DEFAULTS,
    JOB_EMPLOYMENT_TYPES,
    JOB_OPEN_STATUSES,
    JOB_PLACE_KEY_SQL,
    JOB_PRIORITIES,
    JOB_SHIFTS,
    JOB_STATUSES,
    JOB_TITLE_KEY_SQL,
    JOB_VISIBILITY_LABELS,
    JOB_WORK_MODES,
    AuditLog,
    Company,
    CompanyContact,
    Job,
    JobApplication,
    JobApprovalSetting,
    JobAssignment,
    JobSkill,
    JobStatusHistory,
    RecJobCategory,
    RecLeadSource,
    RecruiterProfile,
    TalentPool,
    User,
)
from app.schemas import REC_REQUIREMENT_TERMS
from app.services import company_pipeline
from app.services import recruiter_contracts as contracts
from app.services import requirement_owners as owners
from app.services import skills as skills_master
from app.services.bdm_appointments import IST
from app.services.candidates import READERS as CANDIDATE_READERS
from app.services.permissions import user_has_grant
from app.services.recruiter import MANAGER_ROLE, ROLE, recruiter_context
from app.services.recruiter_companies import person, ref

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Job requirement not found"
HIRING_MANAGER_ROLE = "interviewer"  # hrc-005 V2: hrc-002's internal Hiring Manager/Interviewer
MAX_DUPLICATE_MATCHES = 10
EXPIRING_DAYS = 7  # J4 (Q-05)
HIRED_APPLICATION_STATUSES = ("joined",)  # rec-017 A1: the legacy "hired" is Joined (workflows.update_job_offer follows an accepted offer there)
STATUS_LABELS = {
    "new": "New", "pending_approval": "Pending Approval", "requirement_received": "Requirement Received", "sourcing": "Sourcing",
    "shortlisting": "Shortlisting", "profiles_shared": "Profiles Shared", "interviewing": "Interviewing", "selected": "Selected", "joined": "Joined",
    "filled": "Filled", "on_hold": "On Hold", "closed": "Closed", "cancelled": "Cancelled",
}
_ACTIVE = (*JOB_OPEN_STATUSES, "selected")
ENDED = ("closed", "cancelled")  # a requirement no longer live for the company stage (rec-005's `requirement_closed`)
TRANSITIONS = {  # spec §2; only a rejection (hrc-007) returns to `new`, and `cancelled` is terminal
    "new": ("requirement_received", "on_hold", "closed", "cancelled"),
    # hrc-007 (A6/A8): Pending Approval is entered by `submit` and left by `decide`; the owner's only move is to cancel.
    "pending_approval": ("cancelled",),
    **{s: (*(a for a in _ACTIVE if a != s), *(("joined",) if s == "selected" else ()), "filled", "on_hold", "closed", "cancelled") for s in _ACTIVE},
    "joined": ("filled", "closed"),
    "filled": ("requirement_received", "closed"),  # hrc-007 (A11): reopened when seats are added, or closed
    "on_hold": (*_ACTIVE, "closed", "cancelled"),
    "closed": ("requirement_received",),
    "cancelled": (),
}
# hrc-007 (DEC-SCOPE-380 A2, Q-07): the PDF's seven workflow phases over the 13 internal statuses.
PHASE_LABELS = {
    "draft": "Draft", "pending_approval": "Pending Approval", "open": "Open", "on_hold": "On Hold", "filled": "Filled", "closed": "Closed",
    "cancelled": "Cancelled",
}
PHASES = {"new": "draft", **{s: "open" for s in _ACTIVE}, "joined": "filled", **{s: s for s in ("pending_approval", "filled", "on_hold", "closed", "cancelled")}}
SUBMITTABLE = ("new", "on_hold")  # A6
NEEDS_APPROVAL = "This requirement needs approval before it opens: submit it for approval"
OWN_JOB = "You cannot approve or reject your own job requirement"
NOT_PENDING = "This requirement is not pending approval"
FILLED_NOTE = "All vacancies filled"
VOCABULARIES = {"work_mode": JOB_WORK_MODES, "shift": JOB_SHIFTS, "employment_type": JOB_EMPLOYMENT_TYPES, "priority": JOB_PRIORITIES}
REFUSALS = {
    "can_edit": "Only the recruiter on this requirement can edit it",
    "can_change_status": "Only the recruiter on this requirement can change its status",
    "can_reassign": "Only a placement manager can reassign this requirement",
    "can_manage_owners": "Only the primary owner or a placement manager can change the owners",
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
    """The employer API's `status` (J3): draft / open / closed. hrc-007: Pending Approval is still a draft; Filled is closed."""
    if status in ("new", "on_hold", "pending_approval"):
        return "draft"
    return "open" if status in JOB_OPEN_STATUSES else "closed"


def legacy_target(current: str, word: str) -> str | None:
    """The §6 status a legacy draft/open/closed write means from `current`; None = already there (no change)."""
    if word == "draft":
        return None if current in ("new", "on_hold", "pending_approval") else "on_hold"
    if word == "open":
        return None if current in (*JOB_OPEN_STATUSES, "pending_approval") else "requirement_received"
    return None if current in ("closed", "cancelled", "joined") else "closed"


def check_transition(current: str, target: str) -> None:
    if target == current:
        raise HTTPException(409, f"The requirement is already {STATUS_LABELS[current]}")
    if target not in TRANSITIONS[current]:
        raise HTTPException(409, f"A requirement cannot move from {STATUS_LABELS[current]} to {STATUS_LABELS[target]}")


async def change_status(db: AsyncSession, user: User | None, job: Job, target: str, note: str | None = None) -> str:
    """Validated move + history row + the company stage; returns the previous status. hrc-007 (A7): a job that still needs approval
    cannot open by any writer."""
    check_transition(job.status, target)
    if target in _ACTIVE and await approval_required(db, job):
        raise HTTPException(409, NEEDS_APPROVAL)
    return await _move(db, user, job, target, note)


async def _move(db: AsyncSession, user: User | None, job: Job, target: str, note: str | None) -> str:
    previous = job.status
    db.add(JobStatusHistory(job_id=job.id, from_status=previous, to_status=target, note=note, changed_by_user_id=user.id if user else None))
    job.status = target
    await drive_company_stage(db, user, job)
    return previous


async def legacy_move(db: AsyncSession, user: User, job: Job, word: str, note: str | None = None) -> None:
    """The employer and /workflows/it/jobs draft/open/closed words (J3). hrc-007 (A6): "open" means submit while approval applies."""
    target = legacy_target(job.status, word)
    if target == "requirement_received" and job.status in SUBMITTABLE and await approval_required(db, job):
        await submit(db, user, job, note)
    elif target:
        await change_status(db, user, job, target, note)


# --- approval (hrc-007, DEC-SCOPE-380 A4-A10) ---------------------------------------------------------------------------------------
async def approval_settings(db: AsyncSession) -> dict[str, bool]:
    rows = dict((await db.execute(select(JobApprovalSetting.source, JobApprovalSetting.required))).all())
    return {source: rows.get(source, default) for source, default in JOB_APPROVAL_DEFAULTS.items()}


async def approval_required(db: AsyncSession, job: Job) -> bool:
    """A5: the source's setting is on and the job has never been live (an approved job can pause and reopen without a second approval)."""
    if not (await approval_settings(db))[job.source]:
        return False
    live = await db.scalar(select(JobStatusHistory.id).where(JobStatusHistory.job_id == job.id, JobStatusHistory.to_status.in_(_ACTIVE)).limit(1))
    return live is None


def _with_note(prefix: str, note: str | None) -> str:
    return f"{prefix}: {note}" if note else prefix


async def submit(db: AsyncSession, user: User, job: Job, note: str | None = None) -> str:
    """A6: Draft / On Hold -> Pending Approval while approval applies; anything else is a 409."""
    if job.status not in SUBMITTABLE or not await approval_required(db, job):
        raise HTTPException(409, NOT_PENDING if job.status == "pending_approval" else "This requirement does not need approval")
    job.submitted_by_user_id, job.submitted_at = user.id, func.now()
    previous = await _move(db, user, job, "pending_approval", _with_note("Submitted for approval", note))
    audit(db, user, "submit", job.id, {"from": previous, "to": job.status, "note": note, "changes": {"status": [previous, job.status]}})  # every path
    return previous


def is_own(user: User, job: Job) -> bool:
    """A8: separation of duties -- the submitter, the creator and the assigned recruiter never decide."""
    return user.id in {job.submitted_by_user_id, job.created_by_user_id, job.assigned_recruiter_user_id}


async def decide(db: AsyncSession, user: User, job: Job, approve: bool, note: str | None) -> str:
    """The caller holds `jobs.approve` and locked the row. Approve opens the job (rec-005's company stage follows); reject returns it to
    Draft. Returns the previous status."""
    if job.status != "pending_approval":
        raise HTTPException(409, NOT_PENDING)
    if is_own(user, job):
        logger.warning("recruiter_requirement_self_approval_refused", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id)}})
        raise HTTPException(403, OWN_JOB)
    if approve:
        return await _move(db, user, job, "requirement_received", _with_note("Approved", note))
    return await _move(db, user, job, "new", _with_note("Rejected", note))


async def load_for_approver(db: AsyncSession, job_id: UUID) -> Job:
    """An approver has no recruiter scope (the HR Manager): any job, locked; missing = 404."""
    job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None:
        raise HTTPException(404, NOT_FOUND)
    return job


async def set_visibility(db: AsyncSession, user: User, job: Job, visibility: str, pool_id: UUID | None) -> dict:
    """hrc-008 (V7): the caller holds `jobs.publish` and locked the row. A segment's pool must be active (422). Returns the audited
    {field: [before, after]} changes; the same values are no change (no audit, no updated_at bump)."""
    pool = await db.scalar(select(TalentPool).where(TalentPool.id == pool_id, TalentPool.active.is_(True))) if pool_id else None
    if pool_id and pool is None:
        raise HTTPException(422, "Choose an active talent pool")
    if (job.visibility, job.segment_pool_id) == (visibility, pool_id):
        return {}
    changes = {"visibility": [job.visibility, visibility]} if job.visibility != visibility else {}
    if job.segment_pool_id != pool_id:
        old = await db.get(TalentPool, job.segment_pool_id) if job.segment_pool_id else None
        changes["segment_pool"] = [old.name if old else None, pool.name if pool else None]
    job.visibility, job.segment_pool_id = visibility, pool_id
    job.updated_at = func.now()  # hrc-003 S1: open editors see the change
    job.updated_by_user_id = user.id
    audit(db, user, "visibility", job.id, {"changes": changes})
    return changes


async def fill_when_complete(db: AsyncSession, user: User | None, job_id: UUID) -> None:
    """A11: an application just became Joined -- when the joined count reaches the vacancies the (locked) job is Filled."""
    job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.vacancies is None or job.status not in (*_ACTIVE, "joined") or await joined_count(db, job.id) < job.vacancies:
        return
    await _move(db, user, job, "filled", FILLED_NOTE)
    logger.info("recruiter_requirement_filled", extra={"extra_fields": {"job_id": str(job.id)}})


async def record_created(db: AsyncSession, user: User, job: Job, note: str = "Created") -> None:
    """Every create path (recruiter, employer, legacy): the first status row and, hrc-006 (O2), the primary owner's history row."""
    db.add(JobStatusHistory(job_id=job.id, from_status=None, to_status=job.status, note=note, changed_by_user_id=user.id))
    owners.record_primary(db, user, job)
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


async def caller_scope(db: AsyncSession, user: User, *, officers: bool = False) -> list:
    """Read scope as SQL filters. Sub-selects only, so `FOR UPDATE` never locks a company or profile row. hrc-006 (O4): an assignee
    (`job_assignments`) reads the job too; a placement officer has a scope only where the route opts in with `officers` (the requirement
    and its JD), so every candidate-side caller of this function keeps refusing the role."""
    if user.role == ROLE:
        await recruiter_context(db, user)
        mine = Company.assigned_recruiter_user_id == user.id
        return [or_(Job.assigned_recruiter_user_id == user.id, Job.company_id.in_(_companies_of(mine)), Job.id.in_(owners.jobs_of(JobAssignment.user_id == user.id)),
                    Job.backup_owner_user_id == user.id)]  # fmt: skip  # pob-002 R9: the backup owner
    if user.role == MANAGER_ROLE:
        team = select(RecruiterProfile.user_id).where(RecruiterProfile.reporting_manager_user_id == user.id)
        unassigned = and_(Job.assigned_recruiter_user_id.is_(None), Job.company_id.in_(_companies_of(Company.assigned_recruiter_user_id.is_(None))))
        return [or_(Job.assigned_recruiter_user_id.in_(team), Job.company_id.in_(_companies_of(Company.assigned_recruiter_user_id.in_(team))),
                    Job.id.in_(owners.jobs_of(JobAssignment.user_id.in_(team))), Job.backup_owner_user_id.in_(team), unassigned)]  # fmt: skip
    if user.role == "super_admin":
        return []
    if user.role == "bdm":  # R10: the assigned BDM of the company reads
        return [Job.company_id.in_(_companies_of(Company.assigned_bdm_user_id == user.id))]
    if officers and user.role == owners.OFFICER_ROLE:
        return [Job.id.in_(owners.jobs_of(JobAssignment.user_id == user.id))]
    raise HTTPException(403, "Recruiter role required")


async def load_scoped(db: AsyncSession, user: User, job_id: UUID, *, lock: bool = False, officers: bool = False) -> Job:
    """With `lock`, the row is locked by id first and scope is checked in a fresh statement (the rec-003 / bdm-025 rule)."""
    stmt = select(Job).where(Job.id == job_id, *await caller_scope(db, user, officers=officers))
    if lock:
        await db.execute(select(Job.id).where(Job.id == job_id).with_for_update())
        stmt = stmt.execution_options(populate_existing=True)
    job = await db.scalar(stmt)
    if job is None:
        raise HTTPException(404, NOT_FOUND)
    return job


WRITERS = (ROLE, owners.OFFICER_ROLE, "super_admin")  # hrc-006 (O5): in scope, a placement officer is an assignee


def _manages_owners(user: User, job: Job) -> bool:
    """hrc-006 (O5): the primary owner, a placement manager (in scope) or super_admin. pob-002 (R9, Q-02): the backup owner too, always."""
    return user.role in (MANAGER_ROLE, "super_admin") or user.id in (job.assigned_recruiter_user_id, job.backup_owner_user_id)


def permissions(user: User, job: Job) -> dict[str, bool]:
    writer = user.role in WRITERS
    live = job.status != "cancelled"
    return {
        "can_edit": writer and live,
        "can_change_status": writer and bool(TRANSITIONS[job.status]),
        "can_reassign": user.role in (MANAGER_ROLE, "super_admin") and live,
        "can_manage_owners": _manages_owners(user, job) and live,
        "can_view_matches": user.role in CANDIDATE_READERS,  # rec-016 (M7): the assigned BDM reads the requirement, not the pool
        "can_view_candidates": user.role != owners.OFFICER_ROLE,  # hrc-006 (O5): the officer's candidate access waits for hrc-012
    }


def require(user: User, job: Job, action: str, route: str) -> None:
    """403 for the wrong role first (logged), then 409 for the wrong state."""
    if action == "can_manage_owners":
        allowed = _manages_owners(user, job)
    else:
        allowed = user.role in ((MANAGER_ROLE, "super_admin") if action == "can_reassign" else WRITERS)
    if not allowed:
        logger.warning("recruiter_requirement_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "route": route}})
        raise HTTPException(403, REFUSALS[action])
    if not permissions(user, job)[action]:
        raise HTTPException(409, "This requirement is cancelled" if job.status == "cancelled" else "This requirement cannot change status")


def require_creator(user: User) -> None:
    if user.role not in (ROLE, MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, "Your role cannot add job requirements")


# hrc-005 (V1/V2): the job category, the source and the hiring manager -- (column, row, the row's "active" test, the refusal)
_REFERENCES = (
    ("job_category_id", RecJobCategory, lambda row: row.active, "Choose an active job category"),
    ("lead_source_id", RecLeadSource, lambda row: row.active, "Choose an active lead source"),
    ("hiring_manager_user_id", User, lambda row: row.active and row.role == HIRING_MANAGER_ROLE, "Choose an active hiring manager"),
)


async def check_references(db: AsyncSession, values: dict, stored: Job | None) -> None:
    """Each reference must be active when it is set or changed (FOR SHARE); keeping a since-deactivated one is allowed."""
    for column, model, usable, refusal in _REFERENCES:
        new = values.get(column)
        if new is None or (stored is not None and getattr(stored, column) == new):
            continue
        row = await db.scalar(select(model).where(model.id == new).with_for_update(read=True))
        if row is None or not usable(row):
            raise HTTPException(422, refusal)


# --- pob-002 (DEC-SCOPE-407 R6-R9): the decision-maker, the backup owner and the per-requirement terms --------------------------------
DECISION_MAKER_INVALID = "Choose an active contact of this company as the decision-maker"
BACKUP_INVALID = "Choose an active recruiter as the backup owner"
BACKUP_IS_PRIMARY = "The primary owner cannot also be the backup owner"
NO_BACKUP_RIGHT = "Only the primary owner, the backup owner or a placement manager can change the backup owner"
PAYMENT_DAYS = "Enter the number of days only when payment is due a number of days after joining"
TRIGGER_LABELS = {"on_joining": "On joining", "days_after_joining": "Days after joining", "on_invoice": "On invoice"}


def _sent_change(values: dict, stored: Job | None, column: str) -> bool:
    return column in values and (stored is None or getattr(stored, column) != values[column])


async def check_owner_fields(db: AsyncSession, user: User, values: dict, stored: Job | None, company_id: UUID, primary_id: UUID | None) -> None:
    """R6: a decision-maker set or changed is an active contact of the requirement's company (FOR SHARE); keeping one deactivated since is
    allowed. R9: the backup owner is changed only by those who manage the owners (403), is never the primary (409) and is an active
    recruiter with a profile (422)."""
    if _sent_change(values, stored, "decision_maker_contact_id") and values["decision_maker_contact_id"] is not None:
        contact = await db.scalar(select(CompanyContact).where(CompanyContact.id == values["decision_maker_contact_id"]).with_for_update(read=True))
        if contact is None or contact.company_id != company_id or not contact.active:
            raise HTTPException(422, DECISION_MAKER_INVALID)
    if not _sent_change(values, stored, "backup_owner_user_id"):
        return
    if stored is not None and not _manages_owners(user, stored):
        logger.warning("recruiter_requirement_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(stored.id), "route": "backup_owner"}})
        raise HTTPException(403, NO_BACKUP_RIGHT)
    target = values["backup_owner_user_id"]
    if target is None:
        return
    if target == primary_id:
        raise HTTPException(409, BACKUP_IS_PRIMARY)
    eligible = [User.id == target, User.active.is_(True), User.role == ROLE, User.id.in_(select(RecruiterProfile.user_id))]
    if await db.scalar(select(User.id).where(*eligible).with_for_update(read=True)) is None:
        raise HTTPException(422, BACKUP_INVALID)


async def require_terms_edit(db: AsyncSession, user: User, sent: set[str], route: str) -> None:
    """R8: sending any per-requirement term (any value, null included) needs pob-001's effective edit -- 403 otherwise."""
    if sent & set(REC_REQUIREMENT_TERMS):
        await contracts.require_terms(db, user, route, edit=True)


def check_terms(job: Job) -> None:
    """R7, on the merged values: the days go with (and only with) "N days after joining"."""
    if (job.payment_trigger == "days_after_joining") != (job.payment_days is not None):
        raise HTTPException(422, PAYMENT_DAYS)


async def commercial_terms(db: AsyncSession, job: Job, company: Company) -> dict:
    """R7: each term with `inherited` = taken from the company's current contract (the fee: the rec-031 override, else the contract)."""
    contract = await contracts.load_current(db, company)
    own_fee = job.fee_basis is not None
    fee_basis, fee_value = (job.fee_basis, job.fee_value) if own_fee else ((contract.fee_basis, contract.fee_value) if contract else (None, None))
    inherited = {"payment_terms": contract.payment_terms if contract else None, "replacement_terms": contract.replacement_policy if contract else None}

    def term(key: str) -> dict:
        own = getattr(job, key)
        return {"value": own if own is not None else inherited[key], "inherited": own is None and inherited[key] is not None}

    return {
        "fee": {"basis": fee_basis, "value": str(fee_value) if fee_value is not None else None, "inherited": not own_fee and fee_basis is not None},  # exact, as rec-031
        "payment_trigger": job.payment_trigger,
        "payment_trigger_label": TRIGGER_LABELS.get(job.payment_trigger) if job.payment_trigger else None,
        "payment_days": job.payment_days,
        "payment_terms": term("payment_terms"),
        "replacement_terms": term("replacement_terms"),
    }


# --- hrc-005 V3: location ----------------------------------------------------------------------------------------------------------
def place_text(city: str | None, state: str | None, country: str | None) -> str:
    return ", ".join(p for p in (city, state, country) if p)[:120]


def settle_location(job: Job, previous_place: str | None = None) -> None:
    """A blank location is the city, state and country; one that equalled the previous derived text follows them. Neither = 422."""
    place = place_text(job.city, job.state, job.country)
    if not job.location or (previous_place and job.location == previous_place):
        job.location = place or job.location
    if not job.location:
        raise HTTPException(422, "Enter the job location or its city")


# --- hrc-005 V4/V5: possible duplicates -----------------------------------------------------------------------------------------
TITLE_KEY = literal_column(JOB_TITLE_KEY_SQL)
PLACE_KEY = literal_column(JOB_PLACE_KEY_SQL)
DUPLICATE_FIELDS = frozenset({"title", "city", "location", "requisition_reference"})


def _key(text: str | None) -> str | None:
    return " ".join(text.split()).lower() if text and text.strip() else None


async def check_duplicates(db: AsyncSession, job: Job, reason: str | None, exclude_id: UUID | None = None) -> list[str]:
    """Another live job of the same company with the same title and place, or the same requisition reference, is a 409
    `possible_duplicate` unless a reason is given. The company is already in the caller's scope. Returns the overridden codes."""
    same = [and_(TITLE_KEY == _key(job.title), PLACE_KEY == _key(job.city or job.location))]
    if reference := _key(job.requisition_reference):
        same.append(func.lower(func.btrim(Job.requisition_reference)) == reference)
    conditions = [Job.company_id == job.company_id, Job.status.not_in(ENDED), or_(*same), *([Job.id != exclude_id] if exclude_id else [])]
    total = await db.scalar(select(func.count()).select_from(Job).where(*conditions)) or 0
    if not total:
        return []
    rows = (await db.scalars(select(Job).where(*conditions).order_by(Job.requirement_code).limit(MAX_DUPLICATE_MATCHES))).all()
    if reason:
        return [r.requirement_code for r in rows]
    matches = [{"id": str(r.id), "code": r.requirement_code, "title": r.title, "location": r.location, "status_label": STATUS_LABELS[r.status],
                "requisition_reference": r.requisition_reference} for r in rows]  # fmt: skip
    raise HTTPException(409, {"message": "This may be a duplicate of a live job requirement", "code": "possible_duplicate", "matches": matches, "total": total})


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
        "phase": PHASES[job.status],
        "phase_label": PHASE_LABELS[PHASES[job.status]],
        "source": job.source,
        "visibility": job.visibility,  # hrc-008
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
    user_ids = {job.assigned_recruiter_user_id, job.created_by_user_id, job.submitted_by_user_id, job.updated_by_user_id, job.hiring_manager_user_id,
                job.backup_owner_user_id} | {h.changed_by_user_id for h in history}  # fmt: skip
    decision_maker = await db.get(CompanyContact, job.decision_maker_contact_id) if job.decision_maker_contact_id else None
    view_terms, edit_terms = await contracts.commercial_access(db, user)  # pob-001 / pob-002 R8
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids - {None})))).all()}
    category = await db.get(RecJobCategory, job.job_category_id) if job.job_category_id else None
    lead_source = await db.get(RecLeadSource, job.lead_source_id) if job.lead_source_id else None
    segment_pool = await db.get(TalentPool, job.segment_pool_id) if job.segment_pool_id else None
    required = job.status in SUBMITTABLE and await approval_required(db, job)
    allowed = [s for s in TRANSITIONS[job.status] if not (required and s in _ACTIVE)]  # A7
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
        # hrc-005 (V1): the §4.2 fields
        "requisition_reference": job.requisition_reference,
        "lead_source": ref(lead_source),
        "certifications": job.certifications,
        "country": job.country,
        "state": job.state,
        "city": job.city,
        "relocation_required": job.relocation_required,
        "travel_requirement": job.travel_requirement,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "benefits": job.benefits,
        "hiring_manager": person(people.get(job.hiring_manager_user_id)),
        "owners": await owners.owners_out(db, job.id),  # hrc-006 (O11): besides the primary (`assigned_recruiter`)
        "backup_owner": person(people.get(job.backup_owner_user_id)),  # pob-002 R9
        "expected_joining_date": job.expected_joining_date,
        # pob-002 R6: the client's hiring process
        "interview_rounds": job.interview_rounds or [],
        "screening_steps": job.screening_steps or [],
        "decision_maker": {"id": decision_maker.id, "name": decision_maker.name, "designation": decision_maker.designation, "active": decision_maker.active}
        if decision_maker else None,
        "expected_tat_days": job.expected_tat_days,
        # pob-002 R7/R8: absent (not null) without commercials.client.view
        **({"commercial_terms": {**await commercial_terms(db, job, company), "can_edit": edit_terms and permissions(user, job)["can_edit"]}} if view_terms else {}),
        "skills": [
            {"id": s.id, "name": s.name, "kind": s.kind, "weight": s.weight, "skill_id": s.skill_id, "matched": s.skill_id is not None, "min_level": s.min_level}
            for s in skills
        ],
        "joined_count": await joined_count(db, job.id),
        "allowed_statuses": [{"key": s, "label": STATUS_LABELS[s]} for s in allowed],
        "approval": {
            "required": required,
            "submitted_by": person(people.get(job.submitted_by_user_id)),
            "submitted_at": job.submitted_at,
            "can_submit": required and permissions(user, job)["can_edit"],
            "can_decide": job.status == "pending_approval" and not is_own(user, job) and await user_has_grant(db, user, "jobs", "approve"),
        },
        "visibility": {  # hrc-008 (V1, V4)
            "key": job.visibility,
            "label": JOB_VISIBILITY_LABELS[job.visibility],
            "segment_pool": ref(segment_pool),
            "can_change": await user_has_grant(db, user, "jobs", "publish"),
        },
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
        "updated_by": person(people.get(job.updated_by_user_id)),  # hrc-005 V6
        "updated_at": job.updated_at,
    }


def catalogue() -> dict:
    """GET /statuses: everything the form needs, so the web never hard-codes the transitions."""
    return {
        "statuses": [
            {"key": s, "label": STATUS_LABELS[s], "open": s in JOB_OPEN_STATUSES, "next": list(TRANSITIONS[s]), "phase": PHASES[s], "phase_label": PHASE_LABELS[PHASES[s]]}
            for s in JOB_STATUSES
        ],
        "vocabularies": {k: list(v) for k, v in VOCABULARIES.items()},
        "expiring_days": EXPIRING_DAYS,
    }


async def audited_values(db: AsyncSession, job: Job, fields, *, skills: bool = False) -> dict:
    """hrc-004 B5: the values an edit's audit diff compares -- the category by name, and the skill lists as text when `skills`."""
    values = {k: getattr(job, k) for k in fields}
    references = (("job_category_id", RecJobCategory, "name"), ("lead_source_id", RecLeadSource, "name"), ("hiring_manager_user_id", User, "full_name"),
                  ("decision_maker_contact_id", CompanyContact, "name"), ("backup_owner_user_id", User, "full_name"))  # fmt: skip  # pob-002
    for column, model, name in references:
        if column in values:  # hrc-005: by name, like the category
            row_id = values.pop(column)
            values[column.removesuffix("_user_id").removesuffix("_id")] = getattr(await db.get(model, row_id), name) if row_id else None
    for column in ("interview_rounds", "screening_steps"):  # pob-002 R6: an ordered list reads as one line
        if column in values:
            values[column] = "; ".join(values[column]) if values[column] else None
    if skills:
        rows = (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id).order_by(JobSkill.position))).all()
        for kind in DEFAULT_WEIGHT:
            values[f"{kind}_skills"] = ", ".join(r.name for r in rows if r.kind == kind)
    return values


async def recruiter_name(db: AsyncSession, user_id: UUID | None) -> str | None:
    return (await db.get(User, user_id)).full_name if user_id else None


def audit(db: AsyncSession, user: User, action: str, job_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names and statuses -- hrc-004: plus `changes`, redacted values."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_requirement.{action}", entity_type="job", entity_id=str(job_id), metadata_json=metadata or {}))


def audit_settings(db: AsyncSession, user: User, changes: dict) -> None:
    """hrc-007 (A4): one row per settings save, {source: [before, after]}."""
    db.add(AuditLog(user_id=user.id, action="recruiter_requirement.approval_settings", entity_type="job_approval_settings", entity_id="all",
                    metadata_json={"changes": changes}))


def log(event: str, user: User, job_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job_id), **extra}})
