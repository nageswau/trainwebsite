"""pob-006 (DEC-SCOPE-418 M1-M8, C1-C6, AC3): merge a duplicate company into the company that stays, and a duplicate contact into the contact that stays, within
one company -- the hrc-014 / itc-007 merge shape.

Both records are found inside the caller's scope (anything else is a 404), locked in id order, and every rule is checked again on the locked rows. Everything that
points at the victim moves (one UPDATE per table; `test_every_reference_is_handled` fails when a new foreign key is not decided here). The victim stays, archived or
inactive, with `merged_into_id`. Functions only; nothing here commits. Logs and audit rows carry ids, counts and field names, never names or contact data."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Company,
    CompanyAssignmentHistory,
    CompanyBranch,
    CompanyContact,
    CompanyDocument,
    CompanySkillDemand,
    CompanyStageHistory,
    CrmImportRow,
    EmployerProfile,
    Interview,
    Job,
    JobDescription,
    ProfileShare,
    RecCompanySize,
    RecContactRole,
    RecIndustry,
    RecLeadSource,
    RecruiterCall,
    RecruiterContract,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterMeetingParticipant,
    RecruiterMessage,
    RecruitmentDrive,
    User,
)
from app.services import contact_status, recruiter_contacts, recruiter_contracts
from app.services import recruiter_companies as companies
from app.services.recruiter_contracts import effective_status

NO_MERGE = "Your role cannot merge duplicates"
MERGE_SELF = "A company cannot be merged into itself"
SURVIVOR_ARCHIVED = "Restore {code} before merging into it"
VICTIM_ARCHIVED = "{code} is archived. Restore it first"
VICTIM_MERGED = "{code} was already merged into another company"
VICTIM_EMPLOYER = "{code} is an employer's own account. Merge the other company into it instead"
BOTH_EMPLOYERS = "Both companies are employers' own accounts, so they cannot be merged"
BOTH_CONTRACTS = "Both companies have a contract in effect ({a} and {b}). End one before merging"
CONTACT_SELF = "A contact cannot be merged into itself"
CONTACT_MERGED = "This contact was already merged into another one"
COMPANY_ARCHIVED = "Restore this company before merging its contacts"

# M5: `use_victim` may pick these; an empty survivor field is filled regardless.
FIELDS = ("website", "linkedin_url", "industry_id", "company_size_id", "employee_count", "city", "state", "country", "head_office", "description", "lead_source_id", "priority", "products_services")
FILLED = ("branches", "departments_hiring", "hiring_locations", "target_roles", "assigned_bdm_user_id")  # filled when empty, never compared
CATALOGUE_FIELDS = {"industry_id": RecIndustry, "company_size_id": RecCompanySize, "lead_source_id": RecLeadSource}
IN_EFFECT = ("signed", "active")  # Q-06: effective status, so a lapsed end date no longer counts
MOVED = {
    "contacts": CompanyContact, "requirements": Job, "follow_ups": RecruiterFollowUp, "calls": RecruiterCall, "messages": RecruiterMessage, "meetings": RecruiterMeeting,
    "contracts": RecruiterContract, "documents": CompanyDocument, "shares": ProfileShare, "drives": RecruitmentDrive, "stage_history": CompanyStageHistory,
    "assignment_history": CompanyAssignmentHistory, "import_rows": CrmImportRow,
}  # fmt: skip
HANDLED = (CompanyBranch, CompanySkillDemand, EmployerProfile)  # M4's two rules; an employer's company is refused as the victim (M2)

CONTACT_FIELDS = ("name", "designation", "department", "role_id", "mobile", "email", "linkedin_url", "preferred_channel", "notes", "source", "verified_on")  # C3
CONTACT_MOVED = {
    "follow_ups": (RecruiterFollowUp, "contact_id"), "calls": (RecruiterCall, "contact_id"), "messages": (RecruiterMessage, "contact_id"), "meetings": (RecruiterMeeting, "contact_id"),
    "shares": (ProfileShare, "contact_id"), "requirements": (Job, "decision_maker_contact_id"), "job_descriptions": (JobDescription, "contact_id"), "interviews": (Interview, "contact_id"),
    "import_rows": (CrmImportRow, "contact_id"),
}  # fmt: skip


def _empty(value) -> bool:
    return value is None or value == "" or value == []


def _take(survivor, victim, fields: tuple[str, ...], use_victim: list[str]) -> list[str]:
    """M5/C3: the victim's value where it was chosen or the survivor has none. Returns the changed fields."""
    chosen = []
    for name in fields:
        value = getattr(victim, name)
        if not _empty(value) and (name in use_victim or _empty(getattr(survivor, name))) and value != getattr(survivor, name):
            setattr(survivor, name, value)
            chosen.append(name)
    return chosen


