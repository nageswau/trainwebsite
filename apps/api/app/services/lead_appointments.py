"""tel-016 (DEC-SCOPE-095, spec §3): a lead's counselling appointments -- types and counselors by division (AP4), the counselor clash
(AP1), the one-open-per-lead rule (AP5), the EVID-019 §9 lifecycle (AP2) and its stage effects (AC2, AP3), and the output.

Functions only; nothing here commits -- the route owns the transaction. Lock order is lead -> counselor user -> appointment, so two
bookings of one counselor (or of one lead) serialise and the clash check can't race. Logs and audit rows carry ids, statuses and times,
never the lead's name, contact details or free text."""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import label as stage_label
from app.models import (
    APPOINTMENT_CODE_SEQ,
    APPOINTMENT_MODES,
    LEAD_APPOINTMENT_OPEN,
    LEAD_APPOINTMENT_TYPE_LABELS,
    LEAD_APPOINTMENT_TYPES,
    Appointment,
    AppointmentEvent,
    AuditLog,
    Enquiry,
    User,
)
from app.services import lead_pipeline

logger = logging.getLogger("app.leads")

NOT_FOUND = "Appointment not found"
DURATION = 60  # AP1: every booking lasts an hour
HORIZON = timedelta(days=366)  # AP8
MAX_MATCHES = 10
TRANSITIONS: dict[str, frozenset[str]] = {  # EVID-019 §9 -- the single source for enforcement and `permissions`
    "scheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "confirmed": frozenset({"rescheduled", "cancelled", "no_show", "completed"}),
    "rescheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset(),
}
STATUS_TEXT = {
    "scheduled": "scheduled", "confirmed": "confirmed", "rescheduled": "rescheduled", "completed": "completed",
    "cancelled": "cancelled", "no_show": "marked as a no-show",
}
ACTION_STATUS = {"confirm": "confirmed", "complete": "completed", "no_show": "no_show", "cancel": "cancelled", "reschedule": "rescheduled"}
COUNSELOR_ACTIONS = frozenset(ACTION_STATUS)  # AP2
TELECALLER_ACTIONS = frozenset({"cancel", "reschedule"})
STAGE_EVENT = {"complete": "appointment_completed", "no_show": "appointment_released", "cancel": "appointment_released"}  # AC2, AP3
NOT_STARTED = {"complete": "You can only complete an appointment after its start time",
               "no_show": "You can only mark a no-show after the start time"}


def invalid(field: str, msg: str, value=None) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def types_for(division: str) -> tuple[str, ...]:
    return LEAD_APPOINTMENT_TYPES.get(division, ())


async def db_now(db: AsyncSession) -> datetime:
    """The database clock, read once per request: every time rule compares against the same instant."""
    return await db.scalar(select(func.now()))


def _counselors(division: str):
    return select(User).where(User.role == "counselor", User.division == division, User.active.is_(True))


async def options(db: AsyncSession, lead: Enquiry) -> dict:
    counselors = (await db.scalars(_counselors(lead.division).order_by(User.full_name, User.id))).all()
    return {
        "types": [{"key": key, "label": LEAD_APPOINTMENT_TYPE_LABELS[key]} for key in types_for(lead.division)],
        "counselors": [{"id": c.id, "full_name": c.full_name} for c in counselors],
        "modes": list(APPOINTMENT_MODES),
        "duration_minutes": DURATION,
    }


async def lock_counselor(db: AsyncSession, counselor_id: UUID, division: str) -> User:
    """AP4 / AC4: an active counselor of the lead's division. The row lock serialises the clash check for this counselor."""
    counselor = await db.scalar(_counselors(division).where(User.id == counselor_id).with_for_update().execution_options(populate_existing=True))
    if counselor is None:
        raise invalid("counselor_id", "Choose an active counselor of the lead's division", str(counselor_id))
    return counselor


def require_schedulable(start: datetime, now: datetime) -> None:
    if start <= now:
        raise invalid("scheduled_at", "Choose a time in the future", start.isoformat())
    if start > now + HORIZON:
        raise invalid("scheduled_at", "Choose a time within the next year", start.isoformat())


