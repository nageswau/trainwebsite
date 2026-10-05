"""bdm-006 (DEC-SCOPE-068, spec §5.2): appointment scope, transitions, catalogues, overlap and output.

Functions only; nothing here commits -- the route owns the transaction. Every route resolves an appointment through `load_scoped`, so an
id outside the caller's scope is the same 404 as a missing one. Logs carry ids, statuses and counts, never contact details or free text.
"""

import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BDM_APPOINTMENT_AGENT_OUTCOMES,
    BDM_APPOINTMENT_CODE_SEQ,
    BDM_APPOINTMENT_COMMON_OUTCOMES,
    BDM_APPOINTMENT_COMMON_TYPES,
    BDM_APPOINTMENT_MODULE_TYPES,
    BDM_APPOINTMENT_OPEN,
    AuditLog,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmMeetingReport,
    BdmOrganization,
    BdmOrganizationContact,
    BdmProfile,
    BdmTask,
    User,
)
from app.schemas import BDM_REPORT_TEXT_FIELDS
from app.services.bdm import bdm_context, person_ref

logger = logging.getLogger("app.bdm")

IST = ZoneInfo("Asia/Kolkata")
NOT_FOUND = "Appointment not found"
OWNER_ONLY = "Only the appointment's BDM can change it"
MAX_DURATION = 720
MAX_OVERLAP_MATCHES = 10
TRANSITIONS: dict[str, frozenset[str]] = {  # spec §5.4 (A2) -- the single source for enforcement and `permissions`
    "scheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "confirmed": frozenset({"rescheduled", "cancelled", "no_show", "completed"}),
    "rescheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset(),
}
STATUS_TEXT = {
    "scheduled": "scheduled", "confirmed": "confirmed", "rescheduled": "rescheduled",
    "completed": "completed", "cancelled": "cancelled", "no_show": "marked as a no-show",
}
NOT_STARTED = {
    "complete": "You can only complete an appointment after its start time",
    "no_show": "You can only mark a no-show after the start time",
}
NO_REPORT = "This appointment has no meeting report"
REPORT_LOCKED = "Meeting reports can only be changed on the day they were filed"
FOLLOW_UP_DONE = "This follow-up is already done"


def appointment_types(bdm_type: str) -> tuple[str, ...]:
    """§2 common types plus the module's §C list, order kept, duplicates (agent_meeting, mou_discussion) once."""
    return tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_TYPES + BDM_APPOINTMENT_MODULE_TYPES[bdm_type]))


def appointment_outcomes(bdm_type: str) -> tuple[str, ...]:
    """A8: Agent §C for agent BDMs, §8 for school and college BDMs."""
    return BDM_APPOINTMENT_AGENT_OUTCOMES if bdm_type == "agent" else BDM_APPOINTMENT_COMMON_OUTCOMES


def format_code(n: int) -> str:
    return f"APT-{n:06d}"


async def next_code(db: AsyncSession) -> str:
    """A sequence never repeats a value; gaps after a rollback are accepted. uq_bdm_appointments_code is the backstop."""
    return format_code(await db.scalar(select(BDM_APPOINTMENT_CODE_SEQ.next_value())))


async def db_now(db: AsyncSession) -> datetime:
    """The database clock, read once per request: every time rule compares against the same instant."""
    return await db.scalar(select(func.now()))


def today_ist(now: datetime) -> date:
    return now.astimezone(IST).date()


def ist_bounds(date_from: date | None, date_to: date | None) -> list:
    """Inclusive IST dates -> the UTC half-open range [date_from 00:00 IST, date_to + 1 00:00 IST)."""
    filters = []
    if date_from is not None:
        filters.append(BdmAppointment.starts_at >= datetime.combine(date_from, time(), IST))
    if date_to is not None:
        filters.append(BdmAppointment.starts_at < datetime.combine(date_to + timedelta(days=1), time(), IST))
    return filters


async def caller_filters(db: AsyncSession, user: User) -> list:
    """Read scope (A3): a BDM their own appointments; a manager their team's (sub-select, so a row lock never touches bdm_profiles);
    super_admin all; any other role 403."""
    if user.role == "bdm":
        await bdm_context(db, user)
        return [BdmAppointment.bdm_user_id == user.id]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [BdmAppointment.bdm_user_id.in_(team)]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


async def load_scoped(db: AsyncSession, user: User, appt_id: UUID, *, lock: bool = False) -> BdmAppointment:
    stmt = select(BdmAppointment).where(BdmAppointment.id == appt_id, *await caller_filters(db, user))
    if lock:
        stmt = stmt.with_for_update(of=BdmAppointment).execution_options(populate_existing=True)
    appt = await db.scalar(stmt)
    if appt is None:
        raise HTTPException(404, NOT_FOUND)
    return appt


