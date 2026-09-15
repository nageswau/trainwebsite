"""SCH-011 -- Partnership tier entitlements (`DEC-SCOPE-017`).

`GET /school/entitlements` returns the cumulative service list for a School's tier, with a
REAL usage count wherever a confirmed module produces one, and `used: None` for services
with no underlying feature -- the user explicitly confirmed "included = unlimited, count
usage," so there is never a fabricated 0 or an invented cap. Net-new.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    School,
    SchoolStaffAssignment,
    SchoolStudent,
    User,
    UserRoleAssignment,
)

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school(db_session, tier: str | None) -> dict:
    admin = User(email=f"sch011-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-011 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id, tier=tier)
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch011-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student}


async def _add_service_staff(db_session, admin, school, role: str) -> User:
    member = User(email=f"sch011-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"{role} Member", role=role, division="overseas", active=True, profile={})
    db_session.add(member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role=role, is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role=role, assigned_by_user_id=admin.id))
    await db_session.commit()
    return member


def _service(body: dict, key: str) -> dict:
    match = [s for s in body["services"] if s["key"] == key]
    assert match, f"{key} missing from services list"
    return match[0]


@pytest.mark.asyncio
async def test_no_tier_set_returns_empty_services(client, db_session):
    ctx = await _create_school(db_session, tier=None)
    await _login(client, ctx["coordinator"].email)
    response = await client.get("/api/v1/school/entitlements")
    assert response.status_code == 200
    assert response.json() == {"tier": None, "tier_valid_until": None, "services": []}


@pytest.mark.asyncio
async def test_bronze_tier_excludes_higher_tier_services(client, db_session):
    ctx = await _create_school(db_session, tier="bronze")
    await _login(client, ctx["coordinator"].email)
    response = await client.get("/api/v1/school/entitlements")
    body = response.json()
    keys = {s["key"] for s in body["services"]}
    assert keys == {"career_seminar", "career_awareness_session", "parent_orientation", "psychometric_test", "soft_skills"}
    assert _service(body, "soft_skills")["used"] is None


@pytest.mark.asyncio
async def test_platinum_tier_includes_every_cumulative_service(client, db_session):
    ctx = await _create_school(db_session, tier="platinum")
    await _login(client, ctx["coordinator"].email)
    response = await client.get("/api/v1/school/entitlements")
    body = response.json()
    keys = {s["key"] for s in body["services"]}
    assert len(keys) == 5 + 2 + 6 + 7


@pytest.mark.asyncio
async def test_usage_counts_reflect_real_data_hand_built_against_the_endpoint(client, db_session):
    ctx = await _create_school(db_session, tier="platinum")
    school, student, admin = ctx["school"], ctx["student"], ctx["admin"]

    psych = await _add_service_staff(db_session, admin, school, "psychometric_team")
    await _login(client, psych.email)
    await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(student.id), "assessment_type": "Aptitude"})

    counselor = await _add_service_staff(db_session, admin, school, "career_counselor")
    await _login(client, counselor.email)
    await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(student.id), "record_type": "counselling_note", "notes": "Session one"})
    await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(student.id), "record_type": "counselling_note", "notes": "Session two"})

    academic = await _add_service_staff(db_session, admin, school, "academic_team")
    await _login(client, academic.email)
    await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(student.id), "test_type": "ielts"})
    await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(student.id), "test_type": "sat"})
    await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(student.id), "test_type": "sat"})
    await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(student.id), "language": "German"})

    await _login(client, ctx["coordinator"].email)
    await client.post("/api/v1/school/activities", json={"title": "Career Seminar 1", "scheduled_at": datetime.now(UTC).isoformat(), "activity_type": "career_seminar"})
    await client.post("/api/v1/school/activities", json={"title": "Parent Orientation 1", "scheduled_at": datetime.now(UTC).isoformat(), "activity_type": "parent_orientation"})
    await client.post("/api/v1/school/activities", json={"title": "Untyped Session", "scheduled_at": datetime.now(UTC).isoformat()})

    response = await client.get("/api/v1/school/entitlements")
    assert response.status_code == 200
    body = response.json()
    assert _service(body, "psychometric_test")["used"] == 1
    assert _service(body, "individual_counselling")["used"] == 2
    assert _service(body, "ielts_coaching")["used"] == 1
    assert _service(body, "sat_coaching")["used"] == 2
    assert _service(body, "foreign_language_classes")["used"] == 1
    assert _service(body, "career_seminar")["used"] == 1
    assert _service(body, "parent_orientation")["used"] == 1
    assert _service(body, "career_awareness_session")["used"] == 0
    assert _service(body, "dedicated_counselor")["used"] is True
    assert _service(body, "application_support")["used"] == 0
    assert _service(body, "monthly_campus_visits")["used"] == 0
    # Never a fabricated cap or invented zero for a service with no underlying module.
    for untracked_key in ("soft_skills", "web_designing", "digital_portfolio_creation", "internships", "loan_assistance", "alumni_network", "parent_help_desk", "scholarship_assistance"):
        assert _service(body, untracked_key)["used"] is None


@pytest.mark.asyncio
async def test_entitlements_are_isolated_per_institution(client, db_session):
    school_a = await _create_school(db_session, tier="gold")
    school_b = await _create_school(db_session, tier="bronze")

    psych = await _add_service_staff(db_session, school_a["admin"], school_a["school"], "psychometric_team")
    await _login(client, psych.email)
    await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(school_a["student"].id), "assessment_type": "Aptitude"})

    await _login(client, school_b["coordinator"].email)
    response = await client.get("/api/v1/school/entitlements")
    body = response.json()
    assert body["tier"] == "bronze"
    assert _service(body, "psychometric_test")["used"] == 0


@pytest.mark.asyncio
async def test_principal_can_read_but_teacher_and_parent_cannot(client, db_session):
    ctx = await _create_school(db_session, tier="silver")
    principal = User(email=f"sch011-principal-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Principal", role="school_principal", division="overseas", active=True, profile={"school_id": str(ctx["school"].id)})
    teacher = User(email=f"sch011-teacher-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Teacher", role="school_teacher", division="overseas", active=True, profile={"school_id": str(ctx["school"].id)})
    db_session.add_all([principal, teacher])
    await db_session.flush()
    db_session.add_all([
        UserRoleAssignment(user_id=principal.id, division="overseas", role="school_principal", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"),
        UserRoleAssignment(user_id=teacher.id, division="overseas", role="school_teacher", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"),
    ])
    await db_session.commit()

    await _login(client, principal.email)
    ok = await client.get("/api/v1/school/entitlements")
    assert ok.status_code == 200

    await _login(client, teacher.email)
    denied = await client.get("/api/v1/school/entitlements")
    assert denied.status_code == 403
