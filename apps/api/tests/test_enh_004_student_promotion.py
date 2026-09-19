"""ENH-004 -- Student promotion to the next academic year / grade
(docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md, DEC-SCOPE-020)."""

import uuid

import pytest
from pydantic import ValidationError

from app.api.schools import (
    MAX_GRADE_LEVEL,
    REASON_ALREADY_IN_ACTIVE_YEAR,
    REASON_GRADE_LEVEL_NOT_SET,
    REASON_LABEL_UNPARSEABLE,
    REASON_TERMINAL_GRADE,
    _decide_promotion,
    _swap_grade_label,
)
from app.schemas import StudentPromotionRequest

YEAR_OLD = uuid.uuid4()
YEAR_ACTIVE = uuid.uuid4()


# ---------------------------------------------------------------- label swap (pure)


@pytest.mark.parametrize(
    "label,from_level,to_level,expected",
    [
        ("Grade 8-A", 8, 9, "Grade 9-A"),
        ("Class 10", 10, 11, "Class 11"),
        ("grade 5", 5, 6, "grade 6"),
        ("10-A", 10, 11, "11-A"),
        ("Grade 9", 9, 10, "Grade 10"),
        ("Grade 11 (Gold)", 11, 12, "Grade 12 (Gold)"),
    ],
)
def test_swap_grade_label_advances_only_the_grade_number(label, from_level, to_level, expected):
    assert _swap_grade_label(label, from_level, to_level) == (expected, None)


def test_swap_grade_label_leaves_a_missing_label_missing():
    assert _swap_grade_label(None, 8, 9) == (None, None)


@pytest.mark.parametrize("label", ["8A", "Nonsense", "Std IX", ""])
def test_swap_grade_label_refuses_a_label_without_a_grade_number(label):
    new_label, problem = _swap_grade_label(label, 8, 9)
    assert new_label is None
    assert problem and "supply grade_or_class" in problem


def test_swap_grade_label_refuses_a_number_that_disagrees_with_grade_level():
    new_label, problem = _swap_grade_label("Grade 8-A", 9, 10)
    assert new_label is None
    assert problem and "does not match" in problem


def test_swap_grade_label_refuses_a_result_longer_than_60_characters():
    label = "Grade 9 " + "x" * 52  # exactly 60 characters; "9" -> "10" would make it 61
    assert len(label) == 60
    new_label, problem = _swap_grade_label(label, 9, 10)
    assert new_label is None
    assert problem and "60 characters" in problem


# ---------------------------------------------------------------- per-row decision (pure)


def _decide(**overrides):
    args = {"action": "promote", "student_year_id": YEAR_OLD, "active_year_id": YEAR_ACTIVE, "grade_level": 8, "grade_or_class": "Grade 8-A", "override": None}
    args.update(overrides)
    return _decide_promotion(**args)


def test_promote_advances_the_level_and_the_label():
    d = _decide()
    assert (d.status, d.grade_level, d.grade_or_class, d.reason, d.message) == ("promoted", 9, "Grade 9-A", None, None)


def test_promote_uses_the_override_instead_of_the_swap():
    d = _decide(override="Grade 9 (Gold)")
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, "Grade 9 (Gold)")


def test_promote_with_no_label_keeps_no_label():
    d = _decide(grade_or_class=None)
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, None)


def test_hold_back_keeps_grade_and_label():
    d = _decide(action="hold_back")
    assert (d.status, d.grade_level, d.grade_or_class, d.reason) == ("held_back", 8, "Grade 8-A", None)


@pytest.mark.parametrize("grade_level", [12, None])
def test_hold_back_is_allowed_at_the_top_grade_and_with_no_grade(grade_level):
    d = _decide(action="hold_back", grade_level=grade_level)
    assert (d.status, d.grade_level) == ("held_back", grade_level)


@pytest.mark.parametrize("action", ["promote", "hold_back"])
def test_a_student_already_in_the_active_year_is_skipped_and_unchanged(action):
    d = _decide(action=action, student_year_id=YEAR_ACTIVE)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("skipped", REASON_ALREADY_IN_ACTIVE_YEAR, 8, "Grade 8-A")
    assert d.message


def test_a_student_with_no_year_is_processable():
    assert _decide(student_year_id=None).status == "promoted"


def test_promote_without_a_grade_level_fails():
    d = _decide(grade_level=None)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_GRADE_LEVEL_NOT_SET, None, "Grade 8-A")


def test_promote_from_the_top_grade_fails():
    assert MAX_GRADE_LEVEL == 12
    d = _decide(grade_level=12, grade_or_class="Grade 12")
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_TERMINAL_GRADE, 12, "Grade 12")


def test_promote_with_an_unswappable_label_fails_unless_overridden():
    failed = _decide(grade_or_class="8A")
    assert (failed.status, failed.reason, failed.grade_level, failed.grade_or_class) == ("failed", REASON_LABEL_UNPARSEABLE, 8, "8A")
    assert failed.message
    fixed = _decide(grade_or_class="8A", override="Grade 9A")
    assert (fixed.status, fixed.grade_level, fixed.grade_or_class) == ("promoted", 9, "Grade 9A")


# ---------------------------------------------------------------- request model (pure)


def _item(**overrides):
    return {"student_id": str(uuid.uuid4()), "action": "promote", **overrides}


def test_request_accepts_valid_items():
    request = StudentPromotionRequest(items=[_item(), _item(action="hold_back")])
    assert [i.action for i in request.items] == ["promote", "hold_back"]


def test_request_strips_the_override_label():
    request = StudentPromotionRequest(items=[_item(grade_or_class="  Grade 9-A  ")])
    assert request.items[0].grade_or_class == "Grade 9-A"


_DUPLICATE = _item()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [_item() for _ in range(501)]},
        {"items": [_DUPLICATE, _DUPLICATE]},
        {"items": [_item(student_id="not-a-uuid")]},
        {"items": [_item(action="graduate")]},
        {"items": [_item(action="hold_back", grade_or_class="Grade 9")]},
        {"items": [_item(grade_or_class="   ")]},
        {"items": [_item(grade_or_class="x" * 61)]},
        {"items": [_item(grade_or_class="Grade\x00 9")]},
        {"items": [_item(grade_or_class="Grade\n9")]},
        {"items": [_item()], "school_id": str(uuid.uuid4())},
        {"items": [_item(academic_year_id=str(uuid.uuid4()))]},
    ],
    ids=[
        "missing_items", "empty_items", "over_the_cap", "duplicate_id", "not_a_uuid", "unknown_action", "hold_back_with_label", "blank_label", "label_too_long",
        "nul_in_label", "newline_in_label", "client_supplied_school_id", "client_supplied_year_on_item",
    ],
)
def test_request_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        StudentPromotionRequest(**payload)
