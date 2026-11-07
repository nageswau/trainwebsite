"""pob-016 (DEC-SCOPE-419, the spec's C1-C14): a requirement's validation checklist -- the items, their clarification follow-ups, the blocking rules, the
guard on starting sourcing and the Team Lead's override.

Functions only; nothing here commits, and the caller holds the requirement's row lock (`load_scoped(lock=True)`). `recruiter_requirements` calls `guard`, so this
module cannot import it: the routes decide who may act. Audit rows carry item keys, labels and statuses."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    JOB_OPEN_STATUSES,
    AuditLog,
    Company,
    CompanyContact,
    Job,
    JobChecklistItem,
    JobChecklistOverride,
    JobStatusHistory,
    RecruiterFollowUp,
    RequirementChecklistSetting,
    User,
)
from app.schemas import RecFollowUpCreate
from app.services import recruiter_follow_ups as follow_ups
from app.services.bdm_appointments import db_now
from app.services.recruiter import MANAGER_ROLE
from app.services.recruiter_companies import person

# C1 (NEEDS_CONFIRMATION): the backlog's "§7.1 (8 checks)" does not name them and the source document is not on this machine, so these are a proposal from
# the §7 field groups. This tuple is the only place to correct them; stored rows hold the key.
ITEMS = (
    ("role_scope", "Role and responsibilities", "The client has said what the role does."),
    ("skills_experience", "Skills and experience", "The must-have skills and the experience range are agreed."),
    ("openings", "Number of openings", "The client has confirmed how many people they will hire."),
    ("location_work_mode", "Location and work mode", "The location and on-site, hybrid or remote are settled."),
    ("salary_budget", "Salary budget", "The client has given a salary range."),
    ("hiring_process", "Interview process and decision-maker", "The interview rounds and who decides are known."),
    ("commercial_terms", "Commercial terms", "The fee and payment terms for this requirement are agreed."),
    ("timeline", "Joining date and turnaround", "When the client needs people to join, and how fast they review profiles."),
)
KEYS = tuple(key for key, _, _ in ITEMS)
LABELS = {key: label for key, label, _ in ITEMS}
STATUS_LABELS = {None: "Not reviewed", "confirmed": "Confirmed", "not_applicable": "Not applicable", "missing": "Missing"}
DONE = ("confirmed", "not_applicable")
MANAGERS = (MANAGER_ROLE, "super_admin")
WORKING_STATUSES = (*(s for s in JOB_OPEN_STATUSES if s != "requirement_received"), "selected")  # C8
PAST_SOURCING = ("joined", "filled")  # C9
FOLLOW_UP_DAYS = 2  # C4
CONFIRMED_OUTCOME = "Confirmed on the requirement checklist"
NOT_NEEDED = "Marked not applicable on the requirement checklist"
NO_OVERRIDE = "Only a Team Lead can override the checklist"
NO_COMPANY_RULE = "Only a Team Lead can change this company's checklist rule"
NO_GLOBAL_RULE = "Only a super admin can change the global checklist rule"


async def _statuses(db: AsyncSession, job_id) -> dict[str, str]:
    return dict((await db.execute(select(JobChecklistItem.item_key, JobChecklistItem.status).where(JobChecklistItem.job_id == job_id))).all())


def _incomplete(statuses: dict[str, str]) -> list[dict]:
    return [{"key": key, "label": LABELS[key], "status": statuses.get(key)} for key in KEYS if statuses.get(key) not in DONE]


async def _blocking(db: AsyncSession, company_id) -> dict:
    """C6: the company's rule when it has one, else the global rule (no row = off)."""
    company_rule = await db.scalar(select(Company.checklist_blocks_sourcing).where(Company.id == company_id))
    global_rule = bool(await db.scalar(select(RequirementChecklistSetting.block_sourcing).where(RequirementChecklistSetting.id == 1)))
    return {"on": global_rule if company_rule is None else company_rule, "company_rule": company_rule, "global_rule": global_rule}


