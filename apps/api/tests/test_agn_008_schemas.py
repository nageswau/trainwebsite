"""AGN-008 spec §5.4 -- request schemas: forbid extras, trim, bounds, date sanity, null semantics."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import AgentApplicationCreate, AgentApplicationStatus, AgentApplicationUpdate

IDS = {"agent_student_id": str(uuid.uuid4()), "university_id": str(uuid.uuid4())}


def test_create_trims_and_blanks_become_none():
    body = AgentApplicationCreate(**IDS, intake="  Fall 2027 ", application_reference="  ", next_action=" Send SOP ")
    assert (body.intake, body.application_reference, body.next_action) == ("Fall 2027", None, "Send SOP")


@pytest.mark.parametrize("extra", [{"agent_id": str(uuid.uuid4())}, {"status": "offer"}, {"student_id": str(uuid.uuid4())}])
def test_create_forbids_server_owned_fields(extra):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", **extra)


@pytest.mark.parametrize("intake", ["", "   ", "x" * 81])
def test_create_needs_an_intake_of_1_to_80(intake):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake=intake)


def test_reference_and_next_action_limits_and_control_characters():
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", application_reference="x" * 141)
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", next_action="x" * 501)
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", application_reference="AB\x00C")


@pytest.mark.parametrize("field", ["submitted_on", "application_deadline", "offer_deadline"])
@pytest.mark.parametrize("value", [date(1999, 12, 31), date(2101, 1, 1)])
def test_dates_outside_2000_to_2100_are_refused(field, value):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", **{field: value})


def test_submission_date_allows_one_day_ahead_of_utc_and_no_more():
    today = datetime.now(UTC).date()
    AgentApplicationCreate(**IDS, intake="Fall", submitted_on=today + timedelta(days=1))
    with pytest.raises(ValidationError, match="Submission date cannot be in the future"):
        AgentApplicationCreate(**IDS, intake="Fall", submitted_on=today + timedelta(days=2))


def test_past_deadlines_are_allowed():
    AgentApplicationCreate(**IDS, intake="Fall", application_deadline=date(2020, 1, 1))


def test_update_absent_is_unchanged_null_clears_and_intake_cannot_clear():
    body = AgentApplicationUpdate(application_reference=None)
    assert body.model_fields_set == {"application_reference"} and body.application_reference is None
    with pytest.raises(ValidationError):
        AgentApplicationUpdate(intake=None)
    with pytest.raises(ValidationError):
        AgentApplicationUpdate(university_id=str(uuid.uuid4()))


def test_status_body_bounds():
    AgentApplicationStatus(to_status="offer", expected_status="enquiry", notes="ok")
    with pytest.raises(ValidationError):
        AgentApplicationStatus(to_status="offer", notes="x" * 2001)
    with pytest.raises(ValidationError):
        AgentApplicationStatus(to_status="offer", agent_id="x")
