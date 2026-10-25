"""tel-004 (DEC-SCOPE-081, spec §4): the lead pipeline -- the only writer of `enquiries.status` after a lead is created.

System events (tel-007/010/016/018 and the admin student link) call `apply_event`; people call `person_move`. Both work on a row the
caller locked with `locked_lead` (or `bdm_leads.locked_for_admin`), so concurrent changes serialise. Functions only; nothing here
commits -- the route owns the transaction. Logs carry ids, stage keys and the event, never the reason text."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED, COUNSELOR_CLOSED, COUNSELOR_MANUAL, EVENTS, LOSS_STAGES, MANUAL, MANUAL_BEFORE, ORDER, REOPEN_TO, STAGE_LABELS, label
from app.models import (
    LEAD_APPOINTMENT_OPEN,
    Appointment,
    AppointmentEvent,
    AuditLog,
    Enquiry,
    LeadFollowUp,
    LeadLostReason,
    LeadStageHistory,
    TelecallerProfile,
    User,
)

logger = logging.getLogger("app.leads")

LEAD_NOT_FOUND = "Lead not found"
ROLE_REQUIRED = "Telecaller role required"
STAGE_UNKNOWN = "Choose a stage of the lead pipeline"
STAGE_SAME = "The lead is already at this stage"
STAGE_SYSTEM = "This stage is set by the system"
STAGE_PAST = "The lead is with the counselor; its stage moves with the application"
CLOSED_REOPEN_ONLY = "A closed lead can only be reopened to Follow-up"
REOPEN_FORBIDDEN = "Only a manager can reopen a closed lead"
REASON_CLOSED = "Add a reason for closing the lead"
REASON_REOPEN = "Add a reason for reopening the lead"
NEXT_ACTION_REQUIRED = "Set a next action and its due date first"  # ccrm-003 A2
# ccrm-006 (DEC-SCOPE-263): the closure details each target takes, and their refusals
CLOSURE_FIELDS = {"duplicate": ("duplicate_of",), **{stage: ("lost_reason_id", "lost_to") for stage in LOSS_STAGES}}
CLOSURE_NOT_HERE = "This detail only applies when closing a lead as Duplicate, Lost or Not Interested"
DUPLICATE_REQUIRED = "Enter the Lead ID of the lead this one duplicates"
DUPLICATE_UNKNOWN = "No lead with this Lead ID in this team"
DUPLICATE_SELF = "A lead cannot be a duplicate of itself"
DUPLICATE_CHAIN = "That lead is itself a duplicate; enter the lead it duplicates"
LOST_REASON_REQUIRED = "Choose why the lead was lost"
LOST_REASON_INACTIVE = "Choose an active lost reason"
FOLLOW_UPS_CLOSED = "Lead closed"  # tel-011 F4: the cancel reason on follow-ups a closing move cancelled
APPOINTMENTS_CLOSED = FOLLOW_UPS_CLOSED  # tel-016 AP15: and on the counselling appointment it cancelled

Kind = Literal["telecaller", "manager", "counselor"]

# ccrm-003 A5: a counselor's follow-up is never the telecaller's work -- every telecaller-side follow-up list, count and alert filters on
# this. Here (models-only imports) so the telecaller metrics and alerts can use it without an import cycle.
TELECALLER_FOLLOW_UP = LeadFollowUp.created_by_user_id.not_in(select(User.id).where(User.role == "counselor"))


def invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def scope(user: User) -> tuple[Kind, list]:
    """The /telecaller lead routes (T23): a telecaller acts on their own leads; a manager on their direct reports' leads and the
    unassigned leads of those reports' teams; super_admin on all. Other roles 403. Out of scope reads as missing (404)."""
    if user.role == "telecaller":
        return "telecaller", [Enquiry.telecaller_user_id == user.id]
    if user.role == "super_admin":
        return "manager", []
    if user.role == "telecaller_manager":
        reports = select(TelecallerProfile.user_id).where(TelecallerProfile.reporting_manager_user_id == user.id)
        teams = select(TelecallerProfile.team).where(TelecallerProfile.reporting_manager_user_id == user.id)
        return "manager", [or_(Enquiry.telecaller_user_id.in_(reports), and_(Enquiry.telecaller_user_id.is_(None), Enquiry.division.in_(teams)))]
    raise HTTPException(403, ROLE_REQUIRED)


async def locked_lead(db: AsyncSession, lead_id: UUID, *filters) -> Enquiry:
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *filters).with_for_update().execution_options(populate_existing=True))
    if lead is None:
        raise HTTPException(404, LEAD_NOT_FOUND)
    return lead


