"""ENH-027 -- PsychometricResultFields (spec §4.1)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import PSYCHOMETRIC_RESULT_KEYS, PsychometricResultFields, validation_message


def _error(data: dict) -> str:
    with pytest.raises(ValidationError) as exc:
        PsychometricResultFields.model_validate(data)
    return validation_message(exc.value)


def test_keys_are_the_ten_columns_in_order():
    assert PSYCHOMETRIC_RESULT_KEYS == (
        "test_date", "strengths", "interest_areas", "personality_indicators", "recommended_careers",
        "recommended_stream", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
    )


def test_valid_full_input_is_normalised():
    fields = PsychometricResultFields.model_validate({
        "test_date": "2026-09-10", "strengths": ["  Logic ", "logic", "", "Verbal"], "counsellor_remarks": "  Line 1\nLine 2  ",
        "parent_discussion_on": "", "follow_up_on": None,
    })
    assert fields.test_date == date(2026, 9, 10)
    assert fields.strengths == ["Logic", "Verbal"]  # trimmed, case-insensitive de-dup, blanks dropped
    assert fields.counsellor_remarks == "Line 1\nLine 2"
    assert fields.parent_discussion_on is None  # blank string -> None
    assert fields.model_fields_set == {"test_date", "strengths", "counsellor_remarks", "parent_discussion_on", "follow_up_on"}


def test_empty_list_and_blank_text_become_none():
    fields = PsychometricResultFields.model_validate({"interest_areas": [" ", ""], "parent_discussion_notes": "   "})
    assert fields.interest_areas is None and fields.parent_discussion_notes is None


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"strengths": "Logic"}, "strengths"),
        ({"strengths": [f"s{i}" for i in range(21)]}, "strengths"),
        ({"interest_areas": ["x" * 81]}, "interest_areas"),
        ({"personality_indicators": ["ok", "bad\x00"]}, "personality_indicators"),
        ({"recommended_stream": ["a‮b"]}, "recommended_stream"),
        ({"counsellor_remarks": "x" * 4001}, "counsellor_remarks"),
        ({"parent_discussion_notes": "x" * 2001}, "parent_discussion_notes"),
        ({"counsellor_remarks": "a‮b"}, "counsellor_remarks"),
        ({"counsellor_remarks": 42}, "counsellor_remarks"),
        ({"test_date": "2026-02-30"}, "test_date"),
        ({"test_date": "10/09/2026"}, "test_date"),
        ({"test_date": "2026-09-10T00:00:00"}, "test_date"),
        ({"test_date": "20260910"}, "test_date"),
        ({"follow_up_on": 1700000000}, "follow_up_on"),
        ({"parent_discussion_on": "2026-W37-1"}, "parent_discussion_on"),
    ],
)
def test_invalid_values_name_the_field_and_never_echo_the_value(data, field):
    message = _error(data)
    assert message.startswith(f"{field} "), message
    assert "x" * 81 not in message and "Logic" not in message


def test_multiline_remarks_keep_line_breaks_but_list_items_do_not():
    assert PsychometricResultFields.model_validate({"counsellor_remarks": "a\n\tb"}).counsellor_remarks == "a\n\tb"
    assert _error({"strengths": ["a\nb"]}).startswith("strengths ")
