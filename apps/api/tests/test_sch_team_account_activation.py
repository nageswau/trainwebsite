"""SCH-003 addendum -- Coordinator activate/deactivate for their own school's
Principal/Teacher/Parent accounts (EVID-014 "School Master" capability, treated as the
same role as school_coordinator per direct user confirmation). Deliberately no cascade
guard like ADM-001-AC02's trainer/batch check -- see the endpoint's own docstring.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, School, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_roles(db_session) -> dict:
    admin = User(email=f"sch-team-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH Team Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()

    accounts = {}
    for role in ("school_coordinator", "school_principal", "school_teacher", "school_parent"):
        u = User(
            email=f"sch-team-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
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
async def test_coordinator_deactivates_and_reactivates_a_teacher(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    deactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": False})
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["active"] is False

    audit_rows = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "school.team_account_update", AuditLog.entity_id == str(teacher.id))
        )
    ).all()
    assert len(audit_rows) >= 1
    assert audit_rows[0].user_id == ctx["school_coordinator"].id
    assert audit_rows[0].entity_id == str(teacher.id)
    assert audit_rows[0].created_at is not None

    listed = await client.get("/api/v1/school/team")
    row = next(a for a in listed.json()["accounts"] if a["id"] == str(teacher.id))
    assert row["active"] is False

    reactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": True})
    assert reactivated.status_code == 200
    assert reactivated.json()["active"] is True


@pytest.mark.asyncio
async def test_deactivated_teacher_cannot_log_in_and_reactivation_restores_access(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    deactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": False})
    assert deactivated.status_code == 200

    blocked = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
    assert blocked.status_code == 401

    reactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": True})
    assert reactivated.status_code == 200

    restored = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
    assert restored.status_code == 200


@pytest.mark.asyncio
async def test_coordinator_cannot_toggle_another_schools_account(client, db_session):
    ctx_a = await _create_school_with_roles(db_session)
    ctx_b = await _create_school_with_roles(db_session)
    await _login(client, ctx_a["school_coordinator"].email)

    response = await client.patch(f"/api/v1/school/team/accounts/{ctx_b['school_teacher'].id}", json={"active": False})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_cannot_toggle_a_coordinator_account(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)

    self_toggle = await client.patch(f"/api/v1/school/team/accounts/{ctx['school_coordinator'].id}", json={"active": False})
    assert self_toggle.status_code == 403


@pytest.mark.asyncio
async def test_non_coordinator_cannot_toggle_team_accounts(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    for role in ("school_principal", "school_teacher", "school_parent"):
        await _login(client, ctx[role].email)
        response = await client.patch(f"/api/v1/school/team/accounts/{ctx['school_teacher'].id}", json={"active": False})
        assert response.status_code == 403, f"{role} should not be able to toggle a team account"


@pytest.mark.asyncio
async def test_deactivating_a_teacher_leaves_existing_student_assignment_unchanged(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]
    created = await client.post("/api/v1/school/students", json={"full_name": "Still Assigned Student", "assigned_teacher_user_id": str(teacher.id)})
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]

    deactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": False})
    assert deactivated.status_code == 200

    student = await db_session.get(SchoolStudent, uuid.UUID(student_id))
    await db_session.refresh(student)
    assert student.assigned_teacher_user_id == teacher.id


@pytest.mark.asyncio
async def test_toggle_rejects_missing_or_non_boolean_active(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    missing = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={})
    assert missing.status_code == 422

    wrong_type = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": "false"})
    assert wrong_type.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_cannot_toggle_team_account(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    response = await client.patch(f"/api/v1/school/team/accounts/{ctx['school_teacher'].id}", json={"active": False})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_toggle_ignores_extra_fields_and_changes_only_active(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]
    original = (teacher.role, teacher.division, teacher.email, teacher.full_name, teacher.password_hash)

    response = await client.patch(
        f"/api/v1/school/team/accounts/{teacher.id}",
        json={
            "active": False,
            "role": "super_admin",
            "division": "global",
            "email": "attacker@example.local",
            "full_name": "Hacked",
            "password_hash": "x",
        },
    )
    assert response.status_code == 200

    await db_session.refresh(teacher)
    assert (teacher.role, teacher.division, teacher.email, teacher.full_name, teacher.password_hash) == original
    assert teacher.active is False
