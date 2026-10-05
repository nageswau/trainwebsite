import pytest
from pydantic import ValidationError

from app.schemas import ActivityFeedbackCreate

# ENH-018 spec §5.1: the POST body. No database needed.
VALID = {"rating": 4, "satisfaction": 5, "feedback": "Well run session."}


def test_minimal_valid_body_and_optional_fields_default_to_none():
    body = ActivityFeedbackCreate(**VALID)
    assert (body.rating, body.satisfaction, body.feedback, body.suggestions, body.trainer_name) == (4, 5, "Well run session.", None, None)


@pytest.mark.parametrize("field", ["rating", "satisfaction"])
@pytest.mark.parametrize("value", [0, 6, -1, "5", 4.5, True, None])
def test_scores_are_strict_integers_from_one_to_five(field, value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, field: value})


@pytest.mark.parametrize("value", [1, 5])
def test_score_bounds_are_inclusive(value):
    assert ActivityFeedbackCreate(**{**VALID, "rating": value}).rating == value


@pytest.mark.parametrize("value", ["", "   ", "\n\t "])
def test_blank_feedback_is_rejected_not_stored(value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "feedback": value})


def test_text_is_trimmed_newlines_kept_and_blank_optionals_become_none():
    body = ActivityFeedbackCreate(**{**VALID, "feedback": "  Line one\nLine two  ", "suggestions": "  ", "trainer_name": "  Ms. Rao  "})
    assert body.feedback == "Line one\nLine two"
    assert body.suggestions is None
    assert body.trainer_name == "Ms. Rao"


def test_length_limits():
    ActivityFeedbackCreate(**{**VALID, "feedback": "x" * 5000, "suggestions": "y" * 5000, "trainer_name": "z" * 200})
    for field, size in (("feedback", 5001), ("suggestions", 5001), ("trainer_name", 201)):
        with pytest.raises(ValidationError):
            ActivityFeedbackCreate(**{**VALID, field: "x" * size})


@pytest.mark.parametrize("value", ["bad\x00byte", "bidi‮override"])
def test_nul_and_bidi_overrides_are_rejected(value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "feedback": value})


def test_trainer_name_is_single_line():
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "trainer_name": "Ms.\nRao"})


@pytest.mark.parametrize("extra", ["school_id", "submitted_by_user_id", "activity_id", "id"])
def test_server_owned_fields_cannot_be_supplied(extra):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, extra: "00000000-0000-0000-0000-000000000000"})
