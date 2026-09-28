"""ENH-016 school-side analytics (spec §6, AC01, AC06-AC08)."""

import pytest
from enh016_helpers import login, make_school, make_student, make_university

from app.models import OverseasApplication, SchoolAcademicResult, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord, SchoolTestPrepRecord


def _result(student, uploader, *, subject, marks, status="published", term="Term 1", year="2026-27"):
    return SchoolAcademicResult(school_student_id=student.id, academic_year=year, term=term, subject=subject, max_marks=100, marks_obtained=marks, status=status, uploaded_by_user_id=uploader)


@pytest.mark.asyncio
async def test_grade_performance_counts_per_grade_with_proxies_and_fallbacks(client, db_session):
    ctx = await make_school(db_session)
    g10 = await make_student(db_session, ctx, grade_level=10, grade_or_class="Grade 10-A")
    g10_label_only = await make_student(db_session, ctx, grade_level=None, grade_or_class="Class 10")  # Review Focus 2
    await make_student(db_session, ctx, grade_level=5, grade_or_class="Grade 5")  # outside 8-12 -> "other"
    await make_student(db_session, ctx)  # no grade at all -> "unspecified"
    cc, psych = ctx["career_counselor"].id, ctx["psychometric_team"].id
    db_session.add_all([
        SchoolCareerRecord(school_student_id=g10.id, career_counselor_user_id=cc, record_type="guidance_session", notes="n"),
        SchoolPsychometricRecord(school_student_id=g10.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
        SchoolPsychometricRecord(school_student_id=g10_label_only.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
    ])
    university = await make_university(db_session)
    db_session.add(OverseasApplication(student_id=None, school_student_id=g10.id, university_id=university.id, intake="Fall 2027", status="university_selection"))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    response = await client.get("/api/v1/school/analytics/grade-performance")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grades"] == ["10", "other", "unspecified"]
    assert body["students"] == {"10": 2, "other": 1, "unspecified": 1}
    rows = {row["key"]: row for row in body["metrics"]}
    assert rows["career_readiness"]["cells"]["10"] == {"count": 1, "pct": 50.0}
    assert rows["career_readiness"]["is_proxy"] is True and rows["career_readiness"]["definition"]
    assert rows["assessment_completion"]["cells"]["10"] == {"count": 2, "pct": 100.0}
    assert rows["assessment_completion"]["is_proxy"] is False and rows["assessment_completion"]["definition"] is None
    assert rows["application_readiness"]["cells"]["10"]["count"] == 1
    assert rows["global_education_interest"]["cells"]["10"]["count"] == 1
    assert rows["admissions"]["cells"]["other"] == {"count": 0, "pct": 0.0}
    assert list(rows) == ["career_readiness", "assessment_completion", "counselling_completion", "skills_development", "global_education_interest", "application_readiness", "university_applications", "admissions"]


@pytest.mark.asyncio
async def test_grade_performance_for_an_empty_school_is_empty_not_an_error(client, db_session):  # Review Focus 1
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    response = await client.get("/api/v1/school/analytics/grade-performance")

    assert response.status_code == 200
    assert response.json()["grades"] == [] and response.json()["students"] == {}
    assert all(row["cells"] == {} for row in response.json()["metrics"])


@pytest.mark.asyncio
async def test_student_development_pending_is_total_minus_completed_and_published_only(client, db_session):  # AC06, AC08
    ctx = await make_school(db_session)
    acad = ctx["academic_team"].id
    weak = await make_student(db_session, ctx, name="Asha Weak", grade_level=9)
    strong = await make_student(db_session, ctx, name="Ben Strong", grade_level=9)
    middle = await make_student(db_session, ctx, name="Cara Middle", grade_level=10)
    db_session.add_all([
        _result(weak, acad, subject="Maths", marks=30), _result(weak, acad, subject="Science", marks=35),
        _result(strong, acad, subject="Maths", marks=95), _result(strong, acad, subject="Maths", marks=20, status="draft"),  # draft never counts
        _result(middle, acad, subject="Maths", marks=60, term="Term 2"),
        _result(middle, acad, subject="Maths", marks=10, status="withdrawn"),  # withdrawn never counts
        SchoolLanguageRecord(school_student_id=middle.id, academic_team_user_id=acad, language="German", certification_status="certified"),
        SchoolTestPrepRecord(school_student_id=strong.id, academic_team_user_id=acad, test_type="ielts", status="completed"),
    ])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    response = await client.get("/api/v1/school/analytics/student-development")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["headcounts"] == {"students": 3, "teachers": 1, "parents": 1}
    rows = {r["key"]: r for r in body["activities"]}
    assert list(rows) == ["career_guidance", "psychometric_test", "foreign_language", "english_testing", "university_guidance"]
    assert rows["foreign_language"] == {"key": "foreign_language", "label": "Foreign Language", "completed": 1, "pending": 2}
    assert rows["english_testing"]["completed"] == 1 and rows["english_testing"]["pending"] == 2
    assert all(r["completed"] + r["pending"] == 3 for r in body["activities"])
    assert [p["full_name"] for p in body["at_risk"]["items"]] == ["Asha Weak"]
    assert body["at_risk"]["items"][0]["average_pct"] == 32.5 and body["at_risk"]["items"][0]["grade"] == "9"
    assert [p["full_name"] for p in body["top_performers"]["items"]] == ["Ben Strong"]
    assert body["top_performers"]["items"][0]["average_pct"] == 95.0 and body["top_performers"]["items"][0]["result_count"] == 1
    subjects = {r["key"]: r for r in body["by_subject"]}
    assert subjects["Maths"]["count"] == 3 and subjects["Maths"]["average_pct"] == round((30 + 95 + 60) / 3, 1)
    assert [r["key"] for r in body["by_term"]] == ["2026-27 · Term 1", "2026-27 · Term 2"]
    assert {r["key"]: r["average_pct"] for r in body["by_grade"]} == {"9": 63.8, "10": 60.0}


@pytest.mark.asyncio
async def test_thresholds_are_configurable_and_validated(client, db_session):  # AC07, Review Focus 1
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])
    ok = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 50, "top_from": 90})
    assert ok.status_code == 200 and ok.json()["at_risk_below"] == 50 and ok.json()["top_from"] == 90
    assert ok.json()["at_risk"] == {"items": [], "total": 0} and ok.json()["headcounts"]["students"] == 0
    assert (await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 101})).status_code == 422
    assert (await client.get("/api/v1/school/analytics/student-development", params={"top_from": "abc"})).status_code == 422
    same = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 60, "top_from": 60})
    assert same.status_code == 422 and same.json()["detail"] == "at_risk_below must be less than top_from"
