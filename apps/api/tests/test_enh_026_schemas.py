"""ENH-026 -- schema and pure-rule tests (spec §3.1 C1-C8, §11.1 A4/A5/A10)."""
import pytest
from pydantic import ValidationError

from app.schemas import (
    CAREER_STATUS_LABEL,
    CareerRecordFields,
    CareerRecordUpdate,
    career_transition_allowed,
    counts_as_completed,
)


@pytest.mark.parametrize("current,requested,allowed", [
    ("not_started", "scheduled", True), ("not_started", "completed", False), ("not_started", "follow_up_required", False),
    ("scheduled", "completed", True), ("scheduled", "not_started", False),
    ("completed", "follow_up_required", True), ("completed", "scheduled", False),
    ("follow_up_required", "scheduled", True), ("follow_up_required", "completed", True), ("follow_up_required", "not_started", False),
    (None, "completed", True), (None, "follow_up_required", True), (None, "not_started", False), (None, "scheduled", False),
    ("scheduled", "scheduled", True),  # re-sending the current status is a no-op
])
def test_transitions_follow_the_section_7_lifecycle(current, requested, allowed):
    assert career_transition_allowed(current, requested) is allowed


@pytest.mark.parametrize("status,counted", [(None, True), ("completed", True), ("follow_up_required", True), ("not_started", False), ("scheduled", False)])
def test_counts_as_completed(status, counted):
    assert counts_as_completed(status) is counted


def test_labels_cover_every_status_and_legacy():
    assert CAREER_STATUS_LABEL == {"not_started": "Not Started", "scheduled": "Scheduled", "completed": "Completed", "follow_up_required": "Follow-up Required", None: "No status"}


def test_lists_are_cleaned_and_empty_means_none():
    fields = CareerRecordFields.model_validate({"weak_areas": [" Algebra ", "algebra", ""], "recommended_careers": []})
    assert fields.weak_areas == ["Algebra"]
    assert fields.recommended_careers is None


def test_scheduled_for_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"scheduled_for": "2026-10-01T10:00:00"})
    assert CareerRecordFields.model_validate({"scheduled_for": "2026-10-01T10:00:00+05:30"}).scheduled_for is not None


@pytest.mark.parametrize("key", ["career_counselor_user_id", "updated_by_user_id", "school_student_id", "record_type", "id"])
def test_owner_and_identity_fields_are_not_writable(key):
    with pytest.raises(ValidationError):
        CareerRecordUpdate.model_validate({key: "x"})


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"status": "done"})


def test_notes_keep_the_sch_004_rule_but_refuse_nul():
    assert CareerRecordFields.model_validate({"notes": "  Met parents.  "}).notes == "Met parents."
    assert CareerRecordFields.model_validate({"notes": None}).notes == ""
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"notes": "a\x00b"})


def test_expected_status_distinguishes_absent_from_legacy_null():
    assert "expected_status" not in CareerRecordUpdate.model_validate({}).model_fields_set
    update = CareerRecordUpdate.model_validate({"expected_status": None})
    assert "expected_status" in update.model_fields_set and update.expected_status is None


def test_parent_participation_note_is_single_line_and_capped():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"parent_participation_note": "a" * 501})
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"parent_participation_note": "line\nbreak"})
