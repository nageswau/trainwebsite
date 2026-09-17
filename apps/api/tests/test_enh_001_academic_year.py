"""ENH-001 -- Academic-Year foundation model (docs/delivery/ENHANCEMENT_BACKLOG.md,
docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md)."""

from app.models import AcademicYear, SchoolStudent


def test_academic_year_model_has_expected_columns():
    columns = AcademicYear.__table__.columns
    assert "label" in columns
    assert columns["label"].unique is True
    assert "start_date" in columns
    assert "end_date" in columns
    assert columns["status"].default.arg == "active"


def test_school_student_has_academic_year_and_grade_level_columns():
    columns = SchoolStudent.__table__.columns
    assert columns["academic_year_id"].nullable is True
    assert columns["grade_level"].nullable is True
    # grade_or_class must be untouched -- zero data loss per the spec.
    assert "grade_or_class" in columns
