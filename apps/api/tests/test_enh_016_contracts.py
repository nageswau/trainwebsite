"""ENH-016 contract tests (spec §5): /school/entitlements stays byte-identical after the service_usage() extraction except D13
(AC11), and /school/dashboard gains tracked portfolios/skills without losing a key (AC12)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from enh016_helpers import login, make_school, make_student, make_university

from app.models import (
    OverseasApplication,
    PortfolioEntry,
    SchoolActivity,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolSkillBatch,
    SchoolSkillEnrollment,
    SchoolStaffAssignment,
    SchoolTestPrepRecord,
    VisaCase,
)


async def _seed_every_source(db, ctx):
    """One row (or more) in every source /school/entitlements counts. s2 has a portfolio entry and a soft-skills enrolment."""
    s1 = await make_student(db, ctx)
    s2 = await make_student(db, ctx)
    cc, psych, acad, coord = ctx["career_counselor"].id, ctx["psychometric_team"].id, ctx["academic_team"].id, ctx["school_coordinator"].id
    school_id = ctx["school"].id
    db.add_all([
        SchoolPsychometricRecord(school_student_id=s1.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
        SchoolPsychometricRecord(school_student_id=s2.id, psychometric_team_user_id=psych, assessment_type="A"),
        SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="counselling_note", notes="n"),
        SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="guidance_session", notes="n"),
        SchoolTestPrepRecord(school_student_id=s1.id, academic_team_user_id=acad, test_type="ielts"),
        SchoolTestPrepRecord(school_student_id=s2.id, academic_team_user_id=acad, test_type="sat"),
        SchoolTestPrepRecord(school_student_id=s2.id, academic_team_user_id=acad, test_type="sat"),
        SchoolLanguageRecord(school_student_id=s1.id, academic_team_user_id=acad, language="French"),
        SchoolActivity(school_id=school_id, title="Seminar", scheduled_at=datetime.now(UTC) - timedelta(days=1), created_by_user_id=coord, activity_type="career_seminar"),
        SchoolActivity(school_id=school_id, title="Visit", scheduled_at=datetime.now(UTC) + timedelta(days=1), created_by_user_id=coord, activity_type="campus_visit"),
        SchoolActivity(school_id=school_id, title="Free text", scheduled_at=datetime.now(UTC), created_by_user_id=coord),
        SchoolStaffAssignment(school_id=school_id, user_id=cc, role="career_counselor", assigned_by_user_id=ctx["overseas_admin"].id),
        PortfolioEntry(school_student_id=s2.id, section="award", title="Prize", created_by_user_id=coord, updated_by_user_id=coord),
    ])
    university = await make_university(db)
    application = OverseasApplication(student_id=None, school_student_id=s1.id, university_id=university.id, intake="Fall 2027", status="offer")
    db.add(application)
    await db.flush()
    db.add(VisaCase(application_id=application.id, status="checklist"))
    batch = SchoolSkillBatch(school_id=school_id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db.add(batch)
    await db.flush()
    db.add(SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s2.id, enrolled_by_user_id=cc))
    await db.commit()


@pytest.mark.asyncio
async def test_entitlements_usage_is_unchanged_except_digital_portfolio(client, db_session):
    ctx = await make_school(db_session, tier="platinum")
    await _seed_every_source(db_session, ctx)
    await login(client, ctx["school_coordinator"])

    response = await client.get("/api/v1/school/entitlements")

    assert response.status_code == 200, response.text
    used = {s["key"]: s["used"] for s in response.json()["services"]}
    assert used == {
        "career_seminar": 1, "career_awareness_session": 0, "parent_orientation": 0, "psychometric_test": 2, "soft_skills": 1,
        "individual_counselling": 1, "web_designing": 0,
        "application_support": 1, "scholarship_assistance": None, "ielts_coaching": 1, "sat_coaching": 2, "foreign_language_classes": 1,
        "digital_portfolio_creation": 1,  # D13 -- was None before ENH-016
        "dedicated_counselor": True, "monthly_campus_visits": 1, "internships": 0, "visa_support": 1,  # ENH-021: tracked since the merge with main
        "loan_assistance": None,
        "alumni_network": None, "parent_help_desk": None,
    }
    assert [s["key"] for s in response.json()["services"]][:3] == ["career_seminar", "career_awareness_session", "parent_orientation"]
    assert all(s["included"] is True for s in response.json()["services"])


@pytest.mark.asyncio
async def test_service_usage_keeps_schools_apart(db_session):
    from app.api.schools import service_usage

    a = await make_school(db_session)
    b = await make_school(db_session)
    await _seed_every_source(db_session, a)

    usage = await service_usage(db_session, [a["school"].id, b["school"].id])

    assert usage[a["school"].id]["psychometric_test"] == 2
    assert usage[b["school"].id]["psychometric_test"] == 0
    assert usage[b["school"].id]["dedicated_counselor"] is False
    assert usage[b["school"].id]["digital_portfolio_creation"] == 0
    assert "scholarship_assistance" not in usage[a["school"].id]
    assert await service_usage(db_session, []) == {}


@pytest.mark.asyncio
async def test_dashboard_tracks_portfolios_and_skills_and_keeps_every_key(client, db_session):  # AC12, AC13
    from app.models import PortfolioProfile

    ctx = await make_school(db_session)
    await _seed_every_source(db_session, ctx)  # s2 has a portfolio entry and a soft-skills enrolment
    only_profile = await make_student(db_session, ctx, grade_level=8, grade_or_class="Grade 8")
    db_session.add(PortfolioProfile(school_student_id=only_profile.id, personal_statement="   "))
    await db_session.commit()
    await login(client, ctx["school_principal"])

    response = await client.get("/api/v1/school/dashboard")

    assert response.status_code == 200, response.text
    data = response.json()
    kpis = {k["key"]: k for k in data["school_crm_kpis"]}
    assert kpis["digital_portfolios_created"] == {"key": "digital_portfolios_created", "label": "Digital Portfolios Created", "value": 1, "tracked": True, "note": None}
    assert kpis["internships"]["tracked"] is True  # ENH-021
    assert data["skills_training"] == {"soft_skills": 1, "digital_skills": 0, "total_students": 3}
    assert {c["key"] for c in data["untracked_charts"]} == {"student_participation_by_program"}
    for key in ("student_count", "students_with_teacher", "teacher_count", "parent_count", "principal_count", "pending_invite_count", "grade_breakdown",
                "career_guidance", "psychometric", "results_published", "activities", "attendance", "upcoming_activities", "completion",
                "global_education", "application_pipeline", "visa_status"):
        assert key in data, key
    assert data["teacher_count"] == 1 and data["principal_count"] == 1 and data["parent_count"] == 1
