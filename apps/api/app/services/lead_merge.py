"""itc-007 (DEC-SCOPE-339): merge a duplicate lead (the victim) into the lead that stays (the survivor).

The route gives both leads' scope filters; the victim is found by its Lead ID inside that scope (anything else reads as missing, 404), so a
merge never shows a lead the caller could not already see. Both rows are locked FOR UPDATE in id order, so two merges of a crossing pair
serialise instead of deadlocking, and every check is repeated on the locked rows. The victim's activity moves to the survivor (one UPDATE
per table), its empty-on-the-survivor fields fill in, and it closes as a Duplicate of the survivor, merged and read only. One `lead.merge`
audit row on the survivor carries the moved counts and itc-001's field changes. Functions only; nothing here commits. Logs carry ids and
counts, never names, phones or the reason text."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED, label
from app.models import (
    LEAD_APPOINTMENT_OPEN,
    Appointment,
    AuditLog,
    CounselorTask,
    Enquiry,
    LeadCall,
    LeadEnglishTest,
    LeadEnquiry,
    LeadFollowUp,
    LeadMeeting,
    LeadMessage,
    LeadNote,
    LeadQualification,
    User,
)
from app.services import audit_changes, lead_pipeline

logger = logging.getLogger("app.leads")

# The lead fields the merge form compares; schemas.LeadMergeField repeats them.
FIELDS = ("name", "email", "phone", "whatsapp_number", "city", "state", "qualification", "passing_year", "institution")
# What moves with the lead (each belongs to the lead by `lead_id`); the victim's stage history and audit rows stay its own.
MOVED = {
    "calls": LeadCall,
    "follow_ups": LeadFollowUp,
    "notes": LeadNote,
    "messages": LeadMessage,
    "meetings": LeadMeeting,
    "appointments": Appointment,
    "enquiries": LeadEnquiry,
    "tasks": CounselorTask,
}
_QUALIFICATION_SKIP = {"lead_id", "updated_by_user_id", "created_at", "updated_at"}

MANAGER_ONLY = "Only a manager can merge leads"
VICTIM_SELF = "A lead cannot be merged into itself"
OTHER_TEAM = "Both leads must belong to the same team"
LEAD_CLOSED = "Only open leads can be merged. Reopen the closed lead first"
VICTIM_LINKED = "That lead is linked to a student. Merge this lead into it instead"
APPOINTMENT_MERGED = "Lead merged"


def _empty(value) -> bool:
    return value is None or value == ""


async def find_pair(db: AsyncSession, survivor_id: UUID, code: str, filters: list) -> tuple[Enquiry, Enquiry]:
    """The survivor and the victim (by Lead ID), both within the caller's scope (404 otherwise); itself 422; another team 409."""
    survivor = await db.scalar(select(Enquiry).where(Enquiry.id == survivor_id, *filters))
    if survivor is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    victim = await db.scalar(select(Enquiry).where(Enquiry.lead_code == code, *filters))
    if victim is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    if victim.id == survivor.id:
        raise lead_pipeline.invalid("victim", VICTIM_SELF, code)
    if victim.division != survivor.division:
        raise HTTPException(409, OTHER_TEAM)
    return survivor, victim


def check(survivor: Enquiry, victim: Enquiry) -> None:
    """AC3: both open; the victim has no student (one lead per student, and its milestones are the student's)."""
    if survivor.status in CLOSED or victim.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    if victim.converted_user_id is not None or victim.status in ("application_enrollment", "converted"):
        raise HTTPException(409, VICTIM_LINKED)


async def lock_pair(db: AsyncSession, survivor_id: UUID, victim_id: UUID, filters: list) -> tuple[Enquiry, Enquiry]:
    """Both rows FOR UPDATE in id order, still within scope (a lead reassigned meanwhile is 404), then checked again."""
    stmt = select(Enquiry).where(Enquiry.id.in_([survivor_id, victim_id]), *filters).order_by(Enquiry.id).with_for_update()
    rows = {row.id: row for row in (await db.scalars(stmt.execution_options(populate_existing=True))).all()}
    if len(rows) != 2:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    survivor, victim = rows[survivor_id], rows[victim_id]
    check(survivor, victim)
    return survivor, victim


async def _counts(db: AsyncSession, victim_id: UUID) -> dict:
    counts = {key: await db.scalar(select(func.count()).select_from(model).where(model.lead_id == victim_id)) or 0 for key, model in MOVED.items()}
    counts["enquiries"] += 1  # the victim's own enquiry is kept on the survivor too
    return counts


def _side(lead: Enquiry) -> dict:
    return {"id": lead.id, "lead_code": lead.lead_code, "status": lead.status, "status_label": label(lead.status), **{field: getattr(lead, field) for field in FIELDS}}


