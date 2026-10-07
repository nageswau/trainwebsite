"""tel-010 (DEC-SCOPE-096, spec §1-§4): calls logged on a lead -- the outcome catalogue and its pipeline effects, the time and outcome
rules, the lead's call list, the same-day edit/delete gate and the day counts.

A call belongs to its lead: reads go through the lead's scope (`lead_pipeline.scope`), so a call on a lead the caller can't see is the
same 404 as a missing one. Only the lead's telecaller logs (D8), and only the caller changes a call, on its IST day (CL4). Writes lock the
lead first (the order of every lead write). Functions only; nothing here commits. Logs and audit carry ids, the outcome and field names --
never remarks."""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED, ORDER
from app.models import LEAD_CALL_OUTCOMES, AuditLog, Enquiry, LeadCall, TelecallerProfile, User
from app.schemas import LeadCallCreate
from app.services import lead_follow_ups, lead_pipeline, telecaller_leads
from app.services.bdm_activities import BACKDATE_DAYS, CLOCK_TOLERANCE, day_range
from app.services.bdm_appointments import today_ist

logger = logging.getLogger("app.leads")

# D1 / §2: EVID-019 L226-L250, in the source's order.
OUTCOMES = dict(zip(LEAD_CALL_OUTCOMES, (
    "Connected – Interested", "Connected – Need Information", "Connected – Follow-up Required", "Connected – Appointment Fixed",
    "Not Interested", "Wrong Number", "Busy", "No Answer", "Switched Off", "Call Back Requested", "Already Joined Elsewhere", "Duplicate Lead",
    "Not Eligible",
), strict=True))
NOT_CONNECTED = frozenset({"busy", "no_answer", "switched_off", "wrong_number"})  # D2: Appendix B B7
UNREACHED = NOT_CONNECTED - {"wrong_number"}  # -> tel-004 `call_unconnected`
CLOSES = {"not_interested": "not_interested", "wrong_number": "wrong_number", "already_joined": "lost", "not_eligible": "not_eligible"}
FOLLOW_UP_REQUIRED = frozenset({"follow_up_required", "call_back_requested"})  # D4
DAILY_CAP = 300  # D9: an abuse bound, far above real use

NOT_FOUND = "Call not found"
TELECALLER_ONLY = "Only the lead's telecaller can log a call"
CALLER_ONLY = "Only the telecaller who logged this call can change it"
LEAD_CLOSED = "This lead is closed. A manager can reopen it before a call is logged"
FUTURE = "The call time can't be in the future"
TOO_OLD = f"Calls can be logged up to {BACKDATE_DAYS} days back"
NOT_TODAY = "Only today's calls can be changed"
MOVE_TODAY = "A call can only be moved within today"
CAP_REACHED = f"You've logged {DAILY_CAP} calls for this day"
FOLLOW_UP_NEEDED = "Add the next follow-up for this outcome"
FOLLOW_UP_CLOSING = "This outcome closes the lead, so it takes no follow-up"
REMARKS_NEEDED = "Add remarks naming the other lead"


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    """On the field (the validation-error shape), so the form can place it."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_time(occurred_at: datetime, now: datetime) -> datetime:
    """D6 (bdm-009 V4 + V9): up to CLOCK_TOLERANCE ahead is stored as `now`, so no future call is ever stored."""
    if occurred_at > now + CLOCK_TOLERANCE:
        raise _invalid("occurred_at", FUTURE, occurred_at.isoformat())
    if today_ist(occurred_at) < today_ist(now) - timedelta(days=BACKDATE_DAYS):
        raise _invalid("occurred_at", TOO_OLD, occurred_at.isoformat())
    return min(occurred_at, now)


def editable(call: LeadCall, now: datetime) -> bool:
    return today_ist(call.occurred_at) == today_ist(now)


def can_change(user: User, lead: Enquiry, call: LeadCall, now: datetime) -> bool:
    return user.role == "telecaller" and call.caller_user_id == user.id and not telecaller_leads.read_only(user, lead) and editable(call, now)


def out(user: User, lead: Enquiry, call: LeadCall, caller: User, now: datetime) -> dict:
    return {
        "id": call.id, "lead_id": call.lead_id, "occurred_at": call.occurred_at, "duration_seconds": call.duration_seconds,
        "call_type": call.call_type, "outcome": call.outcome, "outcome_label": OUTCOMES[call.outcome], "connected": call.outcome not in NOT_CONNECTED,
        "remarks": call.remarks, "caller": {"id": caller.id, "full_name": caller.full_name}, "created_at": call.created_at,
        "can_change": can_change(user, lead, call, now),
    }


async def lead_page(db: AsyncSession, user: User, lead: Enquiry, now: datetime, limit: int, offset: int) -> dict:
    """The lead's calls, newest first."""
    where = LeadCall.lead_id == lead.id
    total = await db.scalar(select(func.count()).select_from(LeadCall).where(where))
    stmt = select(LeadCall, User).join(User, User.id == LeadCall.caller_user_id).where(where)
    rows = (await db.execute(stmt.order_by(LeadCall.occurred_at.desc(), LeadCall.created_at.desc()).limit(limit).offset(offset))).all()
    return {"items": [out(user, lead, call, caller, now) for call, caller in rows], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, user: User, call_id: UUID, now: datetime) -> dict:
    call, lead, caller = (await db.execute(
        select(LeadCall, Enquiry, User).join(Enquiry, Enquiry.id == LeadCall.lead_id).join(User, User.id == LeadCall.caller_user_id)
        .where(LeadCall.id == call_id).execution_options(populate_existing=True)
    )).one()
    return out(user, lead, call, caller, now)


