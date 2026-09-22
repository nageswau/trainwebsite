"""SCH-003 -- School partner onboarding (Admin-created, Coordinator-seeded invites).

Overseas Admin creates a School partner record and a seed School Coordinator account
for it, both active immediately (DEC-SCOPE-012). The Coordinator then invites Principal/
Teacher/Parent accounts for the same institution, also active immediately. Net-new --
no equivalent exists anywhere in the base codebase.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import School, SchoolAccountInvite, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _create_overseas_admin(db_session) -> User:
    admin = User(
        email=f"sch003-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school(client, db_session, *, suffix: str | None = None) -> dict:
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    suffix = suffix or uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": f"Test School {suffix}",
            "city": "Testville",
            "coordinator_full_name": "Test Coordinator",
            "coordinator_email": f"sch003-coord-{suffix}@example.local",
        },
    )
    assert response.status_code == 201
    data = response.json()
    # ENH-003: the Coordinator sets their own password from the welcome link (dev/test token).
    activation = await client.post("/api/v1/auth/reset-password", json={"token": data["development_welcome_token"], "new_password": PASSWORD})
    assert activation.status_code == 200
    return {"admin": admin, **data}


@pytest.mark.asyncio
async def test_overseas_admin_creates_school_and_seed_coordinator_active_immediately(client, db_session):
    result = await _create_school(client, db_session)

    school = await db_session.get(School, result["id"])
    assert school is not None
    assert school.created_by_user_id == result["admin"].id

    coordinator = await db_session.get(User, result["coordinator_id"])
    assert coordinator.role == "school_coordinator"
    assert coordinator.active is True
    assert coordinator.profile["school_id"] == str(school.id)

    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == coordinator.id))
    assert assignment.approval_status == "approved"
    assert assignment.assigned_by_user_id == result["admin"].id

    # No activation gate: the Coordinator can log in and reach /school/team immediately.
    await _login(client, coordinator.email)
    team = await client.get("/api/v1/school/team")
    assert team.status_code == 200
    assert team.json()["pending_invites"] == []
    assert {a["email"] for a in team.json()["accounts"]} == {coordinator.email}


@pytest.mark.asyncio
async def test_non_admin_role_cannot_create_a_school(client, db_session):
    result = await _create_school(client, db_session)
    # A School Coordinator (not an Overseas Admin) attempting to create another school.
    coordinator = await db_session.get(User, result["coordinator_id"])
    coordinator.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await _login(client, coordinator.email)
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": "Rogue School", "coordinator_full_name": "X", "coordinator_email": f"rogue-{uuid.uuid4().hex[:8]}@example.local"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_school_creation_requires_authentication(client):
    response = await client.post("/api/v1/overseas-admin/schools", json={"name": "X", "coordinator_full_name": "Y", "coordinator_email": "z@example.local"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_coordinator_invites_principal_teacher_parent(client, db_session):
    result = await _create_school(client, db_session)
    coordinator = await db_session.get(User, result["coordinator_id"])
    coordinator.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await _login(client, coordinator.email)

    for role in ("school_principal", "school_teacher", "school_parent"):
        suffix = uuid.uuid4().hex[:8]
        response = await client.post(
            "/api/v1/school/team/invites",
            json={"role": role, "full_name": f"Test {role}", "email": f"sch003-{role}-{suffix}@example.local"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["role"] == role

    team = await client.get("/api/v1/school/team")
    assert team.status_code == 200
    assert len(team.json()["pending_invites"]) == 3


@pytest.mark.asyncio
async def test_invite_rejects_an_unsupported_role(client, db_session):
    result = await _create_school(client, db_session)
    coordinator = await db_session.get(User, result["coordinator_id"])
    coordinator.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await _login(client, coordinator.email)

    response = await client.post("/api/v1/school/team/invites", json={"role": "school_coordinator", "full_name": "X", "email": "x@example.local"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invite_accept_creates_the_account_scoped_to_the_inviting_school(client, db_session):
    result = await _create_school(client, db_session)
    coordinator = await db_session.get(User, result["coordinator_id"])
    coordinator.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await _login(client, coordinator.email)

    email = f"sch003-principal-{uuid.uuid4().hex[:8]}@example.local"
    invite_response = await client.post("/api/v1/school/team/invites", json={"role": "school_principal", "full_name": "Test Principal", "email": email})
    assert invite_response.status_code == 201
    raw_token = invite_response.json()["development_invite_token"]

    accept_response = await client.post(f"/api/v1/school/invites/{raw_token}/accept", json={"password": PASSWORD})
    assert accept_response.status_code == 201, accept_response.text
    account_id = accept_response.json()["id"]

    account = await db_session.get(User, uuid.UUID(account_id))
    assert account.role == "school_principal"
    assert account.profile["school_id"] == str(result["id"])
    assert account.email == email

    invite = await db_session.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.email == email))
    assert invite.status == "accepted"
    assert invite.accepted_by_user_id == account.id

    # `accept_invite` logs the new Principal in (SCR-SCH-013's "one step" design) --
    # re-authenticate as the Coordinator to check the team roster reflects the new member.
    await _login(client, coordinator.email)
    team = await client.get("/api/v1/school/team")
    names = [a["email"] for a in team.json()["accounts"]]
    assert email in names


@pytest.mark.asyncio
async def test_a_consumed_invite_token_cannot_be_accepted_again(client, db_session):
    result = await _create_school(client, db_session)
    coordinator = await db_session.get(User, result["coordinator_id"])
    coordinator.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await _login(client, coordinator.email)

    email = f"sch003-teacher-{uuid.uuid4().hex[:8]}@example.local"
    invite_response = await client.post("/api/v1/school/team/invites", json={"role": "school_teacher", "full_name": "Test Teacher", "email": email})
    raw_token = invite_response.json()["development_invite_token"]

    first = await client.post(f"/api/v1/school/invites/{raw_token}/accept", json={"password": PASSWORD})
    assert first.status_code == 201

    second = await client.post(f"/api/v1/school/invites/{raw_token}/accept", json={"password": PASSWORD})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_non_coordinator_cannot_invite(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post("/api/v1/school/team/invites", json={"role": "school_teacher", "full_name": "X", "email": "x@example.local"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_coordinator_never_sees_another_schools_team(client, db_session):
    result_a = await _create_school(client, db_session)
    result_b = await _create_school(client, db_session)
    coordinator_a = await db_session.get(User, result_a["coordinator_id"])
    coordinator_a.password_hash = hash_password(PASSWORD)
    coordinator_b = await db_session.get(User, result_b["coordinator_id"])
    coordinator_b.password_hash = hash_password(PASSWORD)
    await db_session.commit()

    await _login(client, coordinator_b.email)
    teacher_b_email = f"sch003-b-teacher-{uuid.uuid4().hex[:8]}@example.local"
    await client.post("/api/v1/school/team/invites", json={"role": "school_teacher", "full_name": "B's Teacher", "email": teacher_b_email})

    await _login(client, coordinator_a.email)
    team_a = await client.get("/api/v1/school/team")
    data = team_a.json()
    # Coordinator A legitimately sees themself (a school_coordinator account scoped to
    # their own school), but never school B's pending invite or any school B account.
    assert data["pending_invites"] == []
    assert teacher_b_email not in [a["email"] for a in data["accounts"]]
    assert {a["email"] for a in data["accounts"]} == {coordinator_a.email}


@pytest.mark.asyncio
async def test_list_schools_includes_school_code_and_profile_fields(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"List Test {uuid.uuid4().hex[:8]}", "coordinator_full_name": "C",
              "coordinator_email": f"list-{uuid.uuid4().hex[:8]}@example.local", "branch": "East Wing"},
    )
    response = await client.get("/api/v1/overseas-admin/schools")
    assert response.status_code == 200
    row = response.json()[0]
    assert "school_code" in row
    assert "branch" in row
    assert "student_count" in row


@pytest.mark.asyncio
async def test_school_table_has_the_new_profile_columns(db_session):
    from sqlalchemy import text

    row = await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'schools' AND column_name = ANY(:cols)"
    ), {"cols": [
        "school_code", "branch", "address", "contact_number", "email", "website",
        "grades_available", "board", "partnership_date", "mou_reference",
        "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name",
    ]})
    found = {r[0] for r in row.fetchall()}
    assert found == {
        "school_code", "branch", "address", "contact_number", "email", "website",
        "grades_available", "board", "partnership_date", "mou_reference",
        "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name",
    }


@pytest.mark.asyncio
async def test_school_model_exposes_the_new_profile_attributes(db_session):
    suffix = uuid.uuid4().hex[:4]
    admin = User(
        email=f"test-admin-{suffix}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name="Test Admin",
        role="overseas_admin",
        division="overseas",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    school = School(
        name="Attr Test School", created_by_user_id=admin.id,
        school_code=f"TST{suffix}", branch="North Campus", address="1 Test Rd",
        contact_number="+91-9000000000", email="school@example.local",
        website="https://example.local", grades_available="1-10", board="CBSE",
        mou_reference="MOU-2026-001", edusphere_bdm="Jane BDM",
        monthly_visit_schedule="2nd Tuesday monthly", vice_principal_name="John VP",
    )
    db_session.add(school)
    await db_session.commit()
    reloaded = await db_session.get(School, school.id)
    assert reloaded.school_code == f"TST{suffix}"
    assert reloaded.branch == "North Campus"
    assert reloaded.board == "CBSE"
    assert reloaded.vice_principal_name == "John VP"


@pytest.mark.asyncio
async def test_school_out_computes_counts_and_role_derived_names(client, db_session):
    from app.api.admin import _school_out
    from app.core.identifiers import unique_student_code
    from app.models import SchoolStaffAssignment, SchoolStudent

    result = await _create_school(client, db_session)
    school = await db_session.get(School, result["id"])

    principal = User(
        email=f"vp-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Principal", role="school_principal", division="overseas", active=True,
        profile={"school_id": str(school.id)},
    )
    counsellor = User(
        email=f"cc-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Counsellor", role="career_counselor", division="overseas", active=True,
    )
    db_session.add_all([principal, counsellor])
    await db_session.flush()
    db_session.add(SchoolStaffAssignment(user_id=counsellor.id, school_id=school.id, role="career_counselor", assigned_by_user_id=result["admin"].id))
    db_session.add(SchoolStudent(
        school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code),
        full_name="A Student", grade_level=5, created_by_user_id=result["admin"].id,
    ))
    await db_session.commit()

    out = await _school_out(db_session, school)
    assert out.student_count == 1
    assert out.teacher_count == 0
    assert out.principal_name == "Test Principal"
    assert out.school_coordinator_name is not None  # the seed Coordinator from _create_school
    assert out.career_counsellor_names == ["Test Counsellor"]


@pytest.mark.asyncio
async def test_create_school_generates_a_unique_school_code_and_stores_new_fields(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": f"Full Profile School {suffix}", "city": "Testville",
            "coordinator_full_name": "Test Coordinator",
            "coordinator_email": f"sch009-coord-{suffix}@example.local",
            "branch": "North Campus", "address": "1 Test Road", "board": "CBSE",
            # NOTE: SchoolCreate.email is typed `EmailStr` (Task 3), which rejects the
            # `.local` TLD this suite otherwise uses everywhere else (see LoginRequest's
            # comment in schemas.py -- it deliberately avoids EmailStr for that exact
            # reason). `coordinator_email` above is a plain `str` field so `.local` is
            # fine there; this one field needs a non-reserved domain to pass validation.
            "email": "school-contact@example.com", "grades_available": "1-10",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["school_code"] is not None
    assert len(data["school_code"]) == 8

    school = await db_session.get(School, data["id"])
    assert school.branch == "North Campus"
    assert school.address == "1 Test Road"
    assert school.board == "CBSE"
    assert school.email == "school-contact@example.com"


@pytest.mark.asyncio
async def test_create_school_rejects_an_invalid_board_value(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": "X", "coordinator_full_name": "Y",
            "coordinator_email": f"y-{uuid.uuid4().hex[:8]}@example.local",
            "board": "Cambridge",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_school_rejects_a_smuggled_role_field(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": "X", "coordinator_full_name": "Y",
            "coordinator_email": f"y-{uuid.uuid4().hex[:8]}@example.local",
            "role": "super_admin",
        },
    )
    assert response.status_code == 422
