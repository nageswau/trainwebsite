"""SCH-004/005/006 provisioning -- Overseas Admin/Super Admin creates an academic_team/
career_counselor/psychometric_team account and assigns its school portfolio
(`DEC-SCOPE-014`), a separate path from SCH-003's SchoolAccountInvite flow.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import School, SchoolStaffAssignment, User

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_admin_and_schools(db_session, count: int = 1) -> dict:
    admin = User(email=f"schstaff-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    schools = []
    for _ in range(count):
        school = School(name=f"Staff Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
        db_session.add(school)
        schools.append(school)
    await db_session.flush()
    await db_session.commit()
    return {"admin": admin, "schools": schools}


@pytest.mark.asyncio
async def test_overseas_admin_creates_an_academic_team_account_with_a_portfolio(client, db_session):
    ctx = await _create_admin_and_schools(db_session, count=2)
    await _login(client, ctx["admin"].email)
    school_ids = [str(s.id) for s in ctx["schools"]]
    response = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "academic_team", "full_name": "New Academic Team Member", "email": f"schstaff-{uuid.uuid4().hex[:8]}@example.local", "school_ids": school_ids})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["role"] == "academic_team"
    assert set(data["school_ids"]) == set(school_ids)

    assignments = (await db_session.scalars(select(SchoolStaffAssignment).where(SchoolStaffAssignment.user_id == uuid.UUID(data["id"])))).all()
    assert len(assignments) == 2


@pytest.mark.asyncio
async def test_school_coordinator_cannot_create_specialized_role_accounts(client, db_session):
    ctx = await _create_admin_and_schools(db_session)
    coordinator = User(email=f"schstaff-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(ctx["schools"][0].id)})
    db_session.add(coordinator)
    await db_session.commit()
    await _login(client, coordinator.email)
    response = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "academic_team", "full_name": "X", "email": f"x-{uuid.uuid4().hex[:8]}@example.local", "school_ids": []})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unsupported_role_is_rejected(client, db_session):
    ctx = await _create_admin_and_schools(db_session)
    await _login(client, ctx["admin"].email)
    response = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "school_coordinator", "full_name": "X", "email": f"x-{uuid.uuid4().hex[:8]}@example.local", "school_ids": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_adds_a_school_to_an_existing_members_portfolio(client, db_session):
    ctx = await _create_admin_and_schools(db_session, count=2)
    await _login(client, ctx["admin"].email)
    created = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "career_counselor", "full_name": "Counselor", "email": f"schstaff-{uuid.uuid4().hex[:8]}@example.local", "school_ids": [str(ctx["schools"][0].id)]})
    staff_id = created.json()["id"]

    added = await client.post(f"/api/v1/overseas-admin/school-staff/{staff_id}/portfolio", json={"school_id": str(ctx["schools"][1].id)})
    assert added.status_code == 200

    listed = await client.get("/api/v1/overseas-admin/school-staff")
    assert listed.status_code == 200
    entry = next(e for e in listed.json() if e["id"] == staff_id)
    assert len(entry["school_ids"]) == 2
