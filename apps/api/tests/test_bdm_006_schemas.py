"""bdm-006 -- request validation (spec §5.1, §12.1 R-A7, §12.3 input validation)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import BdmAppointmentCreate, BdmAppointmentReason, BdmAppointmentReschedule, BdmAppointmentUpdate, BdmMeetingReportCreate


def base(**over) -> dict:
    payload = {
        "organization_id": str(uuid.uuid4()), "contact_id": str(uuid.uuid4()), "starts_at": "2030-01-07T10:00:00+05:30",
        "appointment_type": "college_meeting",
    }
    payload.update(over)
    return payload


def test_minimal_create_defaults_and_minute_normalization():
    model = BdmAppointmentCreate.model_validate(base(starts_at="2030-01-07T10:00:42.5+05:30"))
    assert model.duration_minutes == 60 and model.confirm_overlap is False
    assert model.starts_at == datetime(2030, 1, 7, 4, 30, tzinfo=UTC)
    assert model.location is None and model.expected_revenue is None


@pytest.mark.parametrize(
    "over",
    [
        {"starts_at": "2030-01-07T10:00:00"},  # naive
        {"appointment_type": "lunch"},
        {"duration_minutes": 10},
        {"duration_minutes": 721},
        {"duration_minutes": "60"},
        {"expected_leads": -1},
        {"expected_leads": 1.5},
        {"expected_revenue": -1},
        {"expected_revenue": "1.234"},
        {"location": "x" * 256},
        {"purpose": "bad\x00text"},
        {"code": "APT-000001"},
        {"status": "confirmed"},
        {"bdm_user_id": str(uuid.uuid4())},
        {"contact_name": "Injected"},
        {"outcome": "interested"},
    ],
)
def test_create_rejects(over):
    with pytest.raises(ValidationError):
        BdmAppointmentCreate.model_validate(base(**over))


def test_blank_optional_text_becomes_none_and_is_stripped():
    model = BdmAppointmentCreate.model_validate(base(location="   ", purpose="  Demo  ", expected_revenue="1500.5"))
    assert model.location is None and model.purpose == "Demo" and model.expected_revenue == Decimal("1500.50")


def test_update_forbids_time_status_and_org_and_rejects_null_on_required():
    for bad in ({"starts_at": "2030-01-07T10:00:00+05:30"}, {"status": "cancelled"}, {"organization_id": str(uuid.uuid4())}, {"contact_id": None}, {"duration_minutes": None}):
        with pytest.raises(ValidationError):
            BdmAppointmentUpdate.model_validate(bad)
    assert BdmAppointmentUpdate.model_validate({}).model_dump(exclude_unset=True) == {}


def test_reason_is_required_trimmed_and_bounded():
    for bad in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": "a\x07b"}):
        with pytest.raises(ValidationError):
            BdmAppointmentReason.model_validate(bad)
    assert BdmAppointmentReason.model_validate({"reason": "  Principal on leave "}).reason == "Principal on leave"


def test_reschedule_and_complete_shapes():
    r = BdmAppointmentReschedule.model_validate({"starts_at": "2030-01-08T11:00:00+05:30"})
    assert r.duration_minutes is None and r.reason is None and r.confirm_overlap is False
    with pytest.raises(ValidationError):
        BdmMeetingReportCreate.model_validate({"outcome": "great", "discussion": "x"})
    c = BdmMeetingReportCreate.model_validate({"outcome": "agreement_required", "discussion": "x", "next_follow_up_on": "2030-01-10"})
    assert c.next_follow_up_on.isoformat() == "2030-01-10"
