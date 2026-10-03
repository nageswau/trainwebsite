"""bdm-010 (DEC-SCOPE-060, spec §5.2): trip rules, scope, decisions, expenses and audit.

Functions only; nothing here commits -- the route owns the transaction. One transition table (`RULES`) drives both enforcement
and the UI's `can_*` flags. Logs carry ids, route, action and state -- never places, purpose, remarks, reason or amounts (S11)."""

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

logger = logging.getLogger("app.bdm")

INDIA = ZoneInfo("Asia/Kolkata")  # T14: "today" is the India calendar date (as schools.TIER_TIMEZONE)
PAST_DAYS = 30
MAX_SPAN_DAYS = 30  # return - travel <= 30 days, i.e. a trip lasts at most 31 days
MAX_EXPENSES = 100  # §12.1 A9: keeps the detail response bounded
EDITABLE = ("draft", "rejected")
UNDERWAY = ("planned", "in_progress")

RULES = {
    "edit": lambda t, today: t.approval_status in EDITABLE and t.travel_status == "planned",
    "submit": lambda t, today: t.approval_status in EDITABLE and t.travel_status == "planned",
    "withdraw": lambda t, today: t.approval_status == "submitted" and t.travel_status == "planned",
    "decide": lambda t, today: t.approval_status == "submitted" and t.travel_status == "planned",
    "start": lambda t, today: t.approval_status == "approved" and t.travel_status == "planned" and today >= t.travel_date,
    "complete": lambda t, today: t.approval_status == "approved" and t.travel_status in UNDERWAY and today >= t.travel_date,
    "cancel": lambda t, today: t.travel_status in UNDERWAY,
    "expense": lambda t, today: t.approval_status == "approved",
}
VERBS = {"edit": "edited", "submit": "submitted", "withdraw": "withdrawn", "decide": "decided", "start": "started",
         "complete": "completed", "cancel": "cancelled"}
FLAG_ACTIONS = {"can_edit": "edit", "can_submit": "submit", "can_withdraw": "withdraw", "can_start": "start",
                "can_complete": "complete", "can_cancel": "cancel", "can_add_expense": "expense"}


def india_today() -> date:
    return datetime.now(INDIA).date()


def now() -> datetime:
    return datetime.now(UTC)


def check_dates(travel: date, ret: date, today: date) -> None:
    if ret < travel:
        raise HTTPException(422, "Return date must be on or after the travel date")
    if travel < today - timedelta(days=PAST_DAYS):
        raise HTTPException(422, f"Travel date can be at most {PAST_DAYS} days in the past")
    if (ret - travel).days > MAX_SPAN_DAYS:
        raise HTTPException(422, f"A trip can last at most {MAX_SPAN_DAYS + 1} days")


def allowed(trip, action: str, today: date) -> bool:
    return RULES[action](trip, today)


def state_label(trip) -> str:
    status = trip.travel_status if trip.travel_status != "planned" else trip.approval_status
    return status.replace("_", " ")


def refusal(trip, action: str, today: date) -> HTTPException:
    """The 409 for an action outside its row of the transition table, worded for the user."""
    if action == "expense":
        return HTTPException(409, "Expenses can be added once the trip is approved")
    if action in ("start", "complete") and trip.approval_status == "approved" and trip.travel_status in UNDERWAY:
        return HTTPException(409, f"This trip starts on {trip.travel_date:%d %b %Y}; it can be {VERBS[action]} from that day")
    return HTTPException(409, f"This trip is {state_label(trip)} and can't be {VERBS[action]}")


def owner_flags(trip, today: date) -> dict[str, bool]:
    return {flag: allowed(trip, action, today) for flag, action in FLAG_ACTIONS.items()} | {"can_decide": False}


def decider_may(user, manager) -> bool:
    """T2/T3: the BDM's reporting manager decides; any super_admin only while that manager is inactive."""
    if user.role == "bdm_manager":
        return user.id == manager.id
    return user.role == "super_admin" and not manager.active
