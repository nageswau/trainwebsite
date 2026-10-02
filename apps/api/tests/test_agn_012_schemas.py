"""AGN-012 (DEC-SCOPE-055) -- request schemas and the pure rules of services/agent_visa.py (spec §4, §10.1)."""

from datetime import date

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.schemas import AgentVisaStart, AgentVisaUpdate
from app.services.agent_visa import INTERVIEW_BEFORE_APPLICATION, VISA_CASE_STAGES, check_dates, stage_index


def test_stage_list_is_unchanged_and_still_importable_from_workflows():
    from app.api.workflows import VISA_CASE_STAGES as from_workflows
    from app.api.workflows import VISA_DECISION_DISCLAIMER as disclaimer

    assert VISA_CASE_STAGES == ["checklist", "documentation", "interview_prep", "tracking", "decision"]
    assert from_workflows is VISA_CASE_STAGES
    assert disclaimer.startswith("Visa decisions are made by the relevant government")


@pytest.mark.parametrize(("stage", "index"), [("checklist", 0), ("decision", 4), ("not_started", -1), ("", -1)])
def test_stage_index_counts_a_legacy_stage_as_before_checklist(stage, index):
    assert stage_index(stage) == index


def test_start_accepts_named_document_types_and_optional_dates():
    body = AgentVisaStart.model_validate({"expected_status": "offer", "checklist": ["Passport", "Financial documents"], "interview_date": "2027-06-01"})
    assert body.checklist == ["Passport", "Financial documents"] and body.interview_date == date(2027, 6, 1) and body.visa_application_date is None
    assert AgentVisaStart.model_validate({"expected_status": "offer"}).checklist == []


@pytest.mark.parametrize(
    "body",
    [
        {"expected_status": "offer", "checklist": ["Other"]},
        {"expected_status": "offer", "checklist": ["Passport", "Passport"]},
        {"expected_status": "offer", "checklist": ["Visa form"]},
        {"expected_status": "offer", "checklist": ["Passport"] * 9},
        {"expected_status": "offer", "status": "decision"},  # no stage field: a case always starts at checklist
        {"expected_status": "offer", "visa_application_date": "1999-12-31"},
        {"checklist": []},
    ],
)
def test_start_rejects(body):
    with pytest.raises(ValidationError):
        AgentVisaStart.model_validate(body)


def test_update_keeps_absent_and_null_apart():
    body = AgentVisaUpdate.model_validate({"expected_stage": "documentation", "interview_date": None})
    assert body.model_dump(exclude_unset=True) == {"expected_stage": "documentation", "interview_date": None}


@pytest.mark.parametrize(
    "body",
    [
        {"expected_stage": "decision", "decision": "pending"},
        {"expected_stage": "decision", "decision": None},
        {"expected_stage": "checklist", "to_stage": None},
        {"expected_stage": "checklist", "to_stage": "approved"},
        {"expected_stage": "checklist", "checklist": None},
        {"expected_stage": "checklist", "checklist": ["Other"]},
        {"expected_stage": "checklist", "tracking_reference": "X"},
        {"to_stage": "documentation"},
    ],
)
def test_update_rejects(body):
    with pytest.raises(ValidationError):
        AgentVisaUpdate.model_validate(body)


def test_date_order_allows_same_day_and_either_alone():
    check_dates(date(2027, 5, 1), date(2027, 5, 1))
    check_dates(None, date(2027, 5, 1))
    check_dates(date(2027, 5, 1), None)


def test_interview_before_application_is_a_field_error():
    with pytest.raises(RequestValidationError) as caught:
        check_dates(date(2027, 5, 2), date(2027, 5, 1))
    (error,) = caught.value.errors()
    assert error["loc"] == ("body", "interview_date") and error["msg"] == INTERVIEW_BEFORE_APPLICATION
