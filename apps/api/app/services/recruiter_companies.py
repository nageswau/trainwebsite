"""rec-003 (DEC-SCOPE-121, spec §4): the company master's scope, permissions, duplicates, lookups and output.

Functions only; nothing here commits -- the route owns the transaction. Every `{company_id}` resolves through `load_scoped`, so an id
outside the caller's scope is the same 404 as a missing one (the bdm-002 pattern). Logs carry ids, route and counts, never names."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, literal_column, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    COMPANY_NAME_KEY_SQL,
    AuditLog,
    Company,
    CompanyAssignmentHistory,
    CompanyBranch,
    CompanySkillDemand,
    RecCampaign,
    RecCompanySize,
    RecIndustry,
    RecLeadSource,
    RecruiterCall,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterMessage,
    RecruiterProfile,
    Skill,
    User,
)
from app.recruiter_stages import label as stage_label
from app.services.permissions import user_has_grant
from app.services.recruiter import MANAGER_ROLE, ROLE, recruiter_context

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Company not found"
MAX_DUPLICATE_MATCHES = 10
REASSIGN_INVALID = "Choose an active recruiter from your team"
EMPLOYER_LEAD_SOURCE = "website"  # D3: the seeded rec_lead_sources row, matched case-insensitively
# The duplicate key in SQL, spelled exactly as ix_companies_name_key so the planner can use it: trimmed, inner whitespace collapsed,
# lower-cased. name_key() is the same in Python. Only ever queried against `companies` alone.
NAME_KEY = literal_column(COMPANY_NAME_KEY_SQL)
REFUSALS = {
    "can_edit": "Only the assigned recruiter can edit this company",
    "can_archive": "Only the assigned recruiter can archive this company",
    "can_restore": "Only a placement manager can restore this company",
    "can_reassign": "Only a placement manager can reassign this company",
}
MERGED = "This company was merged into another one"  # pob-006 M6
STATE_REFUSALS = {"can_edit": "Restore this company first", "can_archive": "Already archived", "can_restore": "Already active", "can_reassign": "Restore this company first"}
# rec-024 FU9: a company's next follow-up is its earliest open one -- derived, never stored (correlated, so the list stays one query).
NEXT_FOLLOW_UP = (
    select(func.min(RecruiterFollowUp.due_at))
    .where(RecruiterFollowUp.company_id == Company.id, RecruiterFollowUp.status == "open")
    .correlate(Company)
    .scalar_subquery()
)
LOOKUPS = {  # field -> (model, the word in its 422)
    "industry_id": (RecIndustry, "industry"),
    "company_size_id": (RecCompanySize, "company size"),
    "lead_source_id": (RecLeadSource, "lead source"),
    "campaign_id": (RecCampaign, "campaign"),
}


SKILL_INACTIVE = "Choose an active skill"
BRANCH_FIELDS = ("city", "state", "country")


def name_key(name: str) -> str:
    return " ".join(name.split()).lower()


async def caller_scope(db: AsyncSession, user: User) -> list:
    """Read scope as SQL filters (spec §4). The manager filter is a sub-select, so `FOR UPDATE` never locks a profile row."""
    if user.role == ROLE:
        await recruiter_context(db, user)
        return [Company.assigned_recruiter_user_id == user.id]
    if user.role == MANAGER_ROLE:
        team = select(RecruiterProfile.user_id).where(RecruiterProfile.reporting_manager_user_id == user.id)
        return [or_(Company.assigned_recruiter_user_id.in_(team), Company.assigned_recruiter_user_id.is_(None))]
    if user.role == "super_admin":
        return []
    if user.role == "bdm":  # R10: the assigned BDM reads
        return [Company.assigned_bdm_user_id == user.id]
    raise HTTPException(403, "Recruiter role required")


async def load_scoped(db: AsyncSession, user: User, company_id: UUID, *, lock: bool = False) -> Company:
    """With `lock`, the row is locked by id first and scope is checked in a fresh statement (bdm-025: a FOR UPDATE that waited on a
    concurrent reassign must see the new assignee, not drop the row as out of scope)."""
    stmt = select(Company).where(Company.id == company_id, *await caller_scope(db, user))
    if lock:
        await db.execute(select(Company.id).where(Company.id == company_id).with_for_update())
        stmt = stmt.execution_options(populate_existing=True)
    company = await db.scalar(stmt)
    if company is None:
        raise HTTPException(404, NOT_FOUND)
    return company


def _allowed(user: User, company: Company, action: str) -> bool:
    if action in ("can_edit", "can_archive"):
        return user.role == "super_admin" or (user.role == ROLE and company.assigned_recruiter_user_id == user.id)
    return user.role in (MANAGER_ROLE, "super_admin")


def permissions(user: User, company: Company) -> dict[str, bool]:
    archived = company.archived_at is not None
    if company.merged_into_id is not None:  # pob-006 M6: final, a merged record is never restored
        return dict.fromkeys(REFUSALS, False)
    return {a: _allowed(user, company, a) and (archived if a == "can_restore" else not archived) for a in REFUSALS}


def require(user: User, company: Company, action: str, route: str) -> None:
    """403 for the wrong role first (logged), then 409 for the wrong state."""
    if not _allowed(user, company, action):
        logger.warning("recruiter_company_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "company_id": str(company.id), "route": route}})
        raise HTTPException(403, REFUSALS[action])
    if company.merged_into_id is not None:
        raise HTTPException(409, MERGED)
    if not permissions(user, company)[action]:
        raise HTTPException(409, STATE_REFUSALS[action])


async def require_crm(db: AsyncSession, user: User, action: str, refusal: str) -> None:
    """pob-006 (G2): a company writer role holding `crm.import` / `crm.merge`; a grant never lets another role in. Scope still comes from `load_scoped`."""
    if user.role not in (ROLE, MANAGER_ROLE, "super_admin") or not await user_has_grant(db, user, "crm", action):
        raise HTTPException(403, refusal)
    if user.role == ROLE:
        await recruiter_context(db, user)  # a recruiter without a profile is 403


def team_ids(user: User):
    """The manager's direct reports, as a sub-select."""
    return select(RecruiterProfile.user_id).where(RecruiterProfile.reporting_manager_user_id == user.id)