async def require_free(db: AsyncSession, staff_id: UUID, start: datetime, exclude_id: UUID | None = None) -> None:
    """AP1: refuse a time that overlaps any open appointment of the counselor -- a lead's or a student's -- as half-open intervals, so
    back-to-back is fine. The lower bound keeps the query on ix_appointments_staff_scheduled. Matches carry times only."""
    end = start + timedelta(minutes=DURATION)
    their_end = Appointment.scheduled_at + func.make_interval(0, 0, 0, 0, 0, Appointment.duration_minutes)
    conditions = [
        Appointment.staff_id == staff_id,
        Appointment.status.in_(LEAD_APPOINTMENT_OPEN),
        Appointment.scheduled_at > start - timedelta(minutes=DURATION),  # every row lasts DURATION (the column's default; AP1)
        Appointment.scheduled_at < end,
        their_end > start,
    ]
    if exclude_id is not None:
        conditions.append(Appointment.id != exclude_id)
    rows = (await db.execute(select(Appointment.scheduled_at, Appointment.duration_minutes).where(*conditions)
                             .order_by(Appointment.scheduled_at).limit(MAX_MATCHES))).all()
    if rows:
        logger.info("lead_appt_clash", extra={"extra_fields": {"counselor_id": str(staff_id), "match_count": len(rows)}})
        raise HTTPException(409, {"message": "The counselor already has an appointment at this time", "code": "counselor_busy",
                                  "matches": [{"scheduled_at": at.isoformat(), "duration_minutes": minutes} for at, minutes in rows]})


async def has_open(db: AsyncSession, lead_id: UUID) -> bool:
    stmt = select(Appointment.id).where(Appointment.lead_id == lead_id, Appointment.status.in_(LEAD_APPOINTMENT_OPEN))
    return await db.scalar(stmt) is not None


async def next_code(db: AsyncSession) -> str:
    """AP6: a sequence never repeats a value; gaps after a rollback are accepted. The unique constraint is the backstop."""
    return f"CAP-{await db.scalar(select(APPOINTMENT_CODE_SEQ.next_value())):06d}"


def record(db: AsyncSession, appt: Appointment, actor: User, from_status: str | None, to_status: str, *, old=None, new=None, reason=None) -> None:
    db.add(AppointmentEvent(appointment_id=appt.id, actor_user_id=actor.id, from_status=from_status, to_status=to_status,
                            old_scheduled_at=old, new_scheduled_at=new, reason=reason))


def audit(db: AsyncSession, user: User, action: str, appt: Appointment, metadata: dict) -> None:
    """Same transaction as the write (fail closed); ids, statuses and times only."""
    db.add(AuditLog(user_id=user.id, action=f"lead_appointment.{action}", entity_type="appointment", entity_id=str(appt.id),
                    metadata_json={"lead_id": str(appt.lead_id), **metadata}))
    logger.info("lead_appt_changed", extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt.id), "action": action,
                                                              "status": appt.status}})


async def load_for_action(db: AsyncSession, user: User, appt_id: UUID) -> tuple[Appointment, Enquiry]:
    """Scope (spec §3): the counselor of the appointment, or the telecaller of its lead; anyone else (another counselor, a manager, any
    other role) reads it as missing -- 404, the IDOR rule. Locks lead -> appointment and re-checks the scope under the lock."""
    if user.role == "counselor":
        scoped = [Appointment.staff_id == user.id]
    elif user.role == "telecaller":
        scoped = [Enquiry.telecaller_user_id == user.id]
    else:
        raise HTTPException(404, NOT_FOUND)
    stmt = select(Appointment.lead_id).join(Enquiry, Enquiry.id == Appointment.lead_id).where(Appointment.id == appt_id, *scoped)
    lead_id = await db.scalar(stmt)
    if lead_id is None:
        raise HTTPException(404, NOT_FOUND)
    lead = await lead_pipeline.locked_lead(db, lead_id)
    appt = await db.scalar(select(Appointment).where(Appointment.id == appt_id).with_for_update().execution_options(populate_existing=True))
    if user.role == "counselor" and appt.staff_id != user.id or user.role == "telecaller" and lead.telecaller_user_id != user.id:
        raise HTTPException(404, NOT_FOUND)  # reassigned while the request waited for the lock
    return appt, lead


def require_action(user: User, appt: Appointment, action: str, now: datetime) -> None:
    allowed = COUNSELOR_ACTIONS if user.role == "counselor" else TELECALLER_ACTIONS
    if action not in allowed:
        logger.warning("lead_appt_refused", extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt.id), "action": action}})
        raise HTTPException(403, "Only the counselor can do this")
    if ACTION_STATUS[action] not in TRANSITIONS.get(appt.status, frozenset()):
        raise HTTPException(409, f"Appointment is already {STATUS_TEXT.get(appt.status, appt.status)}")
    if action in NOT_STARTED and appt.scheduled_at > now:
        raise HTTPException(422, NOT_STARTED[action])