async def _repoint(db: AsyncSession, model, column: str, survivor_id: UUID, victim_id: UUID, *where) -> int:
    """One UPDATE; `updated_at` is kept where the table has one: a merge is not an edit of the row."""
    values = {column: survivor_id}
    if "updated_at" in model.__table__.c:
        values["updated_at"] = model.updated_at
    result = await db.execute(update(model).where(getattr(model, column) == victim_id, *where).values(**values).execution_options(synchronize_session=False))
    return result.rowcount


async def _display(db: AsyncSession, row, fields: tuple[str, ...], catalogues: dict) -> dict:
    """The preview's text per field: a catalogue value by its name, a date as ISO."""
    out = {}
    for name in fields:
        value = getattr(row, name)
        if name in catalogues and value is not None:
            found = await db.get(catalogues[name], value)
            value = found.name if found else None
        out[name] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


# --- companies ------------------------------------------------------------------------------------------------------------------------


async def _is_employers(db: AsyncSession, company: Company) -> bool:
    return (
        company.owner_type == "employer" or company.employer_user_id is not None or (await db.scalar(select(EmployerProfile.id).where(EmployerProfile.company_id == company.id).limit(1))) is not None
    )


async def _check(db: AsyncSession, survivor: Company, victim: Company) -> None:
    if victim.id == survivor.id:
        raise HTTPException(422, MERGE_SELF)
    if survivor.archived_at is not None:
        raise HTTPException(409, SURVIVOR_ARCHIVED.format(code=survivor.company_code))
    if victim.merged_into_id is not None:
        raise HTTPException(409, VICTIM_MERGED.format(code=victim.company_code))
    if victim.archived_at is not None:
        raise HTTPException(409, VICTIM_ARCHIVED.format(code=victim.company_code))
    if await _is_employers(db, victim):
        raise HTTPException(409, BOTH_EMPLOYERS if await _is_employers(db, survivor) else VICTIM_EMPLOYER.format(code=victim.company_code))


async def _find_victim(db: AsyncSession, user: User, code: str) -> Company:
    victim = await db.scalar(select(Company).where(func.upper(Company.company_code) == code.strip().upper(), *await companies.caller_scope(db, user)))
    if victim is None:
        raise HTTPException(404, companies.NOT_FOUND)
    return victim


async def _contracts(db: AsyncSession, survivor: Company, victim: Company) -> tuple[RecruiterContract | None, RecruiterContract | None, bool]:
    """(the survivor's current contract, the victim's, whether both are in effect)."""
    on = recruiter_contracts.today()
    mine, theirs = await recruiter_contracts.load_current(db, survivor), await recruiter_contracts.load_current(db, victim)
    both = bool(mine and theirs) and effective_status(mine, on) in IN_EFFECT and effective_status(theirs, on) in IN_EFFECT
    return mine, theirs, both


async def _moved_counts(db: AsyncSession, victim: Company) -> dict:
    return {key: await db.scalar(select(func.count()).select_from(model).where(model.company_id == victim.id)) for key, model in MOVED.items() if key != "import_rows"}


async def _side(db: AsyncSession, company: Company) -> dict:
    recruiter = await db.get(User, company.assigned_recruiter_user_id) if company.assigned_recruiter_user_id else None
    return {
        "id": company.id, "code": company.company_code, "name": company.name, "stage": company.stage, "assigned_recruiter": recruiter.full_name if recruiter else None,
        "values": await _display(db, company, FIELDS, CATALOGUE_FIELDS),
    }  # fmt: skip


async def preview(db: AsyncSession, user: User, survivor_id: UUID, code: str) -> dict:
    """Both sides, what would move and what blocks the merge (Merge is disabled then). Read only."""
    survivor = await companies.load_scoped(db, user, survivor_id)
    victim = await _find_victim(db, user, code)
    await _check(db, survivor, victim)
    _, _, both = await _contracts(db, survivor, victim)
    return {
        "survivor": await _side(db, survivor), "victim": await _side(db, victim), "fields": list(FIELDS), "moved": await _moved_counts(db, victim),
        "blocked": [BOTH_CONTRACTS.format(a=survivor.company_code, b=victim.company_code)] if both else [],
    }  # fmt: skip


async def _settle_contracts(db: AsyncSession, survivor: Company, victim: Company) -> None:
    """M3: one current contract after the move. Both in effect is refused; else the one in effect stays current, and neither in effect keeps the survivor's."""
    mine, theirs, both = await _contracts(db, survivor, victim)
    if both:
        raise HTTPException(409, BOTH_CONTRACTS.format(a=survivor.company_code, b=victim.company_code))
    if mine and theirs:
        theirs_in_effect = effective_status(theirs, recruiter_contracts.today()) in IN_EFFECT
        (mine if theirs_in_effect else theirs).is_current = False
        await db.flush()


