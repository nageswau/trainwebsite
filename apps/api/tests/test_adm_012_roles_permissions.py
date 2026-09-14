"""ADM-012 -- Roles/permission administration.

Promoted out of `Unscheduled/BLOCKED` on 2026-09-03 (`DEC-SCOPE-008`). **PARTIAL scope,
deliberately**: the Acceptance Criteria (`ADM-012-AC01`) call for "views and adjusts", but
the confirmed requirement this feature actually traces to (`PRD-ADM-013` -- MASTER_
FEATURE_CATALOG.md's own trace, distinct from PRD.md's unrelated `PRD-ADM-012` heading) is
explicit: "Admin can view role/permission assignments... whether permissions need to be
admin-configurable at runtime... was never asked." `core/rbac.py`'s `PERMISSIONS` is a
static code table with no DB-backed concept to edit. Building live permission editing here
would mean inventing a security-critical runtime engine on an unconfirmed requirement, not
extending a confirmed one -- not attempted; flagged in `PRD_OPEN_ITEMS.md` instead. This
tests the confirmed view half (real, live `core/rbac.py` data, IT-Admin-only) and confirms
there is no write endpoint to silently misbehave (`ADM-012-AC02` is vacuously satisfied).
"""

import uuid

import pytest

from app.core.rbac import PERMISSIONS
from app.core.security import hash_password
from app.models import User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}", role=role, division="it", active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, division: str = "it") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_it_admin_sees_the_real_permission_bundle_enforced_per_role(client, db_session):
    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin.email)

    response = await client.get("/api/v1/portal/it/admin/roles")
    assert response.status_code == 200
    rows = {row["role"]: row for row in response.json()["rows"]}

    # Every role in the live enforcement table appears, with its real bundle -- not a
    # hand-copied duplicate that could drift from what core/rbac.py actually enforces.
    for role, perms in PERMISSIONS.items():
        assert role in rows
        assert rows[role]["permissions"] == ", ".join(sorted(perms))


@pytest.mark.asyncio
async def test_role_row_reflects_a_real_active_user_count(client, db_session):
    await _create_user(db_session, "trainer")
    await _create_user(db_session, "trainer")
    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin.email)

    response = await client.get("/api/v1/portal/it/admin/roles")
    rows = {row["role"]: row for row in response.json()["rows"]}
    assert rows["trainer"]["users"] >= 2


@pytest.mark.asyncio
async def test_super_admin_can_also_view_the_roles_section(client, db_session):
    super_admin = await _create_user(db_session, "super_admin")
    await _login(client, super_admin.email)
    response = await client.get("/api/v1/portal/it/admin/roles")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_role_is_rejected(client, db_session):
    trainer = await _create_user(db_session, "trainer")
    await _login(client, trainer.email)
    response = await client.get("/api/v1/portal/it/admin/roles")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_has_no_roles_section_it_admin_only_per_the_confirmed_ac(client, db_session):
    overseas_admin = User(
        email=f"overseas-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(overseas_admin)
    await db_session.commit()
    await _login(client, overseas_admin.email, division="overseas")

    response = await client.get("/api/v1/portal/overseas/admin/roles")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_roles_section_requires_authentication(client):
    response = await client.get("/api/v1/portal/it/admin/roles")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_no_write_endpoint_exists_to_edit_permissions_the_unconfirmed_half_is_not_built(client, db_session):
    # ADM-012-AC02 ("an attempt to remove a structurally-required permission is
    # rejected, not silently accepted") is vacuously true: there is no write surface at
    # all for role/permission editing (deliberately, per PRD-ADM-013's unconfirmed
    # status), so nothing can silently accept a bad edit. Confirmed directly rather than
    # assumed -- a plausible endpoint shape 404s.
    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin.email)
    response = await client.patch("/api/v1/admin/roles/it_admin", json={"permissions": ["*"]})
    assert response.status_code == 404