async def _record(db: AsyncSession, lead: Enquiry, to_stage: str, event: str, actor_id: UUID | None, reason: str | None) -> None:
    from_stage = lead.status
    lead.status, lead.stage_changed_at = to_stage, await db.scalar(select(func.now()))
    db.add(LeadStageHistory(lead_id=lead.id, from_stage=from_stage, to_stage=to_stage, event=event, actor_user_id=actor_id, reason=reason))
    logger.info("lead_stage_changed", extra={"extra_fields": {
        "lead_id": str(lead.id), "from_stage": from_stage, "to_stage": to_stage, "event": event, "actor_id": str(actor_id) if actor_id else None}})


async def apply_event(db: AsyncSession, lead: Enquiry, event: str, actor: User | None = None, reason: str | None = None) -> bool:
    """Spec §2: move the lead if it is in the event's from-set; otherwise (already past it, or closed) leave it. Returns whether it
    moved, so a repeated event never fires twice (AC1). An unknown event is a KeyError: a caller bug, not user input. `reason`: a
    person's text kept in the history (tel-018's return)."""
    sources, to_stage = EVENTS[event]
    if lead.status not in sources:
        return False
    await _record(db, lead, to_stage, event, actor.id if actor else None, reason)
    return True


def _closure_fields(to_stage: str, closure: dict | None) -> dict:
    """ccrm-006 D3/D4: the closure details sent; one meant for another target is 422 at that field."""
    sent = {field: value for field, value in (closure or {}).items() if value is not None}
    for field, value in sent.items():
        if field not in CLOSURE_FIELDS.get(to_stage, ()):
            raise invalid(field, CLOSURE_NOT_HERE, str(value))
    return sent


async def _resolve_closure(db: AsyncSession, lead: Enquiry, to_stage: str, sent: dict) -> tuple[dict, str | None]:
    """ccrm-006 D3/D4: the columns to store and the history text used when the person wrote none (D5). A Duplicate names a lead of the
    same team that is not itself a Duplicate; a loss names an active reason, read FOR SHARE so a concurrent deactivation waits (P4)."""
    if to_stage == "duplicate":
        code = sent.get("duplicate_of")
        if code is None:
            raise invalid("duplicate_of", DUPLICATE_REQUIRED, None)
        target = await db.scalar(select(Enquiry).where(Enquiry.lead_code == code, Enquiry.division == lead.division))
        if target is None:
            raise invalid("duplicate_of", DUPLICATE_UNKNOWN, code)
        if target.id == lead.id:
            raise invalid("duplicate_of", DUPLICATE_SELF, code)
        if target.status == "duplicate":
            raise invalid("duplicate_of", DUPLICATE_CHAIN, code)
        return {"duplicate_of_id": target.id}, f"Duplicate of {target.lead_code}"
    if to_stage in LOSS_STAGES:
        reason_id = sent.get("lost_reason_id")
        if reason_id is None:
            raise invalid("lost_reason_id", LOST_REASON_REQUIRED, None)
        row = await db.scalar(select(LeadLostReason).where(LeadLostReason.id == reason_id, LeadLostReason.active.is_(True)).with_for_update(read=True))
        if row is None:
            raise invalid("lost_reason_id", LOST_REASON_INACTIVE, str(reason_id))
        return {"lost_reason_id": row.id, "lost_to": sent.get("lost_to")}, row.name
    return {}, None


