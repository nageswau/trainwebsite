"""bdm-006 -- service rules that need no database (spec §4.1, §5.2, §5.4)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import BDM_APPOINTMENT_STATUSES
from app.services import bdm_appointments as svc

NOW = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


def appt(status="scheduled", starts_at=NOW + timedelta(hours=1), owner=None):
    return SimpleNamespace(id=uuid4(), status=status, starts_at=starts_at, bdm_user_id=owner or uuid4())


def user(role="bdm", uid=None):
    return SimpleNamespace(id=uid or uuid4(), role=role)


def test_type_lists_include_common_and_module_without_duplicates():
    for bdm_type, _module_count in (("agent", 9), ("school", 11), ("college", 12)):
        types = svc.appointment_types(bdm_type)
        assert len(types) == len(set(types))
        assert set(types) >= {"college_meeting", "seminar_workshop", "other", "mou_discussion"}
    assert len(svc.appointment_types("agent")) == 8 + 9 - 1  # agent_meeting is in both
    assert len(svc.appointment_types("school")) == 8 + 11 - 1  # mou_discussion
    assert len(svc.appointment_types("college")) == 8 + 12 - 1
    assert "principal_meeting" not in svc.appointment_types("agent") and "agent_visit" not in svc.appointment_types("college")


def test_outcome_lists_per_type():
    assert "agreement_required" in svc.appointment_outcomes("agent") and "course_promotion_interested" not in svc.appointment_outcomes("agent")
    assert svc.appointment_outcomes("school") == svc.appointment_outcomes("college")
    assert "agreement_required" not in svc.appointment_outcomes("college")


EXPECTED = {
    "scheduled": {"confirmed", "rescheduled", "cancelled", "no_show", "completed"},
    "confirmed": {"rescheduled", "cancelled", "no_show", "completed"},
    "rescheduled": {"confirmed", "rescheduled", "cancelled", "no_show", "completed"},
    "completed": set(), "cancelled": set(), "no_show": set(),
}


@pytest.mark.parametrize("src", BDM_APPOINTMENT_STATUSES)
@pytest.mark.parametrize("dst", BDM_APPOINTMENT_STATUSES)
def test_transition_matrix(src, dst):
    allowed = dst in EXPECTED[src]
    assert (dst in svc.TRANSITIONS[src]) is allowed
    if allowed:
        svc.require_transition(appt(src), dst)
    else:
        with pytest.raises(HTTPException) as exc:
            svc.require_transition(appt(src), dst)
        assert exc.value.status_code == 409


def test_future_and_started_rules():
    with pytest.raises(HTTPException) as exc:
        svc.require_future(NOW, NOW)
    assert exc.value.status_code == 422 and exc.value.detail == "Choose a time in the future"
    svc.require_future(NOW + timedelta(minutes=1), NOW)
    with pytest.raises(HTTPException) as exc:
        svc.require_started(appt(starts_at=NOW + timedelta(minutes=1)), NOW, "complete")
    assert exc.value.detail == "You can only complete an appointment after its start time"
    svc.require_started(appt(starts_at=NOW), NOW, "no_show")


def test_owner_rule():
    owner = user()
    svc.require_owner(owner, appt(owner=owner.id), "confirm")
    for other in (user(), user("bdm_manager"), user("super_admin")):
        with pytest.raises(HTTPException) as exc:
            svc.require_owner(other, appt(owner=owner.id), "confirm")
        assert exc.value.status_code == 403 and exc.value.detail == "Only the appointment's BDM can change it"


def test_permissions_by_role_and_state():
    owner = user()
    future, past = appt(owner=owner.id), appt(owner=owner.id, starts_at=NOW - timedelta(minutes=1))
    assert svc.permissions(owner, future, NOW) == {"can_edit": True, "can_confirm": True, "can_reschedule": True, "can_cancel": True, "can_no_show": False, "can_complete": False, "can_edit_report": False}
    assert svc.permissions(owner, past, NOW)["can_complete"] and svc.permissions(owner, past, NOW)["can_no_show"]
    assert svc.permissions(owner, appt("confirmed", owner=owner.id), NOW)["can_confirm"] is False
    assert not any(svc.permissions(owner, appt("cancelled", owner=owner.id), NOW).values())
    assert not any(svc.permissions(user("bdm_manager"), past, NOW).values())


def test_ist_helpers():
    assert svc.format_code(7) == "APT-000007" and svc.format_code(1234567) == "APT-1234567"
    assert svc.today_ist(datetime(2030, 1, 6, 19, 0, tzinfo=UTC)) == date(2030, 1, 7)  # 00:30 IST
