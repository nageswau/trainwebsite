"""SCH-003 -- School partner onboarding (Admin-created, Coordinator-seeded invites).

Overseas Admin creates a School partner record and a seed School Coordinator account
for it, both active immediately (DEC-SCOPE-012). The Coordinator then invites Principal/
Teacher/Parent accounts for the same institution, also active immediately. Net-new --
no equivalent exists anywhere in the base codebase.
"""

import importlib.util
import pathlib
import uuid
from datetime import date

import pytest
from sqlalchemy import event, select

from app.core.database import engine
from app.core.security import hash_password
from app.models import School, SchoolAccountInvite, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


def _load_backfill_migration():
    """0036 lives outside any importable package (alembic/versions is a script directory),
    so it is loaded by path -- the same way alembic itself loads it."""
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0036_backfill_school_code.py"
    spec = importlib.util.spec_from_file_location("migration_0036_backfill_school_code", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


@pytest.mark.asyncio
async def test_patch_school_updates_profile_fields_and_logs_changed_field_names_only(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)

    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"branch": "South Campus", "board": "ICSE", "email": "new-contact@example.local"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["branch"] == "South Campus"
    assert response.json()["board"] == "ICSE"

    school = await db_session.get(School, result["id"])
    assert school.branch == "South Campus"
    assert school.email == "new-contact@example.local"

    from app.models import AuditLog
    log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(school.id))
    )
    assert log is not None
    assert set(log.metadata_json["changed_fields"]) == {"branch", "board", "email"}
    # field names only -- the actual new values are never written into the audit trail
    assert "South Campus" not in str(log.metadata_json)


@pytest.mark.asyncio
async def test_patch_school_tier_only_still_works_unchanged(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)
    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"tier": "gold", "tier_valid_until": "2027-01-01"},
    )
    assert response.status_code == 200
    assert response.json()["tier"] == "gold"

    from app.models import AuditLog
    tier_log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "school.tier_update", AuditLog.entity_id == result["id"])
    )
    assert tier_log is not None
    assert tier_log.metadata_json == {"tier": "gold"}


@pytest.mark.asyncio
async def test_patch_school_with_tier_and_profile_fields_logs_both_audit_rows(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)

    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"tier": "silver", "branch": "New Branch"},
    )
    assert response.status_code == 200, response.text

    school = await db_session.get(School, result["id"])

    from app.models import AuditLog
    tier_logs = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "school.tier_update", AuditLog.entity_id == str(school.id))
    )).all()
    assert len(tier_logs) == 1
    assert tier_logs[0].metadata_json == {"tier": "silver"}

    profile_logs = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(school.id))
    )).all()
    assert len(profile_logs) == 1
    assert profile_logs[0].metadata_json == {"changed_fields": ["branch"]}


@pytest.mark.asyncio
async def test_patch_school_profile_only_logs_zero_tier_update_rows(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)

    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"branch": "X"},
    )
    assert response.status_code == 200, response.text

    school = await db_session.get(School, result["id"])

    from app.models import AuditLog
    tier_logs = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "school.tier_update", AuditLog.entity_id == str(school.id))
    )).all()
    assert tier_logs == []

    profile_log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(school.id))
    )
    assert profile_log is not None
    assert profile_log.metadata_json == {"changed_fields": ["branch"]}


@pytest.mark.asyncio
async def test_lookup_school_by_code_returns_the_school(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)
    school = await db_session.get(School, result["id"])

    response = await client.get(f"/api/v1/overseas-admin/schools/lookup?code={school.school_code}")
    assert response.status_code == 200
    assert response.json()["id"] == str(school.id)


