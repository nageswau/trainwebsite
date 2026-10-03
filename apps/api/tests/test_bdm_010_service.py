"""bdm-010 -- the transition table and date rules (spec §5.2, T14; AC7, AC8). Pure functions: no database."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import bdm_travel as travel

TODAY = date(2026, 10, 3)


def trip(approval="draft", status="planned", travel_date=TODAY):
    return SimpleNamespace(approval_status=approval, travel_status=status, travel_date=travel_date)


STATES = [(a, t) for a in ("draft", "submitted", "approved", "rejected") for t in ("planned", "in_progress", "completed", "cancelled")
          if t in ("planned", "cancelled") or a == "approved"]
EXPECTED = {
    "edit": {("draft", "planned"), ("rejected", "planned")},
    "submit": {("draft", "planned"), ("rejected", "planned")},
    "withdraw": {("submitted", "planned")},
    "decide": {("submitted", "planned")},
    "start": {("approved", "planned")},
    "complete": {("approved", "planned"), ("approved", "in_progress")},
    "cancel": {(a, t) for a, t in STATES if t in ("planned", "in_progress")},
    "expense": {(a, t) for a, t in STATES if a == "approved"},
}


@pytest.mark.parametrize("action", sorted(EXPECTED))
def test_transition_table(action):
    allowed = {(a, t) for a, t in STATES if travel.allowed(trip(a, t), action, TODAY)}
    assert allowed == EXPECTED[action]


def test_start_and_complete_wait_for_the_travel_date():
    future = trip("approved", "planned", TODAY + timedelta(days=1))
    assert not travel.allowed(future, "start", TODAY) and not travel.allowed(future, "complete", TODAY)
    err = travel.refusal(future, "start", TODAY)
    assert err.status_code == 409 and "04 Oct 2026" in err.detail


def test_refusal_names_the_state():
    err = travel.refusal(trip("approved", "completed"), "cancel", TODAY)
    assert (err.status_code, err.detail) == (409, "This trip is completed and can't be cancelled")
    assert travel.refusal(trip("draft"), "expense", TODAY).detail == "Expenses can be added once the trip is approved"


@pytest.mark.parametrize("travel_date,ret,message", [
    (TODAY, TODAY - timedelta(days=1), "Return date must be on or after the travel date"),
    (TODAY - timedelta(days=31), TODAY, "Travel date can be at most 30 days in the past"),
    (TODAY, TODAY + timedelta(days=31), "A trip can last at most 31 days"),
])
def test_check_dates_refuses(travel_date, ret, message):
    with pytest.raises(HTTPException) as exc:
        travel.check_dates(travel_date, ret, TODAY)
    assert (exc.value.status_code, exc.value.detail) == (422, message)


def test_check_dates_allows_the_edges():
    travel.check_dates(TODAY - timedelta(days=30), TODAY, TODAY)
    travel.check_dates(TODAY, TODAY + timedelta(days=30), TODAY)
    travel.check_dates(TODAY, TODAY, TODAY)  # same-day local trip


def test_owner_flags_follow_the_table():
    flags = travel.owner_flags(trip("approved", "planned"), TODAY)
    assert flags == {"can_edit": False, "can_submit": False, "can_withdraw": False, "can_start": True, "can_complete": True,
                     "can_cancel": True, "can_add_expense": True, "can_decide": False}


def test_decider_may():
    manager = SimpleNamespace(id=1, active=True)
    assert travel.decider_may(SimpleNamespace(id=1, role="bdm_manager"), manager)
    assert not travel.decider_may(SimpleNamespace(id=2, role="bdm_manager"), manager)
    assert not travel.decider_may(SimpleNamespace(id=3, role="super_admin"), manager)
    assert travel.decider_may(SimpleNamespace(id=3, role="super_admin"), SimpleNamespace(id=1, active=False))