def permissions(user: User, appt: Appointment, lead: Enquiry, now: datetime) -> dict[str, bool]:
    counselor = user.role == "counselor" and appt.staff_id == user.id
    telecaller = user.role == "telecaller" and lead.telecaller_user_id == user.id and lead.owner_id is None
    open_ = appt.status in LEAD_APPOINTMENT_OPEN
    started = appt.scheduled_at <= now
    return {
        "can_confirm": counselor and "confirmed" in TRANSITIONS.get(appt.status, frozenset()),
        "can_complete": counselor and open_ and started,
        "can_no_show": counselor and open_ and started,
        "can_cancel": (counselor or telecaller) and open_,
        "can_reschedule": (counselor or telecaller) and open_,
    }


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


async def outs(db: AsyncSession, user: User, appts: list[Appointment]) -> list[dict]:
    """The shape every route returns (spec §3), batched: one query each for the leads, the people and the events."""
    if not appts:
        return []
    ids = [a.id for a in appts]
    fresh = {a.id: a for a in (await db.scalars(select(Appointment).where(Appointment.id.in_(ids)).execution_options(populate_existing=True))).all()}
    leads = {e.id: e for e in (await db.scalars(select(Enquiry).where(Enquiry.id.in_({a.lead_id for a in fresh.values()}))
                                                .execution_options(populate_existing=True))).all()}
    people_ids = {a.staff_id for a in fresh.values()} | {a.booked_by_user_id for a in fresh.values()}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(people_ids - {None})))).all()}
    events: dict[UUID, list[dict]] = {i: [] for i in ids}
    rows = await db.execute(select(AppointmentEvent, User.full_name).join(User, User.id == AppointmentEvent.actor_user_id)
                            .where(AppointmentEvent.appointment_id.in_(ids)).order_by(AppointmentEvent.position))
    for event, name in rows.all():
        events[event.appointment_id].append({
            "from_status": event.from_status, "to_status": event.to_status, "old_scheduled_at": event.old_scheduled_at,
            "new_scheduled_at": event.new_scheduled_at, "reason": event.reason, "actor_name": name, "created_at": event.created_at,
        })
    now = await db_now(db)
    result = []
    for appt_id in ids:
        a = fresh[appt_id]
        lead = leads[a.lead_id]
        result.append({
            "id": a.id, "code": a.appointment_code,
            "lead": {"id": lead.id, "lead_code": lead.lead_code, "name": lead.name, "phone": lead.phone, "email": lead.email,
                     "status": lead.status, "status_label": stage_label(lead.status)},
            "appointment_type": a.appointment_type, "type_label": LEAD_APPOINTMENT_TYPE_LABELS.get(a.appointment_type, a.appointment_type),
            "counselor": _person(people.get(a.staff_id)), "booked_by": _person(people.get(a.booked_by_user_id)),
            "scheduled_at": a.scheduled_at, "duration_minutes": a.duration_minutes, "mode": a.mode, "meeting_link": a.meeting_link,
            "location": a.location, "purpose": a.purpose, "remarks": a.remarks, "status": a.status, "created_at": a.created_at,
            "events": events[a.id], "permissions": permissions(user, a, lead, now),
        })
    return result


async def lead_list(db: AsyncSession, user: User, lead_id: UUID) -> dict:
    appts = (await db.scalars(select(Appointment).where(Appointment.lead_id == lead_id).order_by(Appointment.created_at.desc(), Appointment.id))).all()
    return {"items": await outs(db, user, list(appts))}


async def counselor_page(db: AsyncSession, user: User, status: str | None, limit: int, offset: int) -> dict:
    """AP13: the counselor's own lead appointments -- open first, soonest first; then the rest, latest first."""
    filters = [Appointment.staff_id == user.id, Appointment.lead_id.is_not(None)]
    if status is not None:
        filters.append(Appointment.status == status)
    is_open = Appointment.status.in_(LEAD_APPOINTMENT_OPEN)
    epoch = func.extract("epoch", Appointment.scheduled_at)
    order = (case((is_open, 0), else_=1), case((is_open, epoch), else_=-epoch), Appointment.id)
    total = await db.scalar(select(func.count()).select_from(Appointment).where(*filters))
    appts = (await db.scalars(select(Appointment).where(*filters).order_by(*order).limit(limit).offset(offset))).all()
    return {"items": await outs(db, user, list(appts)), "total": total or 0, "limit": limit, "offset": offset}