@pytest.mark.asyncio
async def test_lookup_school_by_code_404_when_not_found(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.get("/api/v1/overseas-admin/schools/lookup?code=ZZZZZZZZ")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_schools_query_count_does_not_scale_with_the_number_of_schools(client, db_session):
    """ENH-009 final review: `GET /overseas-admin/schools` is unpaginated and used to call
    the 5-query `_school_out()` once per row, so N schools meant 5N queries. Proof of the
    batched fix -- the statement count for one list call is unchanged after 3 more schools
    exist (a linear implementation would have grown it by 15)."""
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    async def _statements_for_one_list_call() -> int:
        statements.clear()
        event.listen(engine.sync_engine, "before_cursor_execute", _record)
        try:
            response = await client.get("/api/v1/overseas-admin/schools")
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _record)
        assert response.status_code == 200
        return len(statements)

    before_count = await _statements_for_one_list_call()
    schools_before = len((await client.get("/api/v1/overseas-admin/schools")).json())

    for _ in range(3):
        await _create_school(client, db_session)
    await _login(client, admin.email)

    after_count = await _statements_for_one_list_call()
    schools_after = len((await client.get("/api/v1/overseas-admin/schools")).json())

    assert schools_after == schools_before + 3  # the list really did grow
    assert after_count == before_count  # ... but the query count did not
    assert before_count < 10, statements  # and it is a small constant, not O(N)


@pytest.mark.asyncio
async def test_create_school_accepts_tier_valid_until(client, db_session):
    """ENH-009 final review: the pre-ENH-009 dict-bodied create_school() accepted
    `tier_valid_until`; `SchoolCreate` silently dropped it. Restored so the request shape
    really is additive-compatible with existing callers, as the design doc claims."""
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": f"Tier School {suffix}",
            "coordinator_full_name": "Test Coordinator",
            "coordinator_email": f"sch003-tvu-{suffix}@example.local",
            "tier": "gold",
            "tier_valid_until": "2027-06-30",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["tier_valid_until"] == "2027-06-30"

    school = await db_session.get(School, response.json()["id"])
    assert school.tier_valid_until == date(2027, 6, 30)


def test_backfill_migration_0036_generates_unique_eight_character_codes():
    """ENH-009 final review, Fix 5. Unit-level proof of `0036_backfill_school_code`'s code
    generator: every code is a non-null 8-char uppercase-hex value and never collides with
    one already taken. Full end-to-end replay of the backfill would need a fresh
    un-migrated database (the test database is already at head), which this suite has no
    harness for -- the DB-side half is covered by the test below."""
    module = _load_backfill_migration()
    assert module.revision == "0036_backfill_school_code"
    assert module.down_revision == "0035_school_profile_fields"

    taken: set[str] = set()
    for _ in range(50):
        code = module._generate_code(taken)
        assert code not in taken
        assert len(code) == 8
        assert all(character in "0123456789ABCDEF" for character in code)
        taken.add(code)
    assert len(taken) == 50


@pytest.mark.asyncio
async def test_a_pre_existing_school_row_has_a_null_code_that_0036_would_backfill(client, db_session):
    """The other half of Fix 5: a School created outside `create_school()` -- i.e. every row
    that predates the 0035 migration, including all seed data -- really does have
    `school_code IS NULL`, matches the exact predicate 0036's `upgrade()` selects on, and
    accepts the generated code."""
    module = _load_backfill_migration()
    admin = await _create_overseas_admin(db_session)
    school = School(name=f"Legacy School {uuid.uuid4().hex[:8]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.commit()
    assert school.school_code is None

    selected = await db_session.scalar(
        select(School.id).where(School.id == school.id, School.school_code.is_(None))
    )
    assert selected == school.id

    existing = set((await db_session.scalars(select(School.school_code).where(School.school_code.is_not(None)))).all())
    code = module._generate_code(existing)
    school.school_code = code
    await db_session.commit()

    await db_session.refresh(school)
    assert school.school_code == code

    # and the backfilled row is now reachable by the edit panel's lookup-by-code flow
    await _login(client, admin.email)
    response = await client.get(f"/api/v1/overseas-admin/schools/lookup?code={code}")
    assert response.status_code == 200
    assert response.json()["id"] == str(school.id)


@pytest.mark.asyncio
async def test_lookup_school_by_code_excludes_counselor(client, db_session):
    result = await _create_school(client, db_session)
    counselor = User(
        email=f"counselor-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Counselor", role="counselor", division="overseas", active=True,
    )
    db_session.add(counselor)
    await db_session.commit()
    await _login(client, counselor.email)
    school = await db_session.get(School, result["id"])
    response = await client.get(f"/api/v1/overseas-admin/schools/lookup?code={school.school_code}")
    assert response.status_code == 403
