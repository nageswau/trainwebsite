"""tel-016 (DEC-SCOPE-095, spec §3; API §12Q): lead counselling appointments.

- /telecaller/leads/{id}/...: the booking options, the lead's appointments (telecaller, manager, super_admin -- tel-004's scope) and the
  booking itself (the lead's telecaller only, AP2).
- /counselor/appointments: a counselor's own lead appointments (AP13).
- /lead-appointments/{id}/...: the lifecycle actions -- the counselor all of them, the lead's telecaller cancel and reschedule (AP2).

Scope always comes from the session; an id outside it is 404, a role that may not act 403. The existing overseas student appointment
routes (workflows.py) are unchanged for students (AC5)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.lead_stages import CLOSED
from app.models import LEAD_APPOINTMENT_STATUSES, Appointment, Enquiry, User
from app.schemas import LeadAppointmentCancel, LeadAppointmentCreate, LeadAppointmentReschedule
from app.services import lead_appointments as svc
from app.services import lead_pipeline, telecaller_alerts, telecaller_leads

telecaller_router = APIRouter(prefix="/telecaller/leads", tags=["lead-appointments"])
counselor_router = APIRouter(prefix="/counselor/appointments", tags=["lead-appointments"])
router = APIRouter(prefix="/lead-appointments", tags=["lead-appointments"])

LEAD_CLOSED = "This lead is closed; reopen it before booking"
ONE_OPEN = "This lead already has an open counselling appointment"
BOOKER_ONLY = "Only the lead's telecaller can book an appointment"


async def _scoped_lead(db: AsyncSession, user: User, lead_id: UUID) -> Enquiry:
    _, filters = lead_pipeline.scope(user)
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *filters))
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return lead


@telecaller_router.get("/{lead_id}/appointment-options")
async def booking_options(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AP4: the lead's division decides the types and the counselors (active counselors of that division, by name)."""
    return await svc.options(db, await _scoped_lead(db, user, lead_id))


@telecaller_router.get("/{lead_id}/appointments")
async def lead_appointments(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The lead's appointments, newest booking first, each with its history and what the caller may do (a manager: nothing)."""
    lead = await _scoped_lead(db, user, lead_id)
    return await svc.lead_list(db, user, lead.id)


@telecaller_router.post("/{lead_id}/appointments", status_code=201)
async def book(lead_id: UUID, payload: LeadAppointmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1-AC4, spec §3, in this order so each refusal is exactly one rule: scope 404, handed over 403, closed 409, type / time /
    counselor 422, a second open booking 409, the counselor's clash 409. Then the stage moves (`appointment_booked`, AC2)."""
    kind, filters = lead_pipeline.scope(user)
    if kind != "telecaller":
        raise HTTPException(403, BOOKER_ONLY)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    telecaller_leads.require_writable(user, lead)
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    if payload.appointment_type not in svc.types_for(lead.division):
        raise svc.invalid("appointment_type", "This appointment type is not offered for the lead's division", payload.appointment_type)
    svc.require_schedulable(payload.scheduled_at, await svc.db_now(db))
    counselor = await svc.lock_counselor(db, payload.counselor_id, lead.division)
    if await svc.has_open(db, lead.id):
        raise HTTPException(409, ONE_OPEN)
    await svc.require_free(db, counselor.id, payload.scheduled_at)
    appt = Appointment(
        division=lead.division, lead_id=lead.id, staff_id=counselor.id, scheduled_at=payload.scheduled_at, appointment_type=payload.appointment_type,
        mode=payload.mode, status="scheduled", appointment_code=await svc.next_code(db), duration_minutes=svc.DURATION,
        meeting_link=payload.meeting_link, location=payload.location, purpose=payload.purpose, remarks=payload.remarks, booked_by_user_id=user.id,
    )
    db.add(appt)
    await db.flush()
    svc.record(db, appt, user, None, "scheduled", new=appt.scheduled_at)
    svc.audit(db, user, "create", appt, {"counselor_id": str(counselor.id), "scheduled_at": appt.scheduled_at.isoformat()})
    await lead_pipeline.apply_event(db, lead, "appointment_booked", user)
    await db.commit()
    return (await svc.outs(db, user, [appt]))[0]


@counselor_router.get("")
async def my_appointments(
    status: Literal[LEAD_APPOINTMENT_STATUSES] | None = None, limit: int = LIMIT, offset: int = OFFSET,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if user.role != "counselor":
        raise HTTPException(403, "Counselor role required")
    return await svc.counselor_page(db, user, status, limit, offset)


async def _act(db: AsyncSession, user: User, appt_id: UUID, action: str, *, reason: str | None = None, new_time=None) -> dict:
    """AP2 / AP9 / AP10: one transition, its event row and audit row, and its stage effect (AC2, AP3)."""
    appt, lead = await svc.load_for_action(db, user, appt_id)
    if user.role == "telecaller":
        telecaller_leads.require_writable(user, lead)
    now = await svc.db_now(db)
    svc.require_action(user, appt, action, now)
    from_status, old = appt.status, appt.scheduled_at
    if action == "reschedule":
        svc.require_schedulable(new_time, now)
        await svc.lock_counselor(db, appt.staff_id, lead.division)
        await svc.require_free(db, appt.staff_id, new_time, exclude_id=appt.id)
        appt.scheduled_at = new_time
    appt.status = svc.ACTION_STATUS[action]
    moved = action == "reschedule"
    svc.record(db, appt, user, from_status, appt.status, old=old if moved else None, new=new_time if moved else None, reason=reason)
    meta = {"from": from_status, "to": appt.status, **({"old": old.isoformat(), "new": new_time.isoformat()} if moved else {})}
    svc.audit(db, user, action, appt, meta)
    if action in svc.STAGE_EVENT:
        await lead_pipeline.apply_event(db, lead, svc.STAGE_EVENT[action], user)
    if action == "complete":
        await telecaller_alerts.notify_appointment_completed(db, appt, lead, user)  # tel-020
    await db.commit()
    return (await svc.outs(db, user, [appt]))[0]


@router.post("/{appt_id}/confirm")
async def confirm(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, appt_id, "confirm")


@router.post("/{appt_id}/complete")
async def complete(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, appt_id, "complete")


@router.post("/{appt_id}/no-show")
async def no_show(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, appt_id, "no_show")


@router.post("/{appt_id}/cancel")
async def cancel(appt_id: UUID, payload: LeadAppointmentCancel = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, appt_id, "cancel", reason=payload.reason)


@router.post("/{appt_id}/reschedule")
async def reschedule(appt_id: UUID, payload: LeadAppointmentReschedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _act(db, user, appt_id, "reschedule", reason=payload.reason, new_time=payload.scheduled_at)
