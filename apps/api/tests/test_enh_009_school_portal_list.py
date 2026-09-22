"""ENH-009 / DEC-SCOPE-025 -- the existing read-only Partner Schools portal list gains
school_code/branch/board/tier columns (the acceptance criterion that School ID must be displayed
everywhere a school is currently identified only by name)."""

import uuid

import pytest

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"


@pytest.mark.asyncio
async def test_overseas_admin_schools_portal_section_includes_school_code_and_branch(client, db_session):
    admin = User(
        email=f"portal-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Portal Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    login = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD, "division": "overseas"})
    assert login.status_code == 200

    await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"Portal School {uuid.uuid4().hex[:8]}", "coordinator_full_name": "C",
              "coordinator_email": f"portal-{uuid.uuid4().hex[:8]}@example.local", "branch": "West Wing"},
    )

    response = await client.get("/api/v1/portal/overseas/admin/schools")
    assert response.status_code == 200
    payload = response.json()
    column_keys = {c["key"] for c in payload["columns"]}
    assert {"school_code", "branch", "board", "tier"}.issubset(column_keys)
    assert any(row.get("branch") == "West Wing" for row in payload["rows"])
