"""School Coordinator/Principal Reports module -- GET /school/reports.

Every figure is computed from live School data, never fabricated (DATA_MODEL.md §8).
A Draft/Verified academic result's existence stays sensitive to these two roles even in
aggregate (SCH-006-AC02) -- results_published must only ever count Published rows.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_password
from app.models import (
    School,
    SchoolAcademicResult,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
    UserRoleAssignment,
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

    s1 = SchoolStudent(school_id=school.id, full_name="Student One", grade_or_class="Grade 5", created_by_user_id=ctx["school_coordinator"].id, assigned_teacher_user_id=ctx["school_teacher"].id)
    s2 = SchoolStudent(school_id=school.id, full_name="Student Two", grade_or_class="Grade 5", created_by_user_id=ctx["school_coordinator"].id)
    s3 = SchoolStudent(school_id=school.id, full_name="Student Three", grade_or_class="Grade 6", created_by_user_id=ctx["school_coordinator"].id)
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

    student_b = SchoolStudent(school_id=ctx_b["school"].id, full_name="Other School Student", grade_or_class="Grade 9", created_by_user_id=ctx_b["school_coordinator"].id)
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
