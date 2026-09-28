"""ENH-016 school-side analytics (spec §6, AC01, AC06-AC08)."""

import pytest
from enh016_helpers import login, make_school, make_student, make_university

from app.models import OverseasApplication, SchoolCareerRecord, SchoolPsychometricRecord


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
