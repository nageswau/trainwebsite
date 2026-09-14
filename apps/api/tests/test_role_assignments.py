"""FND-002 -- division-aware RBAC & identity framework.

Exercises DATA_MODEL.md §1.1-1.3 and RBAC_MATRIX.md §2.8 end to end through the real
/auth endpoints (no business-module routes are touched -- those are out of scope for
Foundation), plus direct unit coverage of the deny-by-default resolution helpers in
app.core.rbac / app.api.deps against a real database session.
"""

import uuid

import pytest

from app.api.deps import require_division, require_role
from app.core.rbac import get_active_assignments, has_permission
from app.core.security import hash_password
from app.models import User, UserRoleAssignment


async def _create_user(db_session, *, role: str, division: str, email: str | None = None) -> User:
    user = User(
        email=email or f"{uuid.uuid4()}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test User",
        role=role,
        division=division,
        active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# --- FND-002-AC01: main workflow completes and is visible to the correct actor(s) only ---


@pytest.mark.asyncio
async def test_register_creates_an_approved_assignment_for_a_student(client):
    payload = {
        "email": f"student-{uuid.uuid4()}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "New Student",
        "division": "it",
        "account_type": "student",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    body = response.json()["user"]
    assert body["role"] == "it_student"
    assert body["role_assignments"] == [
        {"division": "it", "role": "it_student", "is_active": True, "approval_status": "approved"}
    ]


@pytest.mark.asyncio
async def test_register_agent_creates_a_pending_assignment_not_approved(client):
    """RBAC_MATRIX.md §2.8: an Agent's assignment starts `pending`, not `approved` --
    the two-gate approval requirement (DEC-SCOPE-004) begins at the data-model level."""
    payload = {
        "email": f"agent-{uuid.uuid4()}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "New Agent",
        "division": "overseas",
        "account_type": "agent",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assignment = response.json()["user"]["role_assignments"][0]
    assert assignment == {"division": "overseas", "role": "agent", "is_active": True, "approval_status": "pending"}


# --- FND-002-AC02: unauthorized/wrong-division request returns 401/403, never partial data ---


@pytest.mark.asyncio
async def test_me_without_credentials_is_401_not_partial_data(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "role_assignments" not in response.text


@pytest.mark.asyncio
async def test_login_wrong_division_is_403(client):
    email = f"wrongdiv-{uuid.uuid4()}@example.local"
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Sup3r-Secret-Pass!", "full_name": "Wrong Division", "division": "it", "account_type": "student"},
    )
    assert register_response.status_code == 201
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 403


# --- FND-002-AC03: RBAC -- an actor outside the allowed set cannot perform/view the action, at the API layer ---


async def _call_dependency(dependency, user, db_session):
    # require_division()/require_role() build a small async closure; invoke it directly
    # the same way FastAPI's dependency injection would, without needing a live route.
    return await dependency(user=user, db=db_session)


@pytest.mark.asyncio
async def test_require_division_denies_by_default(db_session):
    user = await _create_user(db_session, role="it_student", division="it")
    db_session.add(UserRoleAssignment(user_id=user.id, division="it", role="it_student", is_active=True, approval_status="approved"))
    await db_session.commit()

    # Has a real, active, approved assignment -- just not in the requested division.
    with pytest.raises(Exception) as exc_info:
        await _call_dependency(require_division("overseas"), user, db_session)
    assert getattr(exc_info.value, "status_code", None) == 403

    result = await _call_dependency(require_division("it"), user, db_session)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_require_role_allows_the_correct_role_and_denies_others(db_session):
    user = await _create_user(db_session, role="trainer", division="it")
    db_session.add(UserRoleAssignment(user_id=user.id, division="it", role="trainer", is_active=True, approval_status="approved"))
    await db_session.commit()

    allowed = require_role("trainer")
    denied = require_role("it_admin")

    result = await _call_dependency(allowed, user, db_session)
    assert result.id == user.id

    with pytest.raises(Exception) as exc_info:
        await _call_dependency(denied, user, db_session)
    assert getattr(exc_info.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_pending_agent_has_no_usable_assignment(db_session):
    """The core of RBAC_MATRIX.md §2.8's deny rule: an unapproved Agent's own
    UserRoleAssignment row exists and is `is_active=True`, but is never returned by
    get_active_assignments() -- so every require_role()/require_division()/
    require_permission() check built on it denies by default, per DATA_MODEL.md §1.3."""
    user = await _create_user(db_session, role="agent", division="overseas")
    db_session.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, approval_status="pending"))
    await db_session.commit()

    assignments = await get_active_assignments(db_session, user.id)
    assert assignments == []

    with pytest.raises(Exception) as exc_info:
        await _call_dependency(require_role("agent"), user, db_session)
    assert getattr(exc_info.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_approved_agent_has_a_usable_assignment(db_session):
    user = await _create_user(db_session, role="agent", division="overseas")
    db_session.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, approval_status="approved"))
    await db_session.commit()

    result = await _call_dependency(require_role("agent"), user, db_session)
    assert result.id == user.id


def test_has_permission_unchanged_for_existing_roles():
    # Base-codebase behavior, preserved -- FND-002 is additive, not a rewrite.
    assert has_permission("super_admin", "anything:anywhere")
    assert not has_permission("it_student", "users:write")
    assert has_permission("employer", "employer:self")
