"""SCH-005 -- Psychometric Assessment module.

Psychometric Team (new role) assigns psychometric assessments and uploads reports for
school-affiliated students in their own portfolio (`DEC-SCOPE-013`). School Coordinator
sees this content read-only, for their own institution only. Net-new.
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
    admin = User(email=f"sch005-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-005 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch005-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.flush()
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student}


async def _add_psychometric_team_member(db_session, admin, school) -> User:
    member = User(email=f"sch005-psych-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Psychometric Team Member", role="psychometric_team", division="overseas", active=True, profile={})
    db_session.add(member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role="psychometric_team", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role="psychometric_team", assigned_by_user_id=admin.id))
    await db_session.commit()
    return member


@pytest.mark.asyncio
async def test_psychometric_team_assigns_an_assessment(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_psychometric_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "Aptitude Test"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "assigned"


@pytest.mark.asyncio
async def test_uploading_a_report_marks_the_assessment_completed(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_psychometric_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "Personality Test"})
    record_id = created.json()["id"]
    assert created.json()["status"] == "assigned"

    updated = await client.patch(f"/api/v1/school/psychometric-team/records/{record_id}", json={"report_url": "/local-files/uploads/report.pdf"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_a_member_outside_the_students_portfolio_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    outsider = User(email=f"sch005-outsider-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Outsider", role="psychometric_team", division="overseas", active=True, profile={})
    db_session.add(outsider)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=outsider.id, division="overseas", role="psychometric_team", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, outsider.email)
    response = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "Should not save"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_reads_but_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_psychometric_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "Aptitude Test"})

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/psychometric-records")
    assert readable.status_code == 200
    assert len(readable.json()) == 1

    write_attempt = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "Not allowed"})
    assert write_attempt.status_code == 403


@pytest.mark.asyncio
async def test_non_psychometric_team_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student"].id), "assessment_type": "X"})
    assert response.status_code == 403