async def _started(db: AsyncSession, job: Job) -> bool:
    """C9: never blocked again once work has begun, even if it paused or the rule was switched on later."""
    if job.status in (*WORKING_STATUSES, *PAST_SOURCING):
        return True
    return await db.scalar(select(JobStatusHistory.id).where(JobStatusHistory.job_id == job.id, JobStatusHistory.to_status.in_(WORKING_STATUSES)).limit(1)) is not None


async def _override(db: AsyncSession, job_id) -> JobChecklistOverride | None:
    return await db.get(JobChecklistOverride, job_id)


async def guard(db: AsyncSession, job: Job, target: str) -> None:
    """C7/C8/AC2: called by `change_status`, after its other checks."""
    if target not in WORKING_STATUSES or not (await _blocking(db, job.company_id))["on"] or await _started(db, job):
        return
    missing = _incomplete(await _statuses(db, job.id))
    if missing and await _override(db, job.id) is None:
        names = ", ".join(item["label"] for item in missing)
        raise HTTPException(409, {"message": f"Complete the checklist before sourcing starts. Still needed: {names}.", "code": "checklist_incomplete", "missing": missing})


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


async def _open_follow_up(db: AsyncSession, user: User, job: Job, key: str, now: datetime) -> RecruiterFollowUp:
    """C4: `follow_ups.create` counts its cap under the company lock. Job, then company: the order `_move` already takes."""
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update())
    contacts = (await db.execute(
        select(CompanyContact.id, CompanyContact.id == job.decision_maker_contact_id).where(
            CompanyContact.company_id == job.company_id, CompanyContact.active.is_(True),
            (CompanyContact.id == job.decision_maker_contact_id) | CompanyContact.is_primary,
        )
    )).all()  # fmt: skip
    contact_id = next((i for i, decides in contacts if decides), contacts[0][0] if contacts else None)
    hint = next(h for k, _, h in ITEMS if k == key)
    notes = f"Clarify with the client for {job.requirement_code} ({job.title}): {LABELS[key]}. {hint}"
    body = RecFollowUpCreate(due_at=now + timedelta(days=FOLLOW_UP_DAYS), reason="clarification", contact_id=contact_id, job_id=job.id, notes=notes)
    return await follow_ups.create(db, user, company, body, now)


async def _close_follow_up(db: AsyncSession, user: User, follow_up_id, status: str, now: datetime) -> None:
    """C5: only one still open; one closed by hand keeps its own outcome."""
    fu = await db.scalar(select(RecruiterFollowUp).where(RecruiterFollowUp.id == follow_up_id, RecruiterFollowUp.status == "open").with_for_update())
    if fu is None:
        return
    if status == "confirmed":
        fu.status, fu.completed_at, fu.completed_by_user_id, fu.outcome = "done", now, user.id, CONFIRMED_OUTCOME
        follow_ups.audit(db, user, "complete", fu.id, {"with_outcome": True})
    else:
        fu.status, fu.cancelled_at, fu.cancel_reason = "cancelled", now, NOT_NEEDED
        follow_ups.audit(db, user, "cancel", fu.id)


async def set_item(db: AsyncSession, user: User, job: Job, key: str, status: str) -> bool:
    """One answer, its follow-up and its audit row. The same answer again changes nothing (False)."""
    row = await db.get(JobChecklistItem, (job.id, key))
    before = row.status if row else None
    if before == status:
        return False
    now = await db_now(db)
    if before == "missing" and row.follow_up_id:
        await _close_follow_up(db, user, row.follow_up_id, status, now)
    if row is None:
        row = JobChecklistItem(job_id=job.id, item_key=key, status=status, updated_by_user_id=user.id)
        db.add(row)
    row.status, row.updated_by_user_id = status, user.id
    if status == "missing":
        row.follow_up_id = (await _open_follow_up(db, user, job, key, now)).id
    _audit(db, user, "recruiter_requirement.checklist_item", "job", job.id,
           {"item": key, "changes": {LABELS[key]: [STATUS_LABELS[before], STATUS_LABELS[status]]}})  # fmt: skip
    return True