def require_owner(user: User, appt: BdmAppointment, action: str) -> None:
    if user.role != "bdm" or appt.bdm_user_id != user.id:
        logger.warning("bdm_appt_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt.id), "action": action}})
        raise HTTPException(403, OWNER_ONLY)


def require_transition(appt: BdmAppointment, to_status: str) -> None:
    if to_status not in TRANSITIONS[appt.status]:
        raise HTTPException(409, f"Appointment is already {STATUS_TEXT[appt.status]}")


def require_open(appt: BdmAppointment) -> None:
    if appt.status not in BDM_APPOINTMENT_OPEN:
        raise HTTPException(409, f"Appointment is already {STATUS_TEXT[appt.status]}")


def require_future(starts_at: datetime, now: datetime) -> None:
    if starts_at <= now:
        raise HTTPException(422, "Choose a time in the future")


def require_started(appt: BdmAppointment, now: datetime, action: str) -> None:
    if appt.starts_at > now:
        raise HTTPException(422, NOT_STARTED[action])


def is_pending(appt: BdmAppointment, now: datetime) -> bool:
    """bdm-007 AC5: open and past its start -- waiting for a meeting report (bdm-023 AL-6 reads the same rule via `pending_filter`)."""
    return appt.status in BDM_APPOINTMENT_OPEN and appt.starts_at <= now


def pending_filter(pending: bool):
    expr = and_(BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at <= func.now())
    return expr if pending else not_(expr)


def report_editable(report: BdmMeetingReport, now: datetime) -> bool:
    """bdm-007 spec §5.4 (R2): the IST day it was filed; legacy reports never."""
    return not report.legacy and today_ist(report.submitted_at) == today_ist(now)


async def load_report(db: AsyncSession, appt_id: UUID, *, lock: bool = False) -> BdmMeetingReport | None:
    stmt = select(BdmMeetingReport).where(BdmMeetingReport.appointment_id == appt_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def load_follow_up(db: AsyncSession, appt_id: UUID, *, lock: bool = False) -> BdmTask | None:
    stmt = select(BdmTask).where(BdmTask.source_appointment_id == appt_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def sync_follow_up(db: AsyncSession, appt: BdmAppointment, due_on: date | None) -> str | None:
    """bdm-007 spec §4.3: the appointment's one follow-up tracks `due_on`; returns what changed (for the audit) or None. The caller
    holds the appointment lock (lock order appointment -> report -> follow-up)."""
    task = await load_follow_up(db, appt.id, lock=True)
    if task is None:
        if due_on is None:
            return None
        db.add(BdmTask(
            kind="follow_up", title=f"Follow up on {appt.code}", due_on=due_on, organization_id=appt.organization_id,
            source="appointment_outcome", source_appointment_id=appt.id, assignee_user_id=appt.bdm_user_id, status="open",
        ))
        return "created"
    if task.status == "done":
        raise HTTPException(409, FOLLOW_UP_DONE)
    if due_on is None:
        if task.status == "cancelled":
            return None
        task.status = "cancelled"
        return "cancelled"
    if task.status == "cancelled":
        task.status, task.due_on = "open", due_on
        return "reopened"
    if task.due_on == due_on:
        return None
    task.due_on = due_on
    return "moved"


def snapshot(contact: BdmOrganizationContact) -> dict:
    return {
        "contact_id": contact.id, "contact_name": contact.name, "contact_designation": contact.designation,
        "contact_phone": contact.phone, "contact_email": contact.email,
    }


async def find_overlaps(db: AsyncSession, bdm_user_id: UUID, starts_at: datetime, duration: int, exclude_id: UUID | None = None) -> tuple[list[dict], int]:
    """A6: the owner's open appointments whose [start, start + duration) intersects. The lower bound keeps the query on
    ix_bdm_appointments_bdm_starts (no appointment can start earlier than new_start - MAX_DURATION and still overlap)."""
    end = starts_at + timedelta(minutes=duration)
    their_end = BdmAppointment.starts_at + func.make_interval(0, 0, 0, 0, 0, BdmAppointment.duration_minutes)
    conditions = [
        BdmAppointment.bdm_user_id == bdm_user_id,
        BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN),
        BdmAppointment.starts_at > starts_at - timedelta(minutes=MAX_DURATION),
        BdmAppointment.starts_at < end,
        their_end > starts_at,
    ]
    if exclude_id is not None:
        conditions.append(BdmAppointment.id != exclude_id)
    total = await db.scalar(select(func.count()).select_from(BdmAppointment).where(*conditions))
    if not total:
        return [], 0
    rows = (
        await db.execute(
            select(BdmAppointment, BdmOrganization.name)
            .join(BdmOrganization, BdmOrganization.id == BdmAppointment.organization_id)
            .where(*conditions)
            .order_by(BdmAppointment.starts_at, BdmAppointment.id)
            .limit(MAX_OVERLAP_MATCHES)
        )
    ).all()
    matches = [
        {"id": str(a.id), "code": a.code, "starts_at": a.starts_at.isoformat(), "duration_minutes": a.duration_minutes, "organization_name": name}
        for a, name in rows
    ]
    return matches, total


def overlap_conflict(matches: list[dict], total: int) -> HTTPException:
    return HTTPException(409, {"message": "You already have an appointment at this time", "code": "possible_overlap", "matches": matches, "total": total})


def record(db: AsyncSession, appt: BdmAppointment, actor: User, from_status: str | None, to_status: str, *, old_starts_at=None, new_starts_at=None, reason=None) -> None:
    db.add(BdmAppointmentEvent(appointment_id=appt.id, actor_user_id=actor.id, from_status=from_status, to_status=to_status, old_starts_at=old_starts_at, new_starts_at=new_starts_at, reason=reason))


def permissions(user: User, appt: BdmAppointment, now: datetime, report: BdmMeetingReport | None = None) -> dict[str, bool]:
    owner = user.role == "bdm" and appt.bdm_user_id == user.id
    open_ = owner and appt.status in BDM_APPOINTMENT_OPEN
    started = appt.starts_at <= now
    return {
        "can_edit": open_,
        "can_confirm": owner and "confirmed" in TRANSITIONS[appt.status],
        "can_reschedule": open_,
        "can_cancel": open_,
        "can_no_show": open_ and started,
        "can_complete": open_ and started,
        "can_edit_report": owner and report is not None and report_editable(report, now),
    }


def row_out(appt: BdmAppointment, org: BdmOrganization, owner: User, now: datetime) -> dict:
    return {
        "id": appt.id, "code": appt.code, "starts_at": appt.starts_at, "duration_minutes": appt.duration_minutes,
        "appointment_type": appt.appointment_type, "status": appt.status,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "archived": org.archived_at is not None},
        "contact_name": appt.contact_name, "bdm": person_ref(owner), "outcome_pending": is_pending(appt, now),
    }


async def appointment_out(db: AsyncSession, user: User, appt: BdmAppointment, *, refresh: bool = True) -> dict:
    """The detail every route returns (R-A1). Refreshes first: server defaults (timestamps) are expired after a flush."""
    if refresh:
        await db.refresh(appt)
    org = await db.get(BdmOrganization, appt.organization_id)
    owner = await db.get(User, appt.bdm_user_id)
    events = (
        await db.execute(
            select(BdmAppointmentEvent, User.full_name)
            .join(User, User.id == BdmAppointmentEvent.actor_user_id)
            .where(BdmAppointmentEvent.appointment_id == appt.id)
            .order_by(BdmAppointmentEvent.position)
        )
    ).all()
    now = await db_now(db)
    report_row = (
        await db.execute(
            select(BdmMeetingReport, User).join(User, User.id == BdmMeetingReport.author_user_id)
            .where(BdmMeetingReport.appointment_id == appt.id).execution_options(populate_existing=True)
        )
    ).first()
    report, author = report_row if report_row else (None, None)
    follow_up = await load_follow_up(db, appt.id)
    return {
        **row_out(appt, org, owner, now),
        **{k: getattr(appt, k) for k in ("contact_id", "contact_designation", "contact_phone", "contact_email", "location", "purpose", "remarks", "outcome", "next_follow_up_on", "expected_leads", "expected_revenue", "created_at", "updated_at")},
        "events": [
            {"from_status": e.from_status, "to_status": e.to_status, "old_starts_at": e.old_starts_at, "new_starts_at": e.new_starts_at, "reason": e.reason, "actor_name": name, "created_at": e.created_at}
            for e, name in events
        ],
        "report": None if report is None else {
            **{k: getattr(report, k) for k in BDM_REPORT_TEXT_FIELDS}, "legacy": report.legacy, "author": person_ref(author),
            "submitted_at": report.submitted_at, "updated_at": report.updated_at,
        },
        "follow_up": None if follow_up is None else {"id": follow_up.id, "due_on": follow_up.due_on, "status": follow_up.status},
        "permissions": permissions(user, appt, now, report),
    }


def audit(db: AsyncSession, user: User, action: str, appt_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names, statuses and times only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_appointment.{action}", entity_type="bdm_appointment", entity_id=str(appt_id), metadata_json=metadata or {}))


def log(event: str, user: User, appt_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt_id), **extra}})
