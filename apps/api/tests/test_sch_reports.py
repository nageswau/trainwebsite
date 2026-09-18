"""School Coordinator/Principal Reports module -- GET /school/reports.

Every figure is computed from live School data, never fabricated (DATA_MODEL.md §8).
A Draft/Verified academic result's existence stays sensitive to these two roles even in
aggregate (SCH-006-AC02) -- results_published must only ever count Published rows.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    Country,
    OverseasApplication,
    School,
    SchoolAcademicResult,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolStudent,
    SchoolTestPrepRecord,
    University,
    User,
    UserRoleAssignment,
    VisaCase,
)

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_roles(db_session) -> dict:
    admin = User(email=f"sch-rpt-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"Reports Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()

    accounts = {}
    for role in ("school_coordinator", "school_principal", "school_teacher", "school_parent"):
        u = User(
            email=f"sch-rpt-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
            full_name=f"Test {role}", role=role, division="overseas", active=True,
            profile={"school_id": str(school.id)},
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
        accounts[role] = u
    academic1 = User(email=f"sch-rpt-academic1-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Academic One", role="academic_team", division="overseas", active=True)
    academic2 = User(email=f"sch-rpt-academic2-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Academic Two", role="academic_team", division="overseas", active=True)
    career_counselor = User(email=f"sch-rpt-career-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Career Counselor", role="career_counselor", division="overseas", active=True)
    psych = User(email=f"sch-rpt-psych-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Psychometric Team", role="psychometric_team", division="overseas", active=True)
    db_session.add_all([academic1, academic2, career_counselor, psych])
    await db_session.commit()
    return {"admin": admin, "school": school, "academic1": academic1, "academic2": academic2, "career_counselor": career_counselor, "psych": psych, **accounts}


@pytest.mark.asyncio
async def test_teacher_and_parent_cannot_access_reports(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_teacher"].email)
    response = await client.get("/api/v1/school/reports")
    assert response.status_code == 403

    await _login(client, ctx["school_parent"].email)
    response = await client.get("/api/v1/school/reports")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_report_figures_match_real_seeded_data(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    school = ctx["school"]

    s1 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Student One", grade_or_class="Grade 5", created_by_user_id=ctx["school_coordinator"].id, assigned_teacher_user_id=ctx["school_teacher"].id)
    s2 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Student Two", grade_or_class="Grade 5", created_by_user_id=ctx["school_coordinator"].id)
    s3 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Student Three", grade_or_class="Grade 6", created_by_user_id=ctx["school_coordinator"].id)
    db_session.add_all([s1, s2, s3])
    await db_session.flush()
    db_session.add(SchoolParentLink(parent_user_id=ctx["school_parent"].id, school_student_id=s1.id, linked_by_user_id=ctx["school_coordinator"].id))

    db_session.add_all(
        [
            SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=ctx["career_counselor"].id, record_type="guidance_session", notes="n"),
            SchoolPsychometricRecord(school_student_id=s1.id, psychometric_team_user_id=ctx["psych"].id, assessment_type="Aptitude", status="completed"),
            SchoolPsychometricRecord(school_student_id=s2.id, psychometric_team_user_id=ctx["psych"].id, assessment_type="Aptitude", status="assigned"),
        ]
    )
    # One Published (must be counted), one Draft and one Verified (must NEVER be counted --
    # SCH-006-AC02 treats their existence as sensitive even in aggregate to this report).
    db_session.add_all(
        [
            SchoolAcademicResult(school_student_id=s1.id, academic_year="2026", term="Term 1", subject="Math", max_marks=100, marks_obtained=90, status="published", uploaded_by_user_id=ctx["academic1"].id, verified_by_user_id=ctx["academic2"].id, published_by_user_id=ctx["academic2"].id),
            SchoolAcademicResult(school_student_id=s2.id, academic_year="2026", term="Term 1", subject="English", max_marks=100, marks_obtained=70, status="draft", uploaded_by_user_id=ctx["academic1"].id),
            SchoolAcademicResult(school_student_id=s3.id, academic_year="2026", term="Term 1", subject="Science", max_marks=100, marks_obtained=80, status="verified", uploaded_by_user_id=ctx["academic1"].id, verified_by_user_id=ctx["academic2"].id),
        ]
    )
    activity = SchoolActivity(school_id=school.id, title="Test Activity", scheduled_at=datetime.now(UTC) - timedelta(days=1), created_by_user_id=ctx["school_coordinator"].id)
    db_session.add(activity)
    await db_session.flush()
    db_session.add_all(
        [
            SchoolActivityAttendance(activity_id=activity.id, school_student_id=s1.id, present=True, marked_by_user_id=ctx["school_coordinator"].id),
            SchoolActivityAttendance(activity_id=activity.id, school_student_id=s2.id, present=True, marked_by_user_id=ctx["school_coordinator"].id),
            SchoolActivityAttendance(activity_id=activity.id, school_student_id=s3.id, present=False, marked_by_user_id=ctx["school_coordinator"].id),
        ]
    )
    await db_session.commit()

    await _login(client, ctx["school_coordinator"].email)
    response = await client.get("/api/v1/school/reports")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["student_count"] == 3
    assert data["students_with_teacher"] == 1
    assert data["teacher_count"] == 1
    assert data["parent_count"] == 1
    assert sorted(data["grade_breakdown"], key=lambda g: g["grade"]) == [{"grade": "Grade 5", "count": 2}, {"grade": "Grade 6", "count": 1}]
    assert data["career_guidance"] == {"students_covered": 1, "total_students": 3}
    assert data["psychometric"] == {"completed": 1, "assigned_only": 1, "total_students": 3}
    # Exactly one student has a Published result -- the Draft and Verified rows above must
    # never surface here, in count or otherwise.
    assert data["results_published"] == {"students_covered": 1, "total_students": 3}
    assert data["activities"] == {"total": 1, "upcoming": 0, "past": 1}
    assert data["attendance"] == {"present": 2, "total": 3}

    # Principal sees the identical report (same institution, same read-only scope).
    await _login(client, ctx["school_principal"].email)
    principal_response = await client.get("/api/v1/school/reports")
    assert principal_response.status_code == 200
    assert principal_response.json() == data


@pytest.mark.asyncio
async def test_a_second_schools_data_never_leaks_into_this_report(client, db_session):
    ctx_a = await _create_school_with_roles(db_session)
    ctx_b = await _create_school_with_roles(db_session)

    student_b = SchoolStudent(school_id=ctx_b["school"].id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Other School Student", grade_or_class="Grade 9", created_by_user_id=ctx_b["school_coordinator"].id)
    db_session.add(student_b)
    await db_session.commit()

    await _login(client, ctx_a["school_coordinator"].email)
    response = await client.get("/api/v1/school/reports")
    assert response.status_code == 200
    data = response.json()
    assert data["student_count"] == 0
    assert data["grade_breakdown"] == []


@pytest.mark.asyncio
async def test_empty_school_reports_honest_zeros_not_fabricated_figures(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    response = await client.get("/api/v1/school/reports")
    assert response.status_code == 200
    data = response.json()
    assert data["student_count"] == 0
    assert data["grade_breakdown"] == []
    assert data["career_guidance"] == {"students_covered": 0, "total_students": 0}
    assert data["psychometric"] == {"completed": 0, "assigned_only": 0, "total_students": 0}
    assert data["results_published"] == {"students_covered": 0, "total_students": 0}
    assert data["attendance"] == {"present": 0, "total": 0}


@pytest.mark.asyncio
async def test_dashboard_exposes_the_full_school_crm_point_one_kpi_board(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    school = ctx["school"]

    # ENH-001 Task 7: the dashboard's grade_8/9/10 KPI counts now read `grade_level`
    # directly instead of regex-parsing `grade_or_class` -- this fixture constructs
    # SchoolStudent rows via the ORM directly (bypassing the API layer that normally
    # populates grade_level from a client-supplied value), so grade_level must be set
    # explicitly here too, matching the grade each label already encodes.
    s8 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Grade Eight", grade_or_class="Grade 8", grade_level=8, created_by_user_id=ctx["school_coordinator"].id)
    s9 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Grade Nine", grade_or_class="Class 9", grade_level=9, created_by_user_id=ctx["school_coordinator"].id)
    s10 = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Grade Ten", grade_or_class="Grade 10-A", grade_level=10, created_by_user_id=ctx["school_coordinator"].id)
    db_session.add_all([s8, s9, s10])
    await db_session.flush()

    db_session.add_all(
        [
            SchoolCareerRecord(school_student_id=s8.id, career_counselor_user_id=ctx["career_counselor"].id, record_type="guidance_session", notes="Guidance complete"),
            SchoolCareerRecord(school_student_id=s9.id, career_counselor_user_id=ctx["career_counselor"].id, record_type="counselling_note", notes="Counselling complete"),
            SchoolPsychometricRecord(school_student_id=s8.id, psychometric_team_user_id=ctx["psych"].id, assessment_type="Aptitude", status="completed"),
            SchoolTestPrepRecord(school_student_id=s8.id, academic_team_user_id=ctx["academic1"].id, test_type="ielts", status="in_progress"),
            SchoolTestPrepRecord(school_student_id=s9.id, academic_team_user_id=ctx["academic1"].id, test_type="sat", status="completed", actual_score="1450"),
            SchoolLanguageRecord(school_student_id=s10.id, academic_team_user_id=ctx["academic1"].id, language="Japanese", certification_status="certified"),
        ]
    )
    country = Country(
        slug=f"sch-dashboard-country-{uuid.uuid4().hex[:8]}",
        name="Dashboard Country",
        overview="Overview",
        tuition="Tuition",
        living_expenses="Living",
        visa_process=[],
        work_opportunities="Work",
        post_study_work="Post-study",
        pr_opportunities="PR",
        faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id,
        slug=f"sch-dashboard-university-{uuid.uuid4().hex[:8]}",
        name="Dashboard University",
        city="City",
        overview="Overview",
        eligibility="Eligibility",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.flush()
    app_shortlisted = OverseasApplication(student_id=None, school_student_id=s8.id, university_id=university.id, intake="Fall 2027", status="university_selection")
    app_offer = OverseasApplication(student_id=None, school_student_id=s9.id, university_id=university.id, intake="Fall 2027", status="offer")
    app_enrolled = OverseasApplication(student_id=None, school_student_id=s10.id, university_id=university.id, intake="Fall 2027", status="enrolled")
    db_session.add_all([app_shortlisted, app_offer, app_enrolled])
    await db_session.flush()
    db_session.add(VisaCase(application_id=app_offer.id, status="checklist"))
    await db_session.commit()

    await _login(client, ctx["school_coordinator"].email)
    response = await client.get("/api/v1/school/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    kpis = {k["key"]: k for k in data["school_crm_kpis"]}

    assert kpis["total_students"]["value"] == 3
    assert kpis["grade_8"]["value"] == 1
    assert kpis["grade_9"]["value"] == 1
    assert kpis["grade_10"]["value"] == 1
    assert kpis["career_guidance_completed"]["value"] == 1
    assert kpis["psychometric_tests_completed"]["value"] == 1
    assert kpis["individual_counselling_completed"]["value"] == 1
    assert kpis["students_in_global_education_pathway"]["value"] == 3
    assert kpis["ielts_training"]["value"] == 1
    assert kpis["sat_preparation"]["value"] == 1
    assert kpis["foreign_language_students"]["value"] == 1
    assert kpis["university_shortlisting"]["value"] == 3
    assert kpis["applications_in_progress"]["value"] == 2
    assert kpis["offers_received"]["value"] == 2
    assert kpis["visa_applications"]["value"] == 1
    assert kpis["students_admitted"]["value"] == 1
    assert kpis["digital_portfolios_created"]["tracked"] is False
    assert kpis["digital_portfolios_created"]["value"] is None
    assert kpis["internships"]["tracked"] is False
    assert {stage["key"]: stage["count"] for stage in data["application_pipeline"]}["offer"] == 1
    assert data["visa_status"] == [{"status": "checklist", "count": 1}]
    assert {chart["key"] for chart in data["untracked_charts"]} == {"skills_training", "internships", "student_participation_by_program"}
