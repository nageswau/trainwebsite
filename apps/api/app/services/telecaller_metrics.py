"""tel-021 (DEC-SCOPE-103, spec §2): the single source of every Telecaller CRM count -- the daily activity D1-D13, the dashboard tiles
B1-B10 and target progress (EVID-019 §1, §14, §15; backlog Appendix B). tel-023 and tel-024 reuse it.

Days are IST calendar days as half-open instant ranges (`bdm_activities.day_range`). Flow counts (calls, completions, ...) take any
range, so a month or a report period is one query. Point-in-time counts (D1, D6, D12) are reconstructed as of an instant from history
(DB4): the last change at or before it gives the "to" value; else the first change after it gives the "from" value; else the current
value. Reads only; nothing here writes."""

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Uuid, case, cast, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import (
    TEL_TARGET_KPIS,
    Appointment,
    AuditLog,
    BdmAppointment,
    BdmMeetingRequest,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    LeadMessage,
    LeadStageHistory,
)
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import today_ist
from app.services.lead_calls import NOT_CONNECTED
from app.services.telecaller_leads import PRIORITY_CHANGE
from app.services.telecaller_targets import effective_targets

ACTIVITY_KEYS = (
    "leads_assigned", "calls", "connected_calls", "not_connected", "follow_ups_completed", "follow_ups_pending", "new_appointments",
    "counselor_appointments", "bdm_appointments", "whatsapp_messages", "qualified_leads", "hot_leads", "converted_leads",
)
# Appendix B K1-K6: each target KPI is one daily-activity count.
KPI_COUNTS = dict(zip(TEL_TARGET_KPIS, ("calls", "connected_calls", "qualified_leads", "follow_ups_completed", "counselor_appointments", "converted_leads"), strict=True))
NOT_CONTACTED_AFTER = timedelta(hours=24)  # DB1: until tel-020 brings the team's threshold
FIRST_CALL = ("assigned", "first_call_pending")
CANCELLED = "cancelled"  # DB7: every other status is on the day's list


# --- point in time ------------------------------------------------------------------------------------------------------------------

def _as_of(changes, order, to_value, from_value, current, at):
    """A lead's value at instant `at` from its change rows (DB4). `changes` is a select of the change table already narrowed to the lead."""
    before = changes.where(order[0] <= at)
    after = changes.where(order[0] > at)
    return case(
        (exists(before), before.with_only_columns(to_value).order_by(*(c.desc() for c in order)).limit(1).scalar_subquery()),
        (exists(after), after.with_only_columns(from_value).order_by(*order).limit(1).scalar_subquery()),
        else_=current,
    )


def _audit(action: str):
    return select(AuditLog.id).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == cast(Enquiry.id, AuditLog.entity_id.type), AuditLog.action == action)


def owner_at(at):
    """The lead's telecaller at `at`, from its `lead.assign` audit rows (tel-007 writes one per change)."""
    return _as_of(_audit("lead.assign"), (AuditLog.created_at,), cast(AuditLog.metadata_json["to"].as_string(), Uuid),
                  cast(AuditLog.metadata_json["from"].as_string(), Uuid), Enquiry.telecaller_user_id, at)


def _stage_at(at):
    changes = select(LeadStageHistory.id).where(LeadStageHistory.lead_id == Enquiry.id)
    return _as_of(changes, (LeadStageHistory.created_at, LeadStageHistory.position), LeadStageHistory.to_stage, LeadStageHistory.from_stage, Enquiry.status, at)


def _priority_at(at):
    return _as_of(_audit(PRIORITY_CHANGE), (AuditLog.created_at,), AuditLog.metadata_json["to"].as_string(),
                  AuditLog.metadata_json["from"].as_string(), Enquiry.priority, at)


def _ever_mine(user_id: UUID):
    """Every lead that is or was the telecaller's -- the candidates a point-in-time count looks at."""
    moves = select(cast(AuditLog.entity_id, Uuid)).where(
        AuditLog.action == "lead.assign", AuditLog.entity_type == "enquiry",
        or_(AuditLog.metadata_json["to"].as_string() == str(user_id), AuditLog.metadata_json["from"].as_string() == str(user_id)),
    )
    return or_(Enquiry.telecaller_user_id == user_id, Enquiry.id.in_(moves))


def _mine_at(user_id: UUID, at) -> list:
    return [_ever_mine(user_id), Enquiry.created_at <= at, owner_at(at) == user_id]


