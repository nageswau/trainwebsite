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

from app.lead_stages import CLOSED, EVENTS, MANUAL, MANUAL_BEFORE, ORDER, REOPEN_TO, STAGE_LABELS, label
from app.models import LEAD_APPOINTMENT_OPEN, Appointment, AppointmentEvent, AuditLog, Enquiry, LeadFollowUp, LeadStageHistory, TelecallerProfile, User

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
FOLLOW_UPS_CLOSED = "Lead closed"  # tel-011 F4: the cancel reason on follow-ups a closing move cancelled
APPOINTMENTS_CLOSED = FOLLOW_UPS_CLOSED  # tel-016 AP15: and on the counselling appointment it cancelled

Kind = Literal["telecaller", "manager"]


def _invalid(field: str, msg: str, value) -> RequestValidationError:
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


async def person_move(db: AsyncSession, lead: Enquiry, actor: User, kind: Kind, to_stage: str, reason: str | None) -> None:
    """T13 / D1-D3: a telecaller or manager (an admin acts as a manager) chooses Qualified, Interested, Follow-up or a closed outcome;
    only a manager reopens a closed lead, to Follow-up. Nobody chooses a system stage (AC2, T5)."""
    current = lead.status
    if to_stage not in STAGE_LABELS:
        raise _invalid("to_stage", STAGE_UNKNOWN, to_stage)
    if to_stage == current:
        raise _invalid("to_stage", STAGE_SAME, to_stage)
    if current in CLOSED:
        if kind == "telecaller":
            raise HTTPException(403, REOPEN_FORBIDDEN)
        if to_stage != REOPEN_TO:
            raise _invalid("to_stage", CLOSED_REOPEN_ONLY, to_stage)
        if reason is None:
            raise _invalid("reason", REASON_REOPEN, reason)
        await _record(db, lead, to_stage, "reopen", actor.id, reason)
        return
    if to_stage not in MANUAL and to_stage not in CLOSED:
        raise _invalid("to_stage", STAGE_SYSTEM, to_stage)
    if current == "converted" or (to_stage in MANUAL and ORDER.index(current) >= MANUAL_BEFORE):
        raise _invalid("to_stage", STAGE_PAST, to_stage)
    if to_stage in CLOSED and reason is None:
        raise _invalid("reason", REASON_CLOSED, reason)
    await _record(db, lead, to_stage, "manual", actor.id, reason)
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
