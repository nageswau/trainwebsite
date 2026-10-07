"""tel-021 (DEC-SCOPE-105, spec §2): the single source of every Telecaller CRM count -- the daily activity D1-D13, the dashboard tiles
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
    TEL_SETTING_DEFAULTS,
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
    TelSetting,
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


def _group(rows) -> dict:
    return {key: count for key, count in rows}


async def conversions_by_user(db: AsyncSession, user_ids: list[UUID], start: datetime, end: datetime) -> dict[UUID, int]:
    """D13 (DB2) per telecaller: leads still converted whose conversion was first recorded in the range, credited to whoever owned the
    lead at that instant. The owner is computed in an inner select so the outer query groups on a plain column."""
    first = (
        select(LeadStageHistory.lead_id, func.min(LeadStageHistory.created_at).label("at"))
        .where(LeadStageHistory.to_stage == "converted").group_by(LeadStageHistory.lead_id).subquery()
    )
    owners = select(owner_at(first.c.at).label("owner")).select_from(Enquiry).join(first, first.c.lead_id == Enquiry.id).where(
        Enquiry.status == "converted", *_in(first.c.at, start, end)).subquery()
    return _group(await db.execute(select(owners.c.owner, func.count()).where(owners.c.owner.in_(user_ids)).group_by(owners.c.owner)))


async def _by_actor(db: AsyncSession, actor, user_ids: list[UUID], *where) -> dict[UUID, int]:
    return _group(await db.execute(select(actor, func.count()).where(actor.in_(user_ids), *where).group_by(actor)))


async def flow_counts_by_user(db: AsyncSession, user_ids: list[UUID], start: datetime, end: datetime) -> dict[UUID, dict]:
    """Every count that is a number of events in [start, end), for several telecallers at once -- one grouped query per count, so a
    report over a whole team costs the same as one telecaller (tel-024 R3). Users with no events get zeros."""
    ids = list(user_ids)
    calls = {key: (total, missed) for key, total, missed in await db.execute(
        select(LeadCall.caller_user_id, func.count(), func.count().filter(LeadCall.outcome.in_(NOT_CONNECTED)))
        .where(LeadCall.caller_user_id.in_(ids), *_in(LeadCall.occurred_at, start, end)).group_by(LeadCall.caller_user_id))}
    counselor = await _by_actor(db, Appointment.booked_by_user_id, ids, Appointment.lead_id.is_not(None), *_in(Appointment.created_at, start, end))
    bdm = await _by_actor(db, BdmMeetingRequest.requester_user_id, ids, *_in(BdmMeetingRequest.created_at, start, end))
    completed = await _by_actor(db, LeadFollowUp.completed_by_user_id, ids, *_in(LeadFollowUp.completed_at, start, end))
    whatsapp = await _by_actor(db, LeadMessage.sender_user_id, ids, LeadMessage.channel == "whatsapp", *_in(LeadMessage.sent_at, start, end))
    qualified = await _by_actor(db, LeadStageHistory.actor_user_id, ids, LeadStageHistory.to_stage == "qualified", *_in(LeadStageHistory.created_at, start, end))
    converted = await conversions_by_user(db, ids, start, end)
    out = {}
    for user_id in ids:
        total, missed = calls.get(user_id, (0, 0))
        out[user_id] = {
            "calls": total, "connected_calls": total - missed, "not_connected": missed,
            "follow_ups_completed": completed.get(user_id, 0),
            "counselor_appointments": counselor.get(user_id, 0), "bdm_appointments": bdm.get(user_id, 0),
            "new_appointments": counselor.get(user_id, 0) + bdm.get(user_id, 0),
            "whatsapp_messages": whatsapp.get(user_id, 0), "qualified_leads": qualified.get(user_id, 0),
            "converted_leads": converted.get(user_id, 0),
        }
    return out


async def flow_counts(db: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> dict:
    """Every count that is a number of events in [start, end), for one telecaller."""
    return (await flow_counts_by_user(db, [user_id], start, end))[user_id]


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


def _became_mine(user_id: UUID, start: datetime, end: datetime):
    """DB8: the lead became the telecaller's in [start, end) -- a `lead.assign` to them, or a lead they created already assigned."""
    return or_(
        exists(_audit("lead.assign").where(AuditLog.metadata_json["to"].as_string() == str(user_id), *_in(AuditLog.created_at, start, end))),
        exists(_audit("lead.create").where(AuditLog.user_id == user_id, AuditLog.metadata_json["assigned"].as_boolean().is_(True),
                                           *_in(AuditLog.created_at, start, end))),
    )


async def leads_received(db: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> int:
    """tel-023 P1 (PF2): distinct leads that became the telecaller's in the range, kept or since reassigned."""
    return await db.scalar(select(func.count()).select_from(Enquiry).where(_became_mine(user_id, start, end)))


async def _not_contacted_after(db: AsyncSession, team: str) -> timedelta:
    """DB1 / DEC-SCOPE-111 AL12: the team's Lead Not Contacted hours (tel-020), the default for a team without a row."""
    hours = await db.scalar(select(TelSetting.not_contacted_hours).where(TelSetting.team == team))
    return timedelta(hours=hours or TEL_SETTING_DEFAULTS["not_contacted_hours"])


async def tiles(db: AsyncSession, user_id: UUID, team: str, now: datetime) -> dict:
    """§1: the ten tiles for today (Appendix B B1-B10)."""
    today = today_ist(now)
    start, end = day_range(today)
    flow = await flow_counts(db, user_id, start, end)
    first_call = await db.scalar(select(func.count()).select_from(Enquiry).where(*_own_open(user_id), Enquiry.status.in_(FIRST_CALL)))
    due_today = await db.scalar(_own_open_follow_ups(user_id).where(*_in(LeadFollowUp.due_at, start, end)))
    rows = _appointments_today(user_id, start, end)
    daily_calls = next(r for r in (await effective_targets(db, team, user_id, today))["daily"] if r["kpi"] == "calls")
    return {
        "new_leads": await db.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.telecaller_user_id == user_id, _became_mine(user_id, start, end))),
        "calls_today": {"done": flow["calls"], "to_do": first_call + due_today},
        "follow_ups_due": due_today,
        "hot_leads": await db.scalar(select(func.count()).select_from(Enquiry).where(*_own_open(user_id), Enquiry.priority == "hot")),
        "appointments": await db.scalar(select(func.count()).select_from(rows)),
        "connected": flow["connected_calls"],
        "not_connected": flow["not_connected"],
        "converted": flow["converted_leads"],
        "overdue": await db.scalar(_own_open_follow_ups(user_id).where(LeadFollowUp.due_at < now)) + await db.scalar(
            select(func.count()).select_from(Enquiry).where(
                *_own_open(user_id), Enquiry.status == "first_call_pending", Enquiry.stage_changed_at < now - await _not_contacted_after(db, team))),
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