async def person_move(db: AsyncSession, lead: Enquiry, actor: User, kind: Kind, to_stage: str, reason: str | None,
                      closure: dict | None = None) -> None:
    """T13 / D1-D3: a telecaller or manager (an admin acts as a manager) chooses Qualified, Interested, Follow-up or a closed outcome;
    only a manager reopens a closed lead, to Follow-up. Nobody chooses a system stage (AC2, T5). ccrm-003 (CC8 / A1, A2): a counselor
    chooses from their own list, and an open target needs the lead's next action and its due date (the route applies any sent first).
    ccrm-006 (D3-D7): a person's stage dialog sends `closure` (even all-empty) -- Duplicate then needs the surviving lead, Lost / Not
    Interested a reason from the list; a call-logged close (tel-010) sends none and keeps its old rules (D6). A reopen clears them."""
    current = lead.status
    if to_stage not in STAGE_LABELS:
        raise invalid("to_stage", STAGE_UNKNOWN, to_stage)
    if to_stage == current:
        raise invalid("to_stage", STAGE_SAME, to_stage)
    sent = _closure_fields(to_stage, closure)
    if current in CLOSED:
        if kind != "manager":
            raise HTTPException(403, REOPEN_FORBIDDEN)
        if to_stage != REOPEN_TO:
            raise invalid("to_stage", CLOSED_REOPEN_ONLY, to_stage)
        if reason is None:
            raise invalid("reason", REASON_REOPEN, reason)
        await _record(db, lead, to_stage, "reopen", actor.id, reason)
        lead.duplicate_of_id = lead.lost_reason_id = lead.lost_to = None  # D7; after the stage, so one flush satisfies the closure CHECKs
        return
    manual, closed = (COUNSELOR_MANUAL, COUNSELOR_CLOSED) if kind == "counselor" else (MANUAL, CLOSED)
    if to_stage not in manual and to_stage not in closed:
        raise invalid("to_stage", STAGE_SYSTEM, to_stage)
    if current == "converted" or (to_stage in manual and ORDER.index(current) >= MANUAL_BEFORE):
        raise invalid("to_stage", STAGE_PAST, to_stage)
    structured = closure is not None or to_stage == "duplicate"  # D6 spares only the loss reason of a call-logged close
    values, default_reason = await _resolve_closure(db, lead, to_stage, sent) if structured else ({}, None)
    reason = reason or default_reason
    if to_stage in CLOSED and reason is None:
        raise invalid("reason", REASON_CLOSED, reason)
    if kind == "counselor" and to_stage not in CLOSED:
        for field in ("next_action", "next_action_due"):
            if getattr(lead, field) is None:
                raise invalid(field, NEXT_ACTION_REQUIRED, None)
    await _record(db, lead, to_stage, "manual", actor.id, reason)
    for field, value in values.items():  # after the stage (as the reopen above)
        setattr(lead, field, value)
    if to_stage in CLOSED:
        await cancel_open_follow_ups(db, lead, FOLLOW_UPS_CLOSED)
        await cancel_open_appointments(db, lead, actor, APPOINTMENTS_CLOSED, "lead_closed")


async def cancel_open_follow_ups(db: AsyncSession, lead: Enquiry, reason: str) -> None:
    """tel-011 F4: a closed lead keeps no open follow-up (tel-018: nor a handed-over one). The caller holds the lead lock, and
    follow-up writes take it first too."""
    cancelled = (await db.scalars(
        update(LeadFollowUp).where(LeadFollowUp.lead_id == lead.id, LeadFollowUp.status == "open")
        .values(status="cancelled", cancelled_at=func.now(), cancel_reason=reason, updated_at=func.now())
        .returning(LeadFollowUp.id).execution_options(synchronize_session=False)
    )).all()
    if cancelled:
        logger.info("lead_follow_ups_cancelled", extra={"extra_fields": {"lead_id": str(lead.id), "count": len(cancelled)}})



async def cancel_open_appointments(db: AsyncSession, lead: Enquiry, actor: User, reason: str, audit_reason: str) -> None:
    """tel-016 AP15 (DEC-SCOPE-095): a closed lead keeps no open counselling appointment, so the counselor's slot frees up (tel-018: nor
    a returned one). Each one gets its history row and audit row, as a cancel does; the caller sets the stage (no release event).
    Lock order lead -> appointment, as every appointment write."""
    stmt = select(Appointment).where(Appointment.lead_id == lead.id, Appointment.status.in_(LEAD_APPOINTMENT_OPEN)).with_for_update()
    for appt in (await db.scalars(stmt.execution_options(populate_existing=True))).all():
        from_status, appt.status = appt.status, "cancelled"
        db.add(AppointmentEvent(appointment_id=appt.id, actor_user_id=actor.id, from_status=from_status, to_status="cancelled", reason=reason))
        db.add(AuditLog(user_id=actor.id, action="lead_appointment.cancel", entity_type="appointment", entity_id=str(appt.id),
                        metadata_json={"lead_id": str(lead.id), "from": from_status, "to": "cancelled", "reason": audit_reason}))
        logger.info("lead_appt_cancelled_on_close", extra={"extra_fields": {"lead_id": str(lead.id), "appointment_id": str(appt.id)}})


def stage_out(lead: Enquiry) -> dict:
    return {"id": lead.id, "status": lead.status, "status_label": label(lead.status), "stage_changed_at": lead.stage_changed_at}


async def history_page(db: AsyncSession, lead_id: UUID, limit: int, offset: int) -> dict:
    """AC5: every change in order, oldest first; the actor is null for the system."""
    where = LeadStageHistory.lead_id == lead_id
    total = await db.scalar(select(func.count()).select_from(LeadStageHistory).where(where))
    stmt = select(LeadStageHistory, User).outerjoin(User, User.id == LeadStageHistory.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(LeadStageHistory.position).limit(limit).offset(offset))).all()
    items = [
        {
            "id": h.id, "from_stage": h.from_stage, "from_label": label(h.from_stage), "to_stage": h.to_stage, "to_label": label(h.to_stage),
            "event": h.event, "actor": {"id": actor.id, "full_name": actor.full_name} if actor else None, "reason": h.reason,
            "created_at": h.created_at,
        }
        for h, actor in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
