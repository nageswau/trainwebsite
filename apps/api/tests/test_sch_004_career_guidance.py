"""SCH-004 -- Career Guidance & Counselling module.

Career Counselor (new role) conducts career guidance sessions, adds counselling notes, and
uploads recommendations for school-affiliated students in their own portfolio
(`DEC-SCOPE-013`). School Coordinator sees this content read-only, for their own
institution only. No Draft/Published gate -- visible as soon as it's created. Net-new.
"""

import uuid

import pytest

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import School, SchoolStaffAssignment, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session) -> dict:
    admin = User(email=f"sch004-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-004 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id, tier="platinum")  # ENH-022: entitled to every service
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch004-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.flush()
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student}


async def _add_career_counselor(db_session, admin, school) -> User:
    member = User(email=f"sch004-counselor-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Career Counselor", role="career_counselor", division="overseas", active=True, profile={})
    db_session.add(member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role="career_counselor", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role="career_counselor", assigned_by_user_id=admin.id))
    await db_session.commit()
    return member


@pytest.mark.asyncio
async def test_career_counselor_adds_a_guidance_session(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_career_counselor(db_session, ctx["admin"], ctx["school"])
    await _login(client, counselor.email)
    response = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student"].id), "record_type": "guidance_session", "notes": "Discussed engineering career paths."})
    assert response.status_code == 201, response.text
    assert response.json()["record_type"] == "guidance_session"


@pytest.mark.asyncio
async def test_a_counselor_outside_the_students_portfolio_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    outsider = User(email=f"sch004-outsider-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Outsider", role="career_counselor", division="overseas", active=True, profile={})
    db_session.add(outsider)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=outsider.id, division="overseas", role="career_counselor", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, outsider.email)
    response = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student"].id), "record_type": "guidance_session", "notes": "Should not save."})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_reads_the_record_but_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_career_counselor(db_session, ctx["admin"], ctx["school"])
    await _login(client, counselor.email)
    await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student"].id), "record_type": "counselling_note", "notes": "Follow-up needed."})

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/career-records")
    assert readable.status_code == 200
    assert len(readable.json()) == 1

    write_attempt = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student"].id), "record_type": "guidance_session", "notes": "Not allowed."})
    assert write_attempt.status_code == 403


@pytest.mark.asyncio
async def test_an_unsupported_record_type_is_rejected(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    counselor = await _add_career_counselor(db_session, ctx["admin"], ctx["school"])
    await _login(client, counselor.email)
    response = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student"].id), "record_type": "not_a_real_type", "notes": "X"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_coordinator_never_sees_another_schools_career_records(client, db_session):
    ctx_a = await _create_school_with_coordinator(db_session)
    ctx_b = await _create_school_with_coordinator(db_session)
    counselor_b = await _add_career_counselor(db_session, ctx_b["admin"], ctx_b["school"])
    await _login(client, counselor_b.email)
    await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx_b["student"].id), "record_type": "recommendation", "notes": "B's record."})

    await _login(client, ctx_a["coordinator"].email)
    readable = await client.get("/api/v1/school/career-records")
    assert readable.status_code == 200
    assert readable.json() == []
