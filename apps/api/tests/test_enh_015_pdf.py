"""ENH-015 -- the PDF renderer on its own (spec §5; AC08). Pure: dict in, bytes out, no database."""

from datetime import date, datetime

from pdf_text import pdf_text

from app.reporting.pdf import render_progress_report, render_school_summary

AS_OF = date(2026, 9, 29)


def _summary(**overrides) -> dict:
    data = {
        "school_name": "Greenfield High",
        "as_of": AS_OF,
        "academic_year": "2026-27",
        "total_students": 3,
        "kpis": [("Total students", 3), ("Career guidance", 2), ("Psychometric assessment completed", 1)],
        "grades": ["Grade 9", "Unspecified"],
        "students": {"Grade 9": 2, "Unspecified": 1},
        "metrics": [
            {"label": "Assessment completion", "is_proxy": False, "definition": None, "cells": {"Grade 9": {"count": 1, "pct": 50.0}, "Unspecified": {"count": 0, "pct": 0.0}}},
            {
                "label": "Skills development",
                "is_proxy": True,
                "definition": "Students enrolled in a skills batch",
                "cells": {"Grade 9": {"count": 2, "pct": 100.0}, "Unspecified": {"count": 0, "pct": 0.0}},
            },
        ],
    }
    return {**data, **overrides}


def _overview(**overrides) -> dict:
    data = {
        "student": {"full_name": "Asha Rao", "student_code": "STU-0001", "grade_or_class": "Grade 9", "section": "B", "school_name": "Greenfield High", "assigned_teacher_name": "Mr Iyer"},
        "career_guidance": {
            "status": "completed",
            "sessions": [{"status": "completed", "completed_on": date(2026, 8, 1), "notes": "Explored engineering", "counselor_name": "Ms Kapoor", "recommended_careers": ["Engineer", "Architect"]}],
        },
        "counselling": {"status": "not_started", "notes": []},
        "recommended_careers": [],
        "structured_recommendations": [],
        "psychometric": {
            "status": "completed",
            "assessments": [{"assessment_type": "Aptitude", "status": "completed", "created_at": datetime(2026, 7, 1, 10, 0), "strengths": ["Logic"], "counsellor_remarks": "Strong reasoning"}],
        },
        "test_prep": {"status": "not_started", "records": []},
        "foreign_language": {"status": "not_started", "records": []},
        "results": [{"subject": "Mathematics", "term": "Term 1", "academic_year": "2026-27", "marks_obtained": 45.0, "max_marks": 50.0, "percentage": 90.0, "grade": "A1", "teacher_remarks": None}],
        "activities": {"attended": [{"title": "Career fair", "scheduled_at": datetime(2026, 8, 10, 9, 0), "present": True}], "upcoming": []},
        "global_education": {"status": "not_started", "applications": []},
        "skills": {"soft_skills": {"status": "not_started", "enrollments": []}, "digital_skills": {"status": "not_started", "enrollments": []}},
    }
    return {**data, **overrides}


def test_school_summary_is_a_pdf_with_the_management_figures_and_grade_table():
    pdf = render_school_summary(_summary())
    assert pdf.startswith(b"%PDF-")
    text = pdf_text(pdf)
    for expected in ("School Summary Report", "Greenfield High", "29 Sep 2026", "2026-27", "Career guidance", "Assessment completion", "Grade 9", "1 (50%)", "Students enrolled in a skills batch"):
        assert expected in text, expected


def test_school_summary_of_an_empty_school_says_so():
    text = pdf_text(render_school_summary(_summary(total_students=0, grades=[], students={}, metrics=[], kpis=[("Total students", 0)])))
    assert "No students on the roster yet." in text


def test_school_summary_with_no_figures_still_renders():  # reportlab rejects a Table with no rows
    assert render_school_summary(_summary(kpis=[], grades=[], students={}, metrics=[])).startswith(b"%PDF-")


def test_school_summary_without_an_active_academic_year():
    assert "No active academic year" in pdf_text(render_school_summary(_summary(academic_year=None)))


def test_progress_report_renders_the_student_and_every_section():
    pdf = render_progress_report(_overview(), AS_OF)
    assert pdf.startswith(b"%PDF-")
    text = pdf_text(pdf)
    for expected in (
        "Student Progress Report",
        "Asha Rao",
        "STU-0001",
        "Greenfield High",
        "Explored engineering",
        "Engineer, Architect",
        "Aptitude",
        "Strong reasoning",
        "Mathematics",
        "90",
        "Career fair",
        "29 Sep 2026",
    ):
        assert expected in text, expected


def test_progress_report_says_when_a_section_has_no_records():
    text = pdf_text(render_progress_report(_overview(), AS_OF))
    assert "No records yet." in text


def test_markup_in_text_is_rendered_literally():  # AC08: Platypus parses <, > and & as markup
    nasty = 'Use <b>bold</b> & <font color="red">x</font> and a lone < sign'
    overview = _overview(career_guidance={"status": "completed", "sessions": [{"status": "completed", "notes": nasty}]})
    text = pdf_text(render_progress_report(overview, AS_OF))
    assert "<b>bold</b>" in text
    assert "a lone < sign" in text


def test_markup_in_the_school_name_is_rendered_literally():
    assert "A & B <School>" in pdf_text(render_school_summary(_summary(school_name="A & B <School>")))


def test_non_latin_text_does_not_break_generation():  # known limitation: glyphs may not show, but nothing fails
    overview = _overview(student={**_overview()["student"], "full_name": "आशा राव"})
    assert render_progress_report(overview, AS_OF).startswith(b"%PDF-")


def test_control_characters_do_not_break_generation():
    overview = _overview(career_guidance={"status": "completed", "sessions": [{"status": "completed", "notes": "a\x00b\x07c\nline two"}]})
    assert "line two" in pdf_text(render_progress_report(overview, AS_OF))
