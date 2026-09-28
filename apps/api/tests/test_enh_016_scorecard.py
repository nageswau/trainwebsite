"""ENH-016 §28 Student Progress Scorecard (spec §6.3; AC14, AC15, Review Focus 4)."""

from datetime import date

import pytest
from enh016_helpers import login, make_school, make_student, make_university

from app.models import (
    OverseasApplication,
    PortfolioEntry,
    PortfolioProfile,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolSkillBatch,
    SchoolSkillEnrollment,
    VisaCase,
)


def _areas(card):
    return {a["key"]: a["state"] for a in card["areas"]}


@pytest.mark.asyncio
async def test_each_area_reports_its_state_and_the_plan_limits_not_started(client, db_session):  # AC15
    ctx = await make_school(db_session, tier="silver")  # bronze + silver services only
    s = await make_student(db_session, ctx, name="Dev", grade_level=11, grade_or_class="Grade 11", date_of_birth=date(2010, 1, 1))
    psych, cc, acad, coord = ctx["psychometric_team"].id, ctx["career_counselor"].id, ctx["academic_team"].id, ctx["school_coordinator"].id
    batch = SchoolSkillBatch(school_id=ctx["school"].id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db_session.add(batch)
    await db_session.flush()
    db_session.add_all([
        SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=psych, assessment_type="A"),  # assigned -> in progress
        SchoolCareerRecord(school_student_id=s.id, career_counselor_user_id=cc, record_type="counselling_note", notes="n"),
        SchoolLanguageRecord(school_student_id=s.id, academic_team_user_id=acad, language="French", certification_status="certified"),
        SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s.id, enrolled_by_user_id=cc),  # enrolled -> in progress
        PortfolioEntry(school_student_id=s.id, section="project", title="P", created_by_user_id=coord, updated_by_user_id=coord),
    ])
    university = await make_university(db_session)
    application = OverseasApplication(student_id=None, school_student_id=s.id, university_id=university.id, intake="Fall 2027", status="eligibility_evaluation")
    db_session.add(application)
    await db_session.flush()
    db_session.add(VisaCase(application_id=application.id))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    response = await client.get(f"/api/v1/school/students/{s.id}/scorecard")

    assert response.status_code == 200, response.text
    card = response.json()
    assert _areas(card) == {
        "career_awareness": "not_started", "psychometric": "in_progress", "career_counselling": "completed", "soft_skills": "in_progress",
        "foreign_language": "completed",  # done counts even outside a silver plan
        "digital_portfolio": "in_progress", "ielts_sat": "not_in_plan", "university_shortlisting": "in_progress", "scholarship": "not_tracked",
        "application": "in_progress", "visa": "in_progress", "internship": "not_tracked",
    }
    assert [a["key"] for a in card["areas"]][:2] == ["career_awareness", "psychometric"]
    assert card["grade"] == "11" and card["full_name"] == "Dev"


@pytest.mark.asyncio
async def test_scorecard_portfolio_percentage_matches_the_portfolio_endpoint(client, db_session):  # AC14
    ctx = await make_school(db_session)
    s = await make_student(db_session, ctx, grade_or_class="Grade 9", grade_level=9, date_of_birth=date(2011, 5, 5))
    coord = ctx["school_coordinator"].id
    db_session.add_all([
        PortfolioEntry(school_student_id=s.id, section="award", title="A", created_by_user_id=coord, updated_by_user_id=coord),
        PortfolioProfile(school_student_id=s.id, personal_statement="Hello"),
        SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A"),
    ])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    card = (await client.get(f"/api/v1/school/students/{s.id}/scorecard")).json()
    portfolio = (await client.get(f"/api/v1/school/students/{s.id}/portfolio")).json()

    assert card["portfolio_completion_pct"] == portfolio["completion_percentage"] > 0


@pytest.mark.asyncio
async def test_grid_filters_by_grade_and_pages_stably(client, db_session):  # D10, Review Focus 4
    ctx = await make_school(db_session)
    for name in ("Cy", "Ab", "Bo"):
        await make_student(db_session, ctx, name=name, grade_level=10)
    await make_student(db_session, ctx, name="Zed", grade_level=12)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    first = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "limit": 2})).json()
    second = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "limit": 2, "offset": 2})).json()
    beyond = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "offset": 50})).json()
    everyone = (await client.get("/api/v1/school/analytics/scorecards")).json()

    assert [c["full_name"] for c in first["items"]] == ["Ab", "Bo"] and first["total"] == 3
    assert [c["full_name"] for c in second["items"]] == ["Cy"]
    assert beyond == {"items": [], "total": 3, "limit": 25, "offset": 50}
    assert everyone["total"] == 4
    assert (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 7})).status_code == 422
    assert (await client.get("/api/v1/school/analytics/scorecards", params={"limit": 101})).status_code == 422
