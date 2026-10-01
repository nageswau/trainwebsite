"""ENH-028 -- per-row validation of bulk CSV rows (spec §6). Every value arrives as a CSV string; every failure is one
'<column> <reason>' message (validation_message) that never echoes the submitted value."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BulkLanguageRow, BulkPsychometricRow, BulkResultRow, BulkTestPrepRow, validation_message

RESULT = {"academic_year": "2026", "term": "Term 1", "subject": "Mathematics", "max_marks": "100", "marks_obtained": "88", "grade": "", "teacher_remarks": ""}


def _error(model, data) -> str:
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    return validation_message(exc.value)


def test_a_valid_result_row_parses_numbers_and_blanks():
    row = BulkResultRow.model_validate({**RESULT, "grade": " A ", "teacher_remarks": "Good\nwork"})
    assert (row.max_marks, row.marks_obtained, row.grade, row.teacher_remarks) == (100.0, 88.0, "A", "Good\nwork")
    assert BulkResultRow.model_validate(RESULT).grade is None


def test_unknown_columns_are_ignored():
    row = BulkResultRow.model_validate({**RESULT, "status": "published", "uploaded_by_user_id": "x", "student_name": "Asha"})
    assert not hasattr(row, "status")


@pytest.mark.parametrize("field", ["academic_year", "term", "subject"])
def test_required_result_text(field):
    assert _error(BulkResultRow, {**RESULT, field: "  "}) == f"{field} is required"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("academic_year", "2" * 21, "academic_year must be at most 20 characters"),
        ("term", "t" * 41, "term must be at most 40 characters"),
        ("subject", "s" * 81, "subject must be at most 80 characters"),
        ("grade", "g" * 11, "grade must be at most 10 characters"),
        ("subject", "Ma\x00ths", "subject must not contain control or bidirectional-override characters"),
        ("teacher_remarks", "r" * 2001, "teacher_remarks must be 2000 characters or fewer"),
    ],
)
def test_result_text_bounds(field, value, message):
    assert _error(BulkResultRow, {**RESULT, field: value}) == message


@pytest.mark.parametrize(
    ("max_marks", "obtained", "message"),
    [
        ("", "5", "max_marks is required"),
        ("abc", "5", "max_marks must be a number"),
        ("nan", "5", "max_marks must be a number"),
        ("inf", "5", "max_marks must be a number"),
        ("0", "0", "max_marks must be greater than 0 and at most 9999.99"),
        ("10000", "5", "max_marks must be greater than 0 and at most 9999.99"),
        ("100", "", "marks_obtained is required"),
        ("100", "-1", "marks_obtained must be between 0 and 9999.99"),
        ("100", "150", "marks_obtained must not exceed max_marks"),
    ],
)
def test_result_marks(max_marks, obtained, message):
    assert _error(BulkResultRow, {**RESULT, "max_marks": max_marks, "marks_obtained": obtained}) == message


def test_marks_equal_to_max_and_decimals_are_accepted():
    row = BulkResultRow.model_validate({**RESULT, "max_marks": "9999.99", "marks_obtained": "9999.99"})
    assert row.marks_obtained == 9999.99


PSYCH = {"assessment_type": "Aptitude", "report_url": "", "test_date": "", "strengths": "", "counsellor_remarks": ""}


def test_psychometric_lists_split_on_semicolons_and_dates_parse():
    row = BulkPsychometricRow.model_validate({**PSYCH, "strengths": "Logic; maths ;logic;;", "test_date": "2026-09-01"})
    assert row.strengths == ["Logic", "maths"]
    assert row.test_date == date(2026, 9, 1)
    assert row.report_url is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("assessment_type", "", "assessment_type is required"),
        ("assessment_type", "a" * 121, "assessment_type must be at most 120 characters"),
        ("report_url", "javascript:alert(1)", "report_url must start with http:// or https://"),
        ("report_url", "https://x.example/" + "a" * 490, "report_url must be at most 500 characters"),
        ("test_date", "2026-13-01", "test_date must be a date in YYYY-MM-DD format"),
        ("strengths", ";".join(f"s{i}" for i in range(21)), "strengths must have at most 20 items"),
    ],
)
def test_psychometric_bounds(field, value, message):
    assert _error(BulkPsychometricRow, {**PSYCH, field: value}) == message


def test_psychometric_report_url_accepts_http_and_https():
    assert BulkPsychometricRow.model_validate({**PSYCH, "report_url": "HTTPS://x.example/r.pdf"}).report_url == "HTTPS://x.example/r.pdf"


def test_test_prep_type_is_case_insensitive_and_allowlisted():
    assert BulkTestPrepRow.model_validate({"test_type": " IELTS ", "target_score": "7.5"}).test_type == "ielts"
    assert _error(BulkTestPrepRow, {"test_type": "toefl"}) == "test_type must be one of ielts, sat"
    assert _error(BulkTestPrepRow, {"test_type": ""}) == "test_type is required"
    assert _error(BulkTestPrepRow, {"test_type": "sat", "target_score": "9" * 21}) == "target_score must be at most 20 characters"


def test_language_bounds():
    assert BulkLanguageRow.model_validate({"language": " French ", "level": ""}).language == "French"
    assert _error(BulkLanguageRow, {"language": " "}) == "language is required"
    assert _error(BulkLanguageRow, {"language": "L" * 61}) == "language must be at most 60 characters"
    assert _error(BulkLanguageRow, {"language": "French", "level": "Z" * 31}) == "level must be at most 30 characters"