def require_creator(user: User) -> None:
    if user.role not in (ROLE, MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, "Your role cannot create companies")


async def check_name(db: AsyncSession, name: str, confirm: bool, exclude_id: UUID | None = None) -> int:
    """D2: an exact name is a hard 409 (`companies.name` stays unique: EMP-001 and /workflows/it/jobs rely on it); a normalised match
    is a 409 the user may override with confirm_duplicate. Searches every company, archived included. Returns the override count."""
    others = [Company.id != exclude_id] if exclude_id else []
    if await db.scalar(select(Company.id).where(Company.name == name, *others)):
        raise HTTPException(409, "A company with this name already exists")
    conditions = [NAME_KEY == name_key(name), *others]
    total = await db.scalar(select(func.count()).select_from(Company).where(*conditions)) or 0
    if total and not confirm:
        rows = (await db.scalars(select(Company).where(*conditions).order_by(Company.company_code).limit(MAX_DUPLICATE_MATCHES))).all()
        matches = [{"id": str(c.id), "code": c.company_code, "name": c.name, "city": c.city, "archived": c.archived_at is not None} for c in rows]
        raise HTTPException(409, {"message": "A similar company already exists", "code": "possible_duplicate", "matches": matches, "total": total})
    return total


async def check_references(db: AsyncSession, values: dict, stored: Company | None) -> None:
    """Catalogue values and the BDM must be active when they are set or changed (FOR SHARE: a concurrent deactivation waits for this
    commit); keeping a since-deactivated value is allowed. A campaign belongs to one lead source: alone it brings that source, and a
    different source is a 422. Mutates `values` (the campaign's source)."""
    for field, (model, word) in LOOKUPS.items():
        new = values.get(field)
        if new is None or (stored is not None and getattr(stored, field) == new):
            continue
        row = await db.scalar(select(model).where(model.id == new).with_for_update(read=True))
        if row is None or not row.active:
            raise HTTPException(422, f"Choose an active {word}")
    campaign_id = values.get("campaign_id", stored.campaign_id if stored else None)
    if campaign_id is not None:
        source_of_campaign = await db.scalar(select(RecCampaign.lead_source_id).where(RecCampaign.id == campaign_id))
        source = values["lead_source_id"] if "lead_source_id" in values else (stored.lead_source_id if stored else None)
        if source is None:
            values["lead_source_id"] = source_of_campaign
        elif source != source_of_campaign:
            raise HTTPException(422, "The campaign belongs to another lead source")
    bdm_id = values.get("assigned_bdm_user_id")
    if bdm_id is not None and (stored is None or stored.assigned_bdm_user_id != bdm_id):
        bdm = await db.scalar(select(User).where(User.id == bdm_id).with_for_update(read=True))
        if bdm is None or not bdm.active or bdm.role != "bdm":
            raise HTTPException(422, "Choose an active BDM")


