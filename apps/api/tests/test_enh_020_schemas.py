"""ENH-020 -- funding support case schemas (spec §3.2/§3.3, D3, AC05/AC06/AC10; plan Review Focus 5)."""

from itertools import product
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    FUNDING_FINAL_STATUSES,
    FUNDING_STATUS_LABEL,
    FUNDING_STATUS_NEXT,
    FUNDING_SUPPORT_TYPE_LABEL,
    FundingRecordCreate,
    FundingRecordUpdate,
    FundingStatus,
    FundingSupportType,
    funding_transition_allowed,
    validation_message,
)

STATUSES = list(get_args(FundingStatus))
ALLOWED = {
    ("required", "counselling"), ("counselling", "documents"), ("documents", "application"), ("application", "approved"), ("approved", "completed"),
    ("required", "closed"), ("counselling", "closed"), ("documents", "closed"), ("application", "closed"), ("approved", "closed"),
}


def _create(**body):
    return FundingRecordCreate.model_validate({"school_student_id": str(uuid4()), "support_type": "education_loan", **body})


def _message(model, body) -> str:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(body)
    return validation_message(caught.value)


@pytest.mark.parametrize("current,requested", list(product(STATUSES, STATUSES)))
def test_every_status_pair(current, requested):
    expected = requested == current or (current, requested) in ALLOWED
    assert funding_transition_allowed(current, requested) is expected


def test_the_source_stages_in_order_then_closed():
    assert STATUSES == ["required", "counselling", "documents", "application", "approved", "completed", "closed"]
    assert list(get_args(FundingSupportType)) == ["education_loan", "financial_assistance", "scholarship", "funding_guidance"]


def test_finals_are_completed_and_closed():
    assert FUNDING_FINAL_STATUSES == {"completed", "closed"}
    assert all(FUNDING_STATUS_NEXT[s] == frozenset() for s in FUNDING_FINAL_STATUSES)


def test_labels_cover_every_value():
    assert set(FUNDING_STATUS_LABEL) == set(STATUSES)
    assert set(FUNDING_SUPPORT_TYPE_LABEL) == set(get_args(FundingSupportType))
    assert FUNDING_STATUS_LABEL["counselling"] == "Counselling" and FUNDING_SUPPORT_TYPE_LABEL["education_loan"] == "Education loan"


@pytest.mark.parametrize("key", ["status", "school_id", "career_counselor_user_id", "status_changed_on"])
def test_create_forbids_status_owner_and_school(key):
    body = {"school_student_id": str(uuid4()), "support_type": "scholarship", key: "x"}
    assert _message(FundingRecordCreate, body) == f"{key} is not an accepted field"


@pytest.mark.parametrize("key", ["support_type", "school_student_id", "school_id", "career_counselor_user_id"])
def test_update_forbids_type_ids_and_owner(key):
    assert _message(FundingRecordUpdate, {key: "x"}) == f"{key} is not an accepted field"


def test_create_needs_a_known_type_and_a_real_id():
    with pytest.raises(ValidationError):
        FundingRecordCreate.model_validate({"school_student_id": "not-a-uuid", "support_type": "education_loan"})
    with pytest.raises(ValidationError):
        FundingRecordCreate.model_validate({"school_student_id": str(uuid4()), "support_type": "grant"})


def test_update_status_must_be_a_known_stage():
    with pytest.raises(ValidationError):
        FundingRecordUpdate.model_validate({"status": "rejected"})
    assert FundingRecordUpdate.model_validate({"status": "closed"}).status == "closed"


@pytest.mark.parametrize("field,limit", [("provider_name", 200), ("amount_text", 120)])
def test_single_line_fields_trim_blank_and_cap(field, limit):
    assert getattr(_create(**{field: "  HDFC  "}), field) == "HDFC"
    assert getattr(_create(**{field: "   "}), field) is None
    assert getattr(_create(**{field: "x" * limit}), field) == "x" * limit
    body = {"school_student_id": str(uuid4()), "support_type": "scholarship", field: "x" * (limit + 1)}
    assert _message(FundingRecordCreate, body) == f"{field} must be at most {limit} characters"
    body[field] = "line one\nline two"
    assert _message(FundingRecordCreate, body) == f"{field} must not contain control or bidirectional-override characters"


def test_closure_reason_is_single_line_and_capped():
    assert FundingRecordUpdate.model_validate({"closure_reason": "  Loan refused  "}).closure_reason == "Loan refused"
    assert FundingRecordUpdate.model_validate({"closure_reason": "  "}).closure_reason is None
    assert _message(FundingRecordUpdate, {"closure_reason": "x" * 501}) == "closure_reason must be at most 500 characters"


def test_indic_zero_width_joiner_accepted_bidi_override_refused():
    assert _create(provider_name="ಕರ್ನಾಟಕ‍ ಬ್ಯಾಂಕ್").provider_name == "ಕರ್ನಾಟಕ‍ ಬ್ಯಾಂಕ್"
    body = {"school_student_id": str(uuid4()), "support_type": "scholarship", "provider_name": "‮knab"}
    assert _message(FundingRecordCreate, body) == "provider_name must not contain control or bidirectional-override characters"


def test_notes_multiline_capped_and_nul_refused():
    assert _create(notes="first\nsecond").notes == "first\nsecond"
    assert _create(notes=None).notes == ""
    assert _create().notes == ""
    body = {"school_student_id": str(uuid4()), "support_type": "scholarship", "notes": "x" * 4001}
    assert _message(FundingRecordCreate, body) == "notes must be at most 4000 characters"
    body["notes"] = "bad\x00"
    assert _message(FundingRecordCreate, body) == "notes must not contain NUL characters"


def test_update_tracks_only_sent_fields():
    fields = FundingRecordUpdate.model_validate({"status": "counselling", "expected_status": "required"})
    assert fields.model_fields_set == {"status", "expected_status"}
