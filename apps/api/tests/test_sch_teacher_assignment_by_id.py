"""SCH-001 addendum -- assigning a Teacher to a student by `assigned_teacher_user_id`
(a live picker, apps/web/components/SchoolStudentsPanel.tsx), alongside the original
`assigned_teacher_email` field kept for SCH-002's bulk-upload CSV path. The id field
takes precedence when both are supplied.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import School, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_roles(db_session) -> dict:
    admin = User(email=f"sch-tid-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH Teacher-ID Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()

    accounts = {}
    for role in ("school_coordinator", "school_principal", "school_teacher", "school_parent"):
        u = User(
            email=f"sch-tid-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
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
async def test_create_student_assigns_teacher_by_id(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    created = await client.post("/api/v1/school/students", json={"full_name": "Picker Student", "assigned_teacher_user_id": str(teacher.id)})
    assert created.status_code == 201, created.text

    student = await db_session.get(SchoolStudent, uuid.UUID(created.json()["id"]))
    assert student.assigned_teacher_user_id == teacher.id


@pytest.mark.asyncio
async def test_create_student_rejects_teacher_id_from_another_school(client, db_session):
    ctx_a = await _create_school_with_roles(db_session)
    ctx_b = await _create_school_with_roles(db_session)
    await _login(client, ctx_a["school_coordinator"].email)

    response = await client.post("/api/v1/school/students", json={"full_name": "Cross-School Student", "assigned_teacher_user_id": str(ctx_b["school_teacher"].id)})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_student_rejects_teacher_id_of_wrong_role(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)

    response = await client.post("/api/v1/school/students", json={"full_name": "Wrong Role Student", "assigned_teacher_user_id": str(ctx["school_principal"].id)})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_student_reassigns_teacher_by_id(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    created = await client.post("/api/v1/school/students", json={"full_name": "Reassign Student"})
    student_id = created.json()["id"]

    updated = await client.patch(f"/api/v1/school/students/{student_id}", json={"assigned_teacher_user_id": str(ctx["school_teacher"].id)})
    assert updated.status_code == 200, updated.text

    student = await db_session.get(SchoolStudent, uuid.UUID(student_id))
    await db_session.refresh(student)
    assert student.assigned_teacher_user_id == ctx["school_teacher"].id

    cleared = await client.patch(f"/api/v1/school/students/{student_id}", json={"assigned_teacher_user_id": None})
    assert cleared.status_code == 200
    await db_session.refresh(student)
    assert student.assigned_teacher_user_id is None


@pytest.mark.asyncio
async def test_assigned_teacher_email_still_works_back_compat(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    created = await client.post("/api/v1/school/students", json={"full_name": "Email Path Student", "assigned_teacher_email": teacher.email})
    assert created.status_code == 201, created.text
    student = await db_session.get(SchoolStudent, uuid.UUID(created.json()["id"]))
    assert student.assigned_teacher_user_id == teacher.id


@pytest.mark.asyncio
async def test_teacher_id_takes_precedence_when_both_supplied(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]
    # A second teacher whose email is deliberately wrong/unresolvable -- if the id field
    # weren't taking precedence, this request would 422 on the bad email instead of
    # succeeding via the valid id.
    created = await client.post(
        "/api/v1/school/students",
        json={"full_name": "Precedence Student", "assigned_teacher_user_id": str(teacher.id), "assigned_teacher_email": "not-a-real-teacher@example.local"},
    )
    assert created.status_code == 201, created.text
    student = await db_session.get(SchoolStudent, uuid.UUID(created.json()["id"]))
    assert student.assigned_teacher_user_id == teacher.id