def require_telecaller(user: User, detail: str = TELECALLER_ONLY) -> None:
    if user.role != "telecaller":
        raise HTTPException(403, detail)


def _check_outcome(payload: LeadCallCreate) -> None:
    """CL3 + D4, before anything is written."""
    if payload.outcome == "duplicate_lead" and not payload.remarks:
        raise _invalid("remarks", REMARKS_NEEDED, payload.remarks)
    if payload.outcome in FOLLOW_UP_REQUIRED and payload.next_follow_up is None:
        raise _invalid("next_follow_up", FOLLOW_UP_NEEDED, None)
    if payload.outcome in CLOSES and payload.next_follow_up is not None:
        raise _invalid("next_follow_up", FOLLOW_UP_CLOSING, None)


async def _apply_effect(db: AsyncSession, user: User, lead: Enquiry, outcome: str) -> None:
    """D3 / §2. tel-004's events move a lead only from their from-set, so a repeated outcome never moves it twice (AC1)."""
    if outcome in CLOSES:
        await lead_pipeline.person_move(db, lead, user, "telecaller", CLOSES[outcome], OUTCOMES[outcome])
    elif outcome in UNREACHED:
        await lead_pipeline.apply_event(db, lead, "call_unconnected", user)
    elif outcome != "duplicate_lead":
        await lead_pipeline.apply_event(db, lead, "call_connected", user)
        if outcome == "interested" and lead.status in ORDER and ORDER.index(lead.status) < ORDER.index("interested"):
            await lead_pipeline.person_move(db, lead, user, "telecaller", "interested", None)


async def create(db: AsyncSession, user: User, lead: Enquiry, payload: LeadCallCreate, now: datetime) -> tuple[LeadCall, UUID | None]:
    """The caller locked the lead and checked role and handover. CL2 closed -> 409; D6 time; CL3/D4 outcome rules; D9 cap; the effect;
    the call; D5 the next follow-up (tel-011's rules, so a refusal there rolls the whole call back)."""
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    occurred_at = check_time(payload.occurred_at or now, now)
    _check_outcome(payload)
    start, end = day_range(today_ist(occurred_at))
    count = await db.scalar(select(func.count()).select_from(LeadCall).where(
        LeadCall.caller_user_id == user.id, LeadCall.occurred_at >= start, LeadCall.occurred_at < end))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, CAP_REACHED)
    await _apply_effect(db, user, lead, payload.outcome)
    call = LeadCall(lead_id=lead.id, caller_user_id=user.id, occurred_at=occurred_at, duration_seconds=payload.duration_seconds,
                    call_type=payload.call_type, outcome=payload.outcome, remarks=payload.remarks)
    db.add(call)
    await db.flush()
    follow_up = None
    if payload.next_follow_up is not None:
        follow_up = await lead_follow_ups.create(db, user, lead, payload.next_follow_up, now)
    audit(db, user, "create", call.id, {"lead_id": str(lead.id), "outcome": call.outcome, "follow_up_id": str(follow_up.id) if follow_up else None})
    return call, follow_up.id if follow_up else None