async def locked_recruiter_target(db: AsyncSession, user: User, recruiter_id: UUID) -> User:
    """An active recruiter with a profile who reports to this manager (any team for super_admin). FOR SHARE on the user row (rec-001's
    locked_active_manager rule). One message for every invalid target, so the route can't be used to probe users."""
    target = await db.scalar(select(User).where(User.id == recruiter_id).with_for_update(read=True))
    profile = await db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == recruiter_id)) if target else None
    valid = target is not None and target.active and target.role == ROLE and profile is not None
    if not valid or (user.role != "super_admin" and profile.reporting_manager_user_id != user.id):
        raise HTTPException(422, REASSIGN_INVALID)
    return target


def record_assignment(db: AsyncSession, user: User, company: Company, to_user_id: UUID) -> None:
    db.add(CompanyAssignmentHistory(company_id=company.id, from_user_id=company.assigned_recruiter_user_id, to_user_id=to_user_id, changed_by_user_id=user.id))
    company.assigned_recruiter_user_id = to_user_id


async def employer_lead_source_id(db: AsyncSession) -> UUID | None:
    return await db.scalar(select(RecLeadSource.id).where(func.lower(RecLeadSource.name) == EMPLOYER_LEAD_SOURCE, RecLeadSource.active.is_(True)))


async def stored_relations(db: AsyncSession, company_id: UUID) -> tuple[list[dict], list[UUID]]:
    """pob-003 D1/D3: the branch rows and the skill-demand ids, each in the saved order."""
    branches = (await db.scalars(select(CompanyBranch).where(CompanyBranch.company_id == company_id).order_by(CompanyBranch.position))).all()
    skills = (await db.scalars(select(CompanySkillDemand.skill_id).where(CompanySkillDemand.company_id == company_id).order_by(CompanySkillDemand.position))).all()
    return [{f: getattr(b, f) for f in BRANCH_FIELDS} for b in branches], list(skills)


async def save_relations(db: AsyncSession, company_id: UUID, values: dict) -> list[str]:
    """pob-003 D1/D3: replace the sent sets (`branch_locations`, `skill_demand_ids`) when they differ from the stored ones; returns the
    changed field names. A newly added skill must exist and be active (FOR SHARE: a concurrent deactivation waits); a kept one may not be."""
    branches, skills = await stored_relations(db, company_id)
    changed = []
    if "branch_locations" in values:
        sent = [{f: b.get(f) for f in BRANCH_FIELDS} for b in values["branch_locations"]]  # exclude_unset drops an unsent state/country
        if sent != branches:
            await db.execute(delete(CompanyBranch).where(CompanyBranch.company_id == company_id))
            db.add_all(CompanyBranch(company_id=company_id, position=i, **b) for i, b in enumerate(sent))
            changed.append("branch_locations")
    if "skill_demand_ids" in values:
        sent_ids = list(values["skill_demand_ids"])
        added = set(sent_ids) - set(skills)
        if added:
            active = (await db.scalars(select(Skill.id).where(Skill.id.in_(added), Skill.active.is_(True)).with_for_update(read=True))).all()
            if len(active) != len(added):
                raise HTTPException(422, SKILL_INACTIVE)
        if sent_ids != skills:
            await db.execute(delete(CompanySkillDemand).where(CompanySkillDemand.company_id == company_id))
            db.add_all(CompanySkillDemand(company_id=company_id, skill_id=s, position=i) for i, s in enumerate(sent_ids))
            changed.append("skill_demand_ids")
    return changed


async def refresh_last_contact(db: AsyncSession, company_id: UUID | None) -> None:
    """pob-003 D4: recompute `last_contacted_at` from the company's calls, messages and completed meetings, in the caller's transaction.
    The row is locked first and the UPDATE is a new statement, so it sees every concurrent writer that committed before it (a later one
    recomputes after us). `updated_at` is kept: activity is not an edit of the company."""
    if company_id is None:
        return
    await db.execute(select(Company.id).where(Company.id == company_id).with_for_update())
    latest = func.greatest(
        select(func.max(RecruiterCall.occurred_at)).where(RecruiterCall.company_id == company_id).scalar_subquery(),
        select(func.max(RecruiterMessage.sent_at)).where(RecruiterMessage.company_id == company_id).scalar_subquery(),
        select(func.max(RecruiterMeeting.starts_at)).where(RecruiterMeeting.company_id == company_id, RecruiterMeeting.status == "completed").scalar_subquery(),
    )
    await db.execute(
        update(Company).where(Company.id == company_id).values(last_contacted_at=latest, updated_at=Company.updated_at).execution_options(synchronize_session=False)
    )


