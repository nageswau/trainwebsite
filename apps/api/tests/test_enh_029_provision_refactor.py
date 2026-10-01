"""ENH-029 -- create_school's body moved into admin._provision_school (spec §7): the single create is unchanged."""

import inspect
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, School, User, UserRoleAssignment
from tests.enh029_helpers import login, mk_admin


def test_helper_exists_and_defaults_to_flush_unique_email():
    from app.api.admin import _provision_school
    from app.services.provisioning import flush_unique_email

    assert inspect.signature(_provision_school).parameters["flush_coordinator"].default is flush_unique_email


@pytest.mark.asyncio
async def test_single_create_response_and_audits_unchanged(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    tag = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"Refactor {tag}", "city": "Pune", "tier": "gold", "coordinator_full_name": "C", "coordinator_email": f"r-{tag}@example.local"},
    )
    assert response.status_code == 201
    body = response.json()
    assert {"id", "school_code", "coordinator_id", "coordinator_email", "email_status", "expires_at", "development_welcome_token"} <= set(body)
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert {"school.create", "school.coordinator_seed", "user.welcome_link_issue", "user.welcome_link_delivery"} <= actions
    coordinator = await db_session.get(User, uuid.UUID(body["coordinator_id"]))
    assert coordinator.role == "school_coordinator"
    assert coordinator.profile == {"school_id": body["id"]}
    assert await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == coordinator.id, UserRoleAssignment.assigned_by_user_id == admin.id))


@pytest.mark.asyncio
async def test_single_create_duplicate_email_is_still_409_and_creates_no_school(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    tag = uuid.uuid4().hex[:8]
    payload = {"name": f"Dup {tag}", "coordinator_full_name": "C", "coordinator_email": f"dup-{tag}@example.local"}
    assert (await client.post("/api/v1/overseas-admin/schools", json=payload)).status_code == 201
    second = await client.post("/api/v1/overseas-admin/schools", json={**payload, "name": f"Dup2 {tag}"})
    assert second.status_code == 409
    assert second.json()["detail"] == "Email already exists"
    assert await db_session.scalar(select(School).where(School.name == f"Dup2 {tag}")) is None