async def _move_children(db: AsyncSession, survivor: Company, victim: Company) -> dict:
    moved = {}
    has_primary = await db.scalar(select(CompanyContact.id).where(CompanyContact.company_id == survivor.id, CompanyContact.is_primary.is_(True)).limit(1))
    if has_primary:
        await db.execute(
            update(CompanyContact).where(CompanyContact.company_id == victim.id).values(is_primary=False, updated_at=CompanyContact.updated_at).execution_options(synchronize_session=False)
        )
    for key, model in MOVED.items():
        moved[key] = await _repoint(db, model, "company_id", survivor.id, victim.id)
    has_branches = await db.scalar(select(CompanyBranch.id).where(CompanyBranch.company_id == survivor.id).limit(1))
    moved["branches"] = 0 if has_branches else await _repoint(db, CompanyBranch, "company_id", survivor.id, victim.id)
    survivor_skills = select(CompanySkillDemand.skill_id).where(CompanySkillDemand.company_id == survivor.id).scalar_subquery()
    moved["skills"] = await _repoint(db, CompanySkillDemand, "company_id", survivor.id, victim.id, CompanySkillDemand.skill_id.not_in(survivor_skills))
    return moved


async def merge(db: AsyncSession, actor: User, survivor_id: UUID, code: str, use_victim: list[str], reason: str | None) -> dict:
    """Find, lock, check, move. The route commits. Returns the route's body."""
    found = await _find_victim(db, actor, code)
    await _check(db, await companies.load_scoped(db, actor, survivor_id), found)  # 404 / 422 / 409 before anything is locked (and again once locked)
    await db.execute(select(Company.id).where(Company.id.in_([survivor_id, found.id])).order_by(Company.id).with_for_update())
    survivor = await companies.load_scoped(db, actor, survivor_id)
    await db.refresh(survivor)
    await db.refresh(found)
    await companies.load_scoped(db, actor, found.id)
    await _check(db, survivor, found)
    victim = found
    await _settle_contracts(db, survivor, victim)

    chosen = _take(survivor, victim, FIELDS, use_victim)
    filled = _take(survivor, victim, FILLED, [])
    if "lead_source_id" in chosen and victim.campaign_id != survivor.campaign_id:  # a campaign belongs to one lead source, so it travels with it
        survivor.campaign_id = victim.campaign_id
    if survivor.assigned_recruiter_user_id is None and victim.assigned_recruiter_user_id is not None:
        companies.record_assignment(db, actor, survivor, victim.assigned_recruiter_user_id)
    await db.flush()

    moved = await _move_children(db, survivor, victim)
    now = datetime.now(UTC)
    await db.execute(
        update(Company).where(Company.merged_into_id == victim.id).values(merged_into_id=survivor.id, updated_at=Company.updated_at).execution_options(synchronize_session=False)
    )  # one hop, always
    victim.archived_at, victim.merged_into_id, victim.merged_at, victim.merged_by_user_id = now, survivor.id, now, actor.id
    await db.flush()
    await companies.refresh_last_contact(db, survivor.id)
    companies.audit(
        db, actor, "merge", survivor.id, {"victim_id": str(victim.id), "victim_code": victim.company_code, "moved": moved, "use_victim": sorted(use_victim), "fields": sorted(chosen + filled)}
    )
    companies.audit(db, actor, "merged_into", victim.id, {"survivor_id": str(survivor.id), "survivor_code": survivor.company_code, "reason": reason})
    companies.log("recruiter_company_merged", actor, survivor.id, victim_id=str(victim.id), **moved)
    return {"id": survivor.id, "code": survivor.company_code, "victim_id": victim.id, "victim_code": victim.company_code, "moved": moved}


# --- contacts ---------------------------------------------------------------------------------------------------------------------------