async def _snapshot(db: AsyncSession, user_id: UUID, at: datetime, day_end: datetime) -> dict:
    """D1, D12 and D6 as of `at` (the end of the day, or now for today)."""
    stage, priority = _stage_at(at), _priority_at(at)
    open_lead = stage.not_in(CLOSED)
    leads = (await db.execute(
        select(func.count(), func.count().filter(priority == "hot")).select_from(Enquiry).where(*_mine_at(user_id, at), open_lead)
    )).one()
    pending = await db.scalar(
        select(func.count()).select_from(LeadFollowUp).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(
            *_mine_at(user_id, at), LeadFollowUp.due_at < day_end, LeadFollowUp.created_at <= at,
            or_(LeadFollowUp.completed_at.is_(None), LeadFollowUp.completed_at > at),
            or_(LeadFollowUp.cancelled_at.is_(None), LeadFollowUp.cancelled_at > at),
        )
    )
    return {"leads_assigned": leads[0], "hot_leads": leads[1], "follow_ups_pending": pending}


# --- flow counts over a range ------------------------------------------------------------------------------------------------------

def _in(column, start, end) -> list:
    return [column >= start, column < end]


async def conversions(db: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> int:
    """D13 (DB2): leads still converted whose conversion was first recorded in the range while the lead was the telecaller's."""
    first = (
        select(LeadStageHistory.lead_id, func.min(LeadStageHistory.created_at).label("at"))
        .where(LeadStageHistory.to_stage == "converted").group_by(LeadStageHistory.lead_id).subquery()
    )
    return await db.scalar(select(func.count()).select_from(Enquiry).join(first, first.c.lead_id == Enquiry.id).where(
        Enquiry.status == "converted", *_in(first.c.at, start, end), _ever_mine(user_id), owner_at(first.c.at) == user_id))


async def flow_counts(db: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> dict:
    """Every count that is a number of events in [start, end)."""
    calls = (await db.execute(
        select(func.count(), func.count().filter(LeadCall.outcome.in_(NOT_CONNECTED)))
        .where(LeadCall.caller_user_id == user_id, *_in(LeadCall.occurred_at, start, end))
    )).one()
    counselor = await db.scalar(select(func.count()).select_from(Appointment).where(
        Appointment.booked_by_user_id == user_id, Appointment.lead_id.is_not(None), *_in(Appointment.created_at, start, end)))
    bdm = await db.scalar(select(func.count()).select_from(BdmMeetingRequest).where(
        BdmMeetingRequest.requester_user_id == user_id, *_in(BdmMeetingRequest.created_at, start, end)))
    return {
        "calls": calls[0], "connected_calls": calls[0] - calls[1], "not_connected": calls[1],
        "follow_ups_completed": await db.scalar(select(func.count()).select_from(LeadFollowUp).where(
            LeadFollowUp.completed_by_user_id == user_id, *_in(LeadFollowUp.completed_at, start, end))),
        "counselor_appointments": counselor, "bdm_appointments": bdm, "new_appointments": counselor + bdm,
        "whatsapp_messages": await db.scalar(select(func.count()).select_from(LeadMessage).where(
            LeadMessage.sender_user_id == user_id, LeadMessage.channel == "whatsapp", *_in(LeadMessage.sent_at, start, end))),
        "qualified_leads": await db.scalar(select(func.count()).select_from(LeadStageHistory).where(
            LeadStageHistory.actor_user_id == user_id, LeadStageHistory.to_stage == "qualified", *_in(LeadStageHistory.created_at, start, end))),
        "converted_leads": await conversions(db, user_id, start, end),
    }


async def daily_activity(db: AsyncSession, user_id: UUID, day: date, now: datetime) -> dict:
    """§14 / T27: the 13 counts for one IST day (today: the snapshot is as of now)."""
    start, end = day_range(day)
    counts = await flow_counts(db, user_id, start, end) | await _snapshot(db, user_id, min(end, now), end)
    return {key: counts[key] for key in ACTIVITY_KEYS}


# --- dashboard ---------------------------------------------------------------------------------------------------------------------

def _own_open(user_id: UUID) -> list:
    """DB5: the leads the telecaller works now -- theirs, not closed, not handed over."""
    return [Enquiry.telecaller_user_id == user_id, Enquiry.status.not_in(CLOSED), Enquiry.owner_id.is_(None)]


def _own_open_follow_ups(user_id: UUID):
    return select(func.count()).select_from(LeadFollowUp).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(
        Enquiry.telecaller_user_id == user_id, LeadFollowUp.status == "open")


def _appointments_today(user_id: UUID, start: datetime, end: datetime):
    counselling = select(
        literal("counselling").label("kind"), Appointment.id, Appointment.appointment_code.label("code"), Enquiry.name.label("title"),
        Appointment.scheduled_at, Appointment.status, Appointment.lead_id,
    ).join(Enquiry, Enquiry.id == Appointment.lead_id).where(
        Appointment.booked_by_user_id == user_id, Appointment.status != CANCELLED, *_in(Appointment.scheduled_at, start, end))
    bdm = select(
        literal("bdm").label("kind"), BdmAppointment.id, BdmMeetingRequest.code, BdmMeetingRequest.organization_name.label("title"),
        BdmAppointment.starts_at.label("scheduled_at"), BdmAppointment.status, literal(None, Uuid).label("lead_id"),
    ).join(BdmAppointment, BdmAppointment.id == BdmMeetingRequest.bdm_appointment_id).where(
        BdmMeetingRequest.requester_user_id == user_id, BdmMeetingRequest.status == "accepted",
        BdmAppointment.status != CANCELLED, *_in(BdmAppointment.starts_at, start, end))
    return counselling.union_all(bdm).subquery()


async def appointments_today(db: AsyncSession, user_id: UUID, now: datetime) -> list[dict]:
    """B5's list: my counselling bookings and my accepted BDM meetings scheduled today, by time."""
    rows = _appointments_today(user_id, *day_range(today_ist(now)))
    result = await db.execute(select(rows).order_by(rows.c.scheduled_at, rows.c.code))
    return [dict(row._mapping) for row in result]


async def tiles(db: AsyncSession, user_id: UUID, team: str, now: datetime) -> dict:
    """§1: the ten tiles for today (Appendix B B1-B10)."""
    today = today_ist(now)
    start, end = day_range(today)
    flow = await flow_counts(db, user_id, start, end)
    became_mine = or_(
        exists(_audit("lead.assign").where(AuditLog.metadata_json["to"].as_string() == str(user_id), *_in(AuditLog.created_at, start, end))),
        exists(_audit("lead.create").where(AuditLog.user_id == user_id, AuditLog.metadata_json["assigned"].as_boolean().is_(True),
                                           *_in(AuditLog.created_at, start, end))),
    )
    first_call = await db.scalar(select(func.count()).select_from(Enquiry).where(*_own_open(user_id), Enquiry.status.in_(FIRST_CALL)))
    due_today = await db.scalar(_own_open_follow_ups(user_id).where(*_in(LeadFollowUp.due_at, start, end)))
    rows = _appointments_today(user_id, start, end)
    daily_calls = next(r for r in (await effective_targets(db, team, user_id, today))["daily"] if r["kpi"] == "calls")
    return {
        "new_leads": await db.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.telecaller_user_id == user_id, became_mine)),
        "calls_today": {"done": flow["calls"], "to_do": first_call + due_today},
        "follow_ups_due": due_today,
        "hot_leads": await db.scalar(select(func.count()).select_from(Enquiry).where(*_own_open(user_id), Enquiry.priority == "hot")),
        "appointments": await db.scalar(select(func.count()).select_from(rows)),
        "connected": flow["connected_calls"],
        "not_connected": flow["not_connected"],
        "converted": flow["converted_leads"],
        "overdue": await db.scalar(_own_open_follow_ups(user_id).where(LeadFollowUp.due_at < now)) + await db.scalar(
            select(func.count()).select_from(Enquiry).where(
                *_own_open(user_id), Enquiry.status == "first_call_pending", Enquiry.stage_changed_at < now - NOT_CONTACTED_AFTER)),
        "daily_target": {"achieved": flow["calls"], "target": daily_calls["value"]},
    }


# --- targets ----------------------------------------------------------------------------------------------------------------------

def _pairs(achieved: dict, targets: list[dict]) -> list[dict]:
    by_kpi = {row["kpi"]: row["value"] for row in targets}
    return [{"kpi": kpi, "achieved": achieved[count], "target": by_kpi.get(kpi)} for kpi, count in KPI_COUNTS.items()]


async def day_targets(db: AsyncSession, user_id: UUID, team: str, day: date, counts: dict) -> list[dict]:
    """One day's achieved figures beside that day's daily targets (tel-022 resolution; a past day keeps its old target, T28)."""
    return _pairs(counts, (await effective_targets(db, team, user_id, day))["daily"])


async def target_progress(db: AsyncSession, user_id: UUID, team: str, now: datetime) -> dict:
    """§15 "Calls: 65 / 80": today against the daily targets, the month to date against the monthly ones."""
    today = today_ist(now)
    targets = await effective_targets(db, team, user_id, today)
    start, end = day_range(today)
    daily = await flow_counts(db, user_id, start, end)
    month = await flow_counts(db, user_id, day_range(today.replace(day=1))[0], end)
    return {"daily": _pairs(daily, targets["daily"]), "monthly": _pairs(month, targets["monthly"])}