async def preview(db: AsyncSession, survivor_id: UUID, code: str, filters: list) -> dict:
    """The merge form's comparison: both leads side by side and what would move. Read only."""
    survivor, victim = await find_pair(db, survivor_id, code, filters)
    check(survivor, victim)
    return {"survivor": _side(survivor), "victim": _side(victim), "moved": await _counts(db, victim.id)}


async def _merge_qualification(db: AsyncSession, actor: User, survivor: Enquiry, victim: Enquiry) -> None:
    """Fill-empty-only: the survivor's empty answers take the victim's; a survivor without answers takes the victim's row. English
    tests move only when the survivor has none."""
    mine = await db.get(LeadQualification, survivor.id)
    theirs = await db.get(LeadQualification, victim.id)
    if theirs is not None and mine is None:
        await db.execute(update(LeadQualification).where(LeadQualification.lead_id == victim.id).values(lead_id=survivor.id).execution_options(synchronize_session=False))
    elif theirs is not None:
        filled = False
        for column in LeadQualification.__table__.columns.keys():
            if column not in _QUALIFICATION_SKIP and _empty(getattr(mine, column)) and not _empty(getattr(theirs, column)):
                setattr(mine, column, getattr(theirs, column))
                filled = True
        if filled:
            mine.updated_by_user_id = actor.id
    if await db.scalar(select(func.count()).select_from(LeadEnglishTest).where(LeadEnglishTest.lead_id == survivor.id)) == 0:
        await db.execute(update(LeadEnglishTest).where(LeadEnglishTest.lead_id == victim.id).values(lead_id=survivor.id).execution_options(synchronize_session=False))


async def merge_by_code(db: AsyncSession, actor: User, survivor_id: UUID, code: str, use_victim: list[str], reason: str | None, filters: list) -> dict:
    """Both merge routes: find, lock, merge. The route commits. Returns the route's body."""
    _, found = await find_pair(db, survivor_id, code, filters)
    survivor, victim = await lock_pair(db, survivor_id, found.id, filters)
    moved = await merge(db, actor, survivor, victim, use_victim, reason)
    return {"id": survivor_id, "victim_id": victim.id, "victim_code": victim.lead_code, "moved": moved}


async def merge(db: AsyncSession, actor: User, survivor: Enquiry, victim: Enquiry, use_victim: list[str], reason: str | None) -> dict:
    """The caller holds both locks (`lock_pair`). Returns the moved counts."""
    before = {field: getattr(survivor, field) for field in FIELDS}
    for field in FIELDS:
        value = getattr(victim, field)
        if not _empty(value) and (field in use_victim or _empty(getattr(survivor, field))):
            setattr(survivor, field, value)
    await _merge_qualification(db, actor, survivor, victim)

    # one open appointment per lead (uq_appointments_lead_open): when both have one, the survivor's stays (lock order lead -> appointment)
    survivor_open = await db.scalar(select(Appointment.id).where(Appointment.lead_id == survivor.id, Appointment.status.in_(LEAD_APPOINTMENT_OPEN)))
    if survivor_open is not None:
        await lead_pipeline.cancel_open_appointments(db, victim, actor, APPOINTMENT_MERGED, "lead_merged")
        await db.flush()
    moved = {}
    for key, model in MOVED.items():
        result = await db.execute(update(model).where(model.lead_id == victim.id).values(lead_id=survivor.id).execution_options(synchronize_session=False))
        moved[key] = result.rowcount
    db.add(
        LeadEnquiry(
            lead_id=survivor.id,
            subject=victim.subject,
            message=victim.message,
            source=victim.source,
            campaign_id=victim.campaign_id,
            metadata_json={"merged_from": victim.lead_code},
            created_by_user_id=actor.id,
            created_at=victim.created_at,
        )
    )
    moved["enquiries"] += 1
    # a lead closed as a Duplicate of the victim now names the survivor (no duplicate of a duplicate, ccrm-006)
    await db.execute(update(Enquiry).where(Enquiry.duplicate_of_id == victim.id).values(duplicate_of_id=survivor.id).execution_options(synchronize_session=False))

    await lead_pipeline.record_stage(db, victim, "duplicate", "merge", actor.id, reason or f"Merged into {survivor.lead_code}")
    # after the stage (as person_move's closure), all in one assignment, so the next flush satisfies the closure and merged CHECKs
    victim.duplicate_of_id, victim.merged_by_user_id, victim.merged_at = survivor.id, actor.id, victim.stage_changed_at

    metadata = {"victim_id": str(victim.id), "victim_code": victim.lead_code, "moved": moved, "use_victim": sorted(use_victim)}
    if changed := audit_changes.changes(before, {field: getattr(survivor, field) for field in FIELDS}):
        metadata["changes"] = changed
    db.add(AuditLog(user_id=actor.id, action="lead.merge", entity_type="enquiry", entity_id=str(survivor.id), metadata_json=metadata))
    logger.info("lead_merged", extra={"extra_fields": {"survivor_id": str(survivor.id), "victim_id": str(victim.id), "actor_id": str(actor.id), **moved}})
    return moved