def person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name, "active": user.active} if user else None


def ref(row) -> dict | None:
    return {"id": row.id, "name": row.name, "active": row.active} if row else None


def row_out(user: User, company: Company, industry, source, recruiter: User | None, next_follow_up_at=None) -> dict:
    return {
        "id": company.id,
        "code": company.company_code,
        "name": company.name,
        "city": company.city,
        "priority": company.priority,
        "industry": ref(industry),
        "lead_source": ref(source),
        "assigned_recruiter": person(recruiter),
        "archived": company.archived_at is not None,
        "permissions": permissions(user, company),
        "stage": company.stage,  # rec-005: the lead's Status (EVID-018 line 116)
        "stage_label": stage_label(company.stage),
        "lost": company.lost_at is not None,
        "next_follow_up_at": next_follow_up_at,
        "last_contacted_at": company.last_contacted_at,  # pob-003 D4
    }


async def company_out(db: AsyncSession, user: User, company: Company, *, refresh: bool = True) -> dict:
    """The detail every route returns. Refreshes first: server defaults (updated_at) are expired after a flush."""
    from app.services.company_pipeline import pipeline_out  # local: company_pipeline imports this module
    from app.services.recruiter_contracts import company_contract_ref  # local: recruiter_contracts imports this module

    if refresh:
        await db.refresh(company)
    history = (
        await db.scalars(select(CompanyAssignmentHistory).where(CompanyAssignmentHistory.company_id == company.id).order_by(CompanyAssignmentHistory.created_at.desc(), CompanyAssignmentHistory.id))
    ).all()
    user_ids = {company.assigned_recruiter_user_id, company.assigned_bdm_user_id, company.created_by_user_id} | {u for h in history for u in (h.from_user_id, h.to_user_id, h.changed_by_user_id)}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids - {None})))).all()}

    async def lookup(model, value):
        return await db.get(model, value) if value else None

    return {
        **row_out(
            user, company, await lookup(RecIndustry, company.industry_id), await lookup(RecLeadSource, company.lead_source_id),
            people.get(company.assigned_recruiter_user_id),
            await db.scalar(select(func.min(RecruiterFollowUp.due_at)).where(RecruiterFollowUp.company_id == company.id, RecruiterFollowUp.status == "open")),
        ),
        "website": company.website,
        "linkedin_url": company.linkedin_url,
        "company_size": ref(await lookup(RecCompanySize, company.company_size_id)),
        "employee_count": company.employee_count,
        "state": company.state,
        "country": company.country,
        "head_office": company.head_office,
        "branches": company.branches,
        "description": company.description,
        "campaign": ref(await lookup(RecCampaign, company.campaign_id)),
        "assigned_bdm": person(people.get(company.assigned_bdm_user_id)),
        "owner_type": company.owner_type,
        "created_by": person(people.get(company.created_by_user_id)),
        "assignment_history": [
            {"from_user": person(people.get(h.from_user_id)), "to_user": person(people[h.to_user_id]), "changed_by": person(people[h.changed_by_user_id]), "created_at": h.created_at} for h in history
        ],
        "pipeline": pipeline_out(user, company),
        "contract": await company_contract_ref(db, company),  # rec-030 CT10
        **await context_out(db, company),  # pob-003
        "merged_into": await merged_into_out(db, company),  # pob-006 M6
        "archived_at": company.archived_at,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


async def merged_into_out(db: AsyncSession, company: Company) -> dict | None:
    survivor = await db.get(Company, company.merged_into_id) if company.merged_into_id else None
    return {"id": survivor.id, "code": survivor.company_code, "name": survivor.name} if survivor else None


async def context_out(db: AsyncSession, company: Company) -> dict:
    """pob-003 D1-D3: the business context of the detail."""
    branches, skill_ids = await stored_relations(db, company.id)
    skills = {s.id: s for s in (await db.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()} if skill_ids else {}
    return {
        "products_services": company.products_services,
        "departments_hiring": company.departments_hiring or [],
        "hiring_locations": company.hiring_locations or [],
        "target_roles": company.target_roles or [],
        "branch_locations": branches,
        "skill_demand": [ref(skills[i]) for i in skill_ids],
    }


def audit(db: AsyncSession, user: User, action: str, company_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names and counts only."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_company.{action}", entity_type="company", entity_id=str(company_id), metadata_json=metadata or {}))


def log(event: str, user: User, company_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "company_id": str(company_id), **extra}})