async def _contact_pair(db: AsyncSession, user: User, survivor_id: UUID, victim_id: UUID, *, lock: bool = False) -> tuple[Company, CompanyContact, CompanyContact]:
    """Both of one company, in the caller's scope (the rest is the same 404). Refreshed: another request may have just merged either."""
    company_id = await db.scalar(select(CompanyContact.company_id).where(CompanyContact.id == survivor_id))
    if company_id is None:
        raise HTTPException(404, recruiter_contacts.CONTACT_NOT_FOUND)
    try:
        company = await companies.load_scoped(db, user, company_id, lock=lock)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, recruiter_contacts.CONTACT_NOT_FOUND) from None
        raise
    if survivor_id == victim_id:
        raise HTTPException(422, CONTACT_SELF)
    rows = (await db.scalars(select(CompanyContact).where(CompanyContact.id.in_([survivor_id, victim_id]), CompanyContact.company_id == company_id).execution_options(populate_existing=True))).all()
    if len(rows) != 2:
        raise HTTPException(404, recruiter_contacts.CONTACT_NOT_FOUND)
    if company.archived_at is not None:
        raise HTTPException(409, COMPANY_ARCHIVED)
    survivor, victim = (rows[0], rows[1]) if rows[0].id == survivor_id else (rows[1], rows[0])
    if survivor.merged_into_id is not None or victim.merged_into_id is not None:
        raise HTTPException(409, CONTACT_MERGED)
    return company, survivor, victim


async def _contact_side(db: AsyncSession, contact: CompanyContact) -> dict:
    return {
        "id": contact.id, "name": contact.name, "status": contact.status, "is_primary": contact.is_primary, "is_decision_maker": contact.is_decision_maker, "active": contact.active,
        "values": await _display(db, contact, CONTACT_FIELDS, {"role_id": RecContactRole}),
    }  # fmt: skip


async def _contact_moved_counts(db: AsyncSession, victim: CompanyContact) -> dict:
    out = {}
    for key, (model, column) in CONTACT_MOVED.items():
        if key != "import_rows":
            out[key] = await db.scalar(select(func.count()).select_from(model).where(getattr(model, column) == victim.id))
    out["meeting_participants"] = await db.scalar(select(func.count()).select_from(RecruiterMeetingParticipant).where(RecruiterMeetingParticipant.contact_id == victim.id))
    return out


async def contact_preview(db: AsyncSession, user: User, survivor_id: UUID, victim_id: UUID) -> dict:
    company, survivor, victim = await _contact_pair(db, user, survivor_id, victim_id)
    return {
        "company": {"id": company.id, "code": company.company_code, "name": company.name}, "survivor": await _contact_side(db, survivor), "victim": await _contact_side(db, victim),
        "fields": list(CONTACT_FIELDS), "moved": await _contact_moved_counts(db, victim),
    }  # fmt: skip


async def merge_contact(db: AsyncSession, actor: User, survivor_id: UUID, victim_id: UUID, use_victim: list[str], reason: str | None) -> dict:
    """The company row lock serialises every contact write of that company (rec-004). The route commits."""
    company, survivor, victim = await _contact_pair(db, actor, survivor_id, victim_id, lock=True)
    chosen = _take(survivor, victim, CONTACT_FIELDS, use_victim)
    survivor.is_decision_maker = survivor.is_decision_maker or victim.is_decision_maker  # C4
    survivor.active = survivor.active or victim.active
    was_primary = victim.is_primary
    victim.is_primary, victim.active = False, False
    victim.merged_into_id, victim.merged_at, victim.merged_by_user_id = survivor.id, datetime.now(UTC), actor.id
    await db.flush()
    if was_primary:
        survivor.is_primary = True
        await db.flush()
    if victim.status == "do_not_contact" and survivor.status != "do_not_contact":  # C4: pob-005 D6 stays true for this person
        contact_status.record(db, actor, survivor, "do_not_contact", "merge")

    moved = {}
    for key, (model, column) in CONTACT_MOVED.items():
        moved[key] = await _repoint(db, model, column, survivor.id, victim.id)
    attending = select(RecruiterMeetingParticipant.meeting_id).where(RecruiterMeetingParticipant.contact_id == survivor.id).scalar_subquery()
    moved["meeting_participants"] = await _repoint(db, RecruiterMeetingParticipant, "contact_id", survivor.id, victim.id, RecruiterMeetingParticipant.meeting_id.not_in(attending))
    participants = RecruiterMeetingParticipant.__table__
    await db.execute(participants.delete().where(participants.c.contact_id == victim.id))  # the survivor already attends those
    await db.execute(
        update(CompanyContact).where(CompanyContact.merged_into_id == victim.id).values(merged_into_id=survivor.id, updated_at=CompanyContact.updated_at).execution_options(synchronize_session=False)
    )
    await db.flush()
    companies.audit(db, actor, "contact_merge", company.id, {
        "contact_id": str(survivor.id), "victim_id": str(victim.id), "moved": moved, "use_victim": sorted(use_victim), "fields": sorted(chosen), "reason": reason,
    })  # fmt: skip
    companies.log("recruiter_contact_merged", actor, company.id, contact_id=str(survivor.id), victim_id=str(victim.id), **moved)
    return {"id": survivor.id, "victim_id": victim.id, "company_id": company.id, "moved": moved}
