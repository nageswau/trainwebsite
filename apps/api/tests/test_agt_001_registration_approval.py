"""AGT-001 -- Agent self-registration and approval gate.

Self-registration (`POST /auth/register` with `account_type=agent`) and the
`UserRoleAssignment.approval_status` schema already existed -- both net-new for a prior
foundation pass, per `DATA_MODEL.md` §1.3. The real, confirmed gap: nothing anywhere in
the codebase actually *enforced* the approval gate. `core/rbac.py`'s own deny-by-default
machinery (`user_has_role`, `require_role`, etc.) correctly denies a Pending/Rejected
Agent -- but no route actually uses it. Every real route instead checks the legacy
`User.role` column directly (`workflows.py`'s `_require`, `portal.py`'s dispatcher),
which has no approval concept at all -- a Pending Agent could reach every agent-scoped
endpoint immediately after registering, unapproved (`AGT-001-AC02`, confirmed directly
against the running stack before this fix). Added `core.rbac.agent_is_approved()` and
wired it into both call sites. Added the missing approve/reject actions
(`POST /overseas-admin/agents/{id}/approve`/`reject`), which did not exist either.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import User, UserRoleAssignment


async def _register_agent(client, **overrides) -> dict:
    payload = {
        "email": f"agt001-{uuid.uuid4().hex[:8]}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "Test Agent",
        "division": "overseas",
        "account_type": "agent",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    return response.json()


async def _create_overseas_admin(db_session) -> User:
    admin = User(
        email=f"agt001-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agent_self_registers_pending_and_is_denied_the_portal_dashboard(client, db_session):
    registration = await _register_agent(client)
    assert registration["user"]["role"] == "agent"

    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uuid.UUID(registration["user"]["id"])))
    assert assignment.approval_status == "pending"

    # Already logged in by registration itself -- confirm the pending gate denies access.
    response = await client.get("/api/v1/portal/overseas/agent/dashboard")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pending_agent_cannot_create_an_overseas_application(client, db_session):
    registration = await _register_agent(client)
    response = await client.post("/api/v1/workflows/overseas/applications", json={"university_id": str(uuid.uuid4()), "student_id": registration["user"]["id"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_approves_and_the_agent_gains_access(client, db_session):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/approve")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"

    await _login(client, registration["user"]["email"])
    dashboard = await client.get("/api/v1/portal/overseas/agent/dashboard")
    assert dashboard.status_code == 200


@pytest.mark.asyncio
async def test_overseas_admin_rejects_and_the_agent_stays_denied(client, db_session):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/reject")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"

    await _login(client, registration["user"]["email"])
    dashboard = await client.get("/api/v1/portal/overseas/agent/dashboard")
    assert dashboard.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_role_cannot_approve_an_agent(client, db_session):
    registration = await _register_agent(client)
    other_agent = await _register_agent(client)

    await _login(client, other_agent["user"]["email"])
    response = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/approve")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_approving_an_unknown_agent_404s(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/agents/{uuid.uuid4()}/approve")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_approval_requires_authentication(client):
    response = await client.post(f"/api/v1/overseas-admin/agents/{uuid.uuid4()}/approve")
    assert response.status_code == 401
