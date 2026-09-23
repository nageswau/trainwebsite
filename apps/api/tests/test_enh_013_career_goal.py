"""ENH-013 -- PATCH /school/students/{id}/career-goal (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6.2)."""
import pytest
from pydantic import ValidationError

from app.schemas import CareerGoalUpdate


@pytest.mark.parametrize("raw, expected", [("  Technology  ", "Technology"), ("", None), ("   ", None), (None, None), ("a" * 120, "a" * 120)])
def test_career_goal_update_cleans_and_clears(raw, expected):
    assert CareerGoalUpdate(career_goal=raw).career_goal == expected


@pytest.mark.parametrize("payload", [{"career_goal": "a" * 121}, {"career_goal": "Line\nbreak"}, {"career_goal": "Bad\x00byte"}, {"career_goal": "Rev‮ersed"}, {}, {"career_goal": "x", "school_id": "y"}])
def test_career_goal_update_rejects(payload):
    with pytest.raises(ValidationError):
        CareerGoalUpdate(**payload)


def test_tab_keys_are_the_sixteen_in_display_order():
    from app.schemas import TAB_360_KEYS
    assert TAB_360_KEYS == ("overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance", "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates", "documents", "teacher_remarks", "parent_communication", "edusphere_programs")
