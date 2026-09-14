"""SCH-001 -- School Portal role-based access (Principal/Coordinator/Teacher/Parent).

Each role logs in and sees/acts on only their own institution's data, further scoped per
role (Coordinator: whole institution write access; Teacher: assigned students only;
Parent: own child(ren) only; Principal: whole institution read-only). Net-new -- no
equivalent exists in the base codebase.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import School, SchoolParentLink, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_roles(db_session) -> dict:
    """Directly creates a School + one account of each School role (bypassing SCH-003's
    own onboarding endpoints, which are already covered by their own test file), scoped
    together, for SCH-001's own role-access tests."""
    admin = User(email=f"sch001-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-001 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()

    accounts = {}
    for role in ("school_coordinator", "school_principal", "school_teacher", "school_parent"):
        u = User(
            email=f"sch001-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
            full_name=f"Test {role}", role=role, division="overseas", active=True,
            profile={"school_id": str(school.id)},
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
        accounts[role] = u
    await db_session.commit()
    return {"admin": admin, "school": school, **accounts}


@pytest.mark.asyncio
async def test_coordinator_creates_a_student_scoped_to_their_own_school(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)

    response = await client.post("/api/v1/school/students", json={"full_name": "Test Student One", "grade_or_class": "Grade 5"})
    assert response.status_code == 201, response.text
    student_id = response.json()["id"]

    student = await db_session.get(SchoolStudent, uuid.UUID(student_id))
    assert student.school_id == ctx["school"].id
    assert student.created_by_user_id == ctx["school_coordinator"].id


@pytest.mark.asyncio
async def test_principal_teacher_parent_cannot_create_a_student(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    for role in ("school_principal", "school_teacher", "school_parent"):
        await _login(client, ctx[role].email)
        response = await client.post("/api/v1/school/students", json={"full_name": "Should Not Save"})
        assert response.status_code == 403, f"{role} should not be able to create a student"


@pytest.mark.asyncio
async def test_principal_sees_the_whole_institution_read_only(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    created = await client.post("/api/v1/school/students", json={"full_name": "Institution Student"})
    student_id = created.json()["id"]

    await _login(client, ctx["school_principal"].email)
    listed = await client.get("/api/v1/school/students")
    assert listed.status_code == 200
    assert any(s["id"] == student_id for s in listed.json())

    detail = await client.get(f"/api/v1/school/students/{student_id}")
    assert detail.status_code == 200

    edit = await client.patch(f"/api/v1/school/students/{student_id}", json={"full_name": "Hacked"})
    assert edit.status_code == 403


@pytest.mark.asyncio
async def test_teacher_sees_only_their_assigned_students_even_within_the_same_school(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    assigned = await client.post("/api/v1/school/students", json={"full_name": "Assigned Student", "assigned_teacher_email": ctx["school_teacher"].email})
    assert assigned.status_code == 201, assigned.text
    unassigned = await client.post("/api/v1/school/students", json={"full_name": "Unassigned Student"})
    assert unassigned.status_code == 201

    await _login(client, ctx["school_teacher"].email)
    listed = await client.get("/api/v1/school/students")
    ids = {s["id"] for s in listed.json()}
    assert assigned.json()["id"] in ids
    assert unassigned.json()["id"] not in ids

    # Direct-ID access to a student outside their assignment, even within the same school.
    detail = await client.get(f"/api/v1/school/students/{unassigned.json()['id']}")
    assert detail.status_code == 403


@pytest.mark.asyncio
async def test_parent_sees_only_their_own_linked_children(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    child = await client.post("/api/v1/school/students", json={"full_name": "My Child"})
    other = await client.post("/api/v1/school/students", json={"full_name": "Someone Else's Child"})
    link = await client.post(f"/api/v1/school/students/{child.json()['id']}/parents", json={"parent_email": ctx["school_parent"].email})
    assert link.status_code == 201, link.text

    await _login(client, ctx["school_parent"].email)
    listed = await client.get("/api/v1/school/students")
    ids = {s["id"] for s in listed.json()}
    assert child.json()["id"] in ids
    assert other.json()["id"] not in ids

    detail = await client.get(f"/api/v1/school/students/{other.json()['id']}")
    assert detail.status_code == 403


@pytest.mark.asyncio
async def test_no_role_sees_another_institutions_data_even_via_direct_record_id(client, db_session):
    ctx_a = await _create_school_with_roles(db_session)
    ctx_b = await _create_school_with_roles(db_session)
    await _login(client, ctx_b["school_coordinator"].email)
    b_student = await client.post("/api/v1/school/students", json={"full_name": "School B Student"})
    assert b_student.status_code == 201

    for role in ("school_coordinator", "school_principal"):
        await _login(client, ctx_a[role].email)
        listed = await client.get("/api/v1/school/students")
        assert b_student.json()["id"] not in {s["id"] for s in listed.json()}
        detail = await client.get(f"/api/v1/school/students/{b_student.json()['id']}")
        assert detail.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_schedules_activity_and_marks_attendance(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    student = await client.post("/api/v1/school/students", json={"full_name": "Attendance Student"})

    activity = await client.post("/api/v1/school/activities", json={"title": "Sports Day", "scheduled_at": "2027-01-15T09:00:00+00:00"})
    assert activity.status_code == 201, activity.text

    marked = await client.post(f"/api/v1/school/activities/{activity.json()['id']}/attendance", json={"records": [{"student_id": student.json()["id"], "present": True}]})
    assert marked.status_code == 200
    assert marked.json()["marked"] == 1


@pytest.mark.asyncio
async def test_attendance_rejects_a_student_from_another_institution(client, db_session):
    ctx_a = await _create_school_with_roles(db_session)
    ctx_b = await _create_school_with_roles(db_session)
    await _login(client, ctx_b["school_coordinator"].email)
    other_student = await client.post("/api/v1/school/students", json={"full_name": "Not Yours"})

    await _login(client, ctx_a["school_coordinator"].email)
    activity = await client.post("/api/v1/school/activities", json={"title": "Field Trip", "scheduled_at": "2027-02-01T09:00:00+00:00"})
    marked = await client.post(f"/api/v1/school/activities/{activity.json()['id']}/attendance", json={"records": [{"student_id": other_student.json()["id"], "present": True}]})
    assert marked.status_code == 422


@pytest.mark.asyncio
async def test_school_teacher_role_never_reachable_through_trainer_permission_check(client, db_session):
    """SCH-001-AC05: role-name collision guard."""
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_teacher"].email)
    # A `trainer`-scoped endpoint must reject a school_teacher, even though both role
    # names contain "teacher"-adjacent meaning -- they are unrelated role identifiers.
    response = await client.get("/api/v1/portal/it/trainer/dashboard")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client):
    response = await client.get("/api/v1/school/dashboard")
    assert response.status_code == 401