async def load_for_write(db: AsyncSession, user: User, call_id: UUID, scope: list, now: datetime) -> LeadCall:
    """In scope (404) -> lead lock -> telecaller and the caller (403) -> handover (403) -> call lock -> its IST day (409)."""
    lead_id = await db.scalar(select(LeadCall.lead_id).join(Enquiry, Enquiry.id == LeadCall.lead_id).where(LeadCall.id == call_id, *scope))
    if lead_id is None:
        raise HTTPException(404, NOT_FOUND)
    lead = await lead_pipeline.locked_lead(db, lead_id, *scope)
    call = await db.scalar(select(LeadCall).where(LeadCall.id == call_id).with_for_update().execution_options(populate_existing=True))
    if call is None:  # deleted while we waited for the lead lock
        raise HTTPException(404, NOT_FOUND)
    require_telecaller(user, CALLER_ONLY)
    if call.caller_user_id != user.id:
        raise HTTPException(403, CALLER_ONLY)
    telecaller_leads.require_writable(user, lead)
    if not editable(call, now):
        raise HTTPException(409, NOT_TODAY)
    return call


def apply_update(db: AsyncSession, user: User, call: LeadCall, changes: dict, now: datetime) -> list[str]:
    """CL4: only values that differ are written; a moved time stays in today; a duplicate keeps its remarks. Returns the changed fields."""
    changed = sorted(key for key, value in changes.items() if getattr(call, key) != value)
    if "occurred_at" in changed:
        changes["occurred_at"] = check_time(changes["occurred_at"], now)
        if today_ist(changes["occurred_at"]) != today_ist(now):
            raise _invalid("occurred_at", MOVE_TODAY, changes["occurred_at"].isoformat())
    if "remarks" in changed and call.outcome == "duplicate_lead" and not changes["remarks"]:
        raise _invalid("remarks", REMARKS_NEEDED, None)
    for key in changed:
        setattr(call, key, changes[key])
    if changed:
        audit(db, user, "update", call.id, {"fields": changed})
    return changed


def caller_filter(user: User) -> list:
    """AC4: calls *made by* the caller scope -- a telecaller's own, a manager's direct reports', super_admin all. Other roles 403."""
    if user.role == "telecaller":
        return [LeadCall.caller_user_id == user.id]
    if user.role == "super_admin":
        return []
    if user.role == "telecaller_manager":
        return [LeadCall.caller_user_id.in_(select(TelecallerProfile.user_id).where(TelecallerProfile.reporting_manager_user_id == user.id))]
    raise HTTPException(403, lead_pipeline.ROLE_REQUIRED)


async def day_counts(db: AsyncSession, filters: list, day: date) -> dict:
    start, end = day_range(day)
    rows = (await db.execute(
        select(LeadCall.outcome, func.count()).where(*filters, LeadCall.occurred_at >= start, LeadCall.occurred_at < end).group_by(LeadCall.outcome)
    )).all()
    by_outcome = dict.fromkeys(OUTCOMES, 0) | dict(rows)
    not_connected = sum(by_outcome[key] for key in NOT_CONNECTED)
    total = sum(by_outcome.values())
    return {"day": day, "total": total, "connected": total - not_connected, "not_connected": not_connected, "by_outcome": by_outcome}


def audit(db: AsyncSession, user: User, action: str, call_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"lead_call.{action}", entity_type="lead_call", entity_id=str(call_id), metadata_json=metadata or {}))


def log(event: str, user: User, call_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "call_id": str(call_id), **extra}})