async def _override_refusal(db: AsyncSession, job: Job, statuses: dict[str, str]) -> str | None:
    """C11: why nothing can be overridden, or None when this requirement is being blocked."""
    if job.status == "cancelled":
        return "This requirement is cancelled"
    if not (await _blocking(db, job.company_id))["on"]:
        return "The checklist is not blocking this requirement"
    if await _started(db, job):
        return "Sourcing has already started on this requirement"
    if not _incomplete(statuses):
        return "The checklist is complete, so there is nothing to override"
    if await _override(db, job.id):
        return "This requirement has already been overridden"
    return None


async def override(db: AsyncSession, user: User, job: Job, reason: str) -> None:
    """AC3: who, when and why, kept on its own row and in the audit log, in one transaction."""
    statuses = await _statuses(db, job.id)
    if refusal := await _override_refusal(db, job, statuses):
        raise HTTPException(409, refusal)
    db.add(JobChecklistOverride(job_id=job.id, reason=reason, overridden_by_user_id=user.id))
    _audit(db, user, "recruiter_requirement.checklist_override", "job", job.id,
           {"reason": reason, "incomplete": [i["key"] for i in _incomplete(statuses)], "changes": {"Checklist override": [None, reason]}})  # fmt: skip


async def set_global_rule(db: AsyncSession, user: User, block: bool) -> None:
    row = await db.get(RequirementChecklistSetting, 1, with_for_update=True)
    before = row.block_sourcing if row else False
    if before == block:
        return
    if row is None:
        db.add(RequirementChecklistSetting(id=1, block_sourcing=block, updated_by_user_id=user.id))
    else:
        row.block_sourcing, row.updated_by_user_id = block, user.id
    _audit(db, user, "requirement_checklist.global_rule", "requirement_checklist_settings", "all", {"changes": {"block_sourcing": [before, block]}})


def set_company_rule(db: AsyncSession, user: User, company: Company, block: bool | None) -> None:
    before = company.checklist_blocks_sourcing
    if before != block:
        company.checklist_blocks_sourcing = block
        _audit(db, user, "requirement_checklist.company_rule", "company", company.id, {"changes": {"block_sourcing": [before, block]}})


async def view(db: AsyncSession, job: Job) -> dict:
    """The whole checklist. One query for the items, their follow-ups and contacts. `overridable` is the state; the route adds who may act."""
    rows = (await db.execute(
        select(JobChecklistItem, RecruiterFollowUp, CompanyContact)
        .outerjoin(RecruiterFollowUp, RecruiterFollowUp.id == JobChecklistItem.follow_up_id)
        .outerjoin(CompanyContact, CompanyContact.id == RecruiterFollowUp.contact_id)
        .where(JobChecklistItem.job_id == job.id)
    )).all()  # fmt: skip
    answered = {item.item_key: (item, fu, contact) for item, fu, contact in rows}
    statuses = {key: entry[0].status for key, entry in answered.items()}
    items = []
    for key, label, hint in ITEMS:
        _, fu, contact = answered.get(key, (None, None, None))
        items.append({
            "key": key, "label": label, "hint": hint, "status": statuses.get(key),
            "follow_up": None if fu is None else {"id": fu.id, "status": fu.status, "due_at": fu.due_at, "contact": contact.name if contact else None},
        })  # fmt: skip
    counted = [statuses.get(key) for key in KEYS]
    summary = {"total": len(KEYS), "confirmed": counted.count("confirmed"), "not_applicable": counted.count("not_applicable"), "missing": counted.count("missing"),
               "not_reviewed": counted.count(None), "complete": not _incomplete(statuses)}  # fmt: skip
    started = await _started(db, job)
    stored = await _override(db, job.id)
    outstanding = len(_incomplete(statuses))
    return {
        "items": items,
        "summary": summary,
        "blocking": await _blocking(db, job.company_id),
        "override": None if stored is None else {"reason": stored.reason, "by": person(await db.get(User, stored.overridden_by_user_id)), "at": stored.created_at},
        "sourcing_started": started,
        "warning": f"Sourcing has already started, so this does not stop it. {outstanding} of {len(KEYS)} items still need an answer." if started and outstanding else None,  # C10
        "overridable": await _override_refusal(db, job, statuses) is None,
    }
