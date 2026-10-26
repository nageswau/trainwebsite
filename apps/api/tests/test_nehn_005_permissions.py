"""nehn-005 -- the permission engine: role x resource x action grants in `role_permissions`, enforced by `require_permission` on the two
pilot modules (admin payments, telecaller reports). DEC-SCOPE-281; spec docs/superpowers/specs/2026-10-26-nehn-005-permission-engine-design.md."""

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, select

from app.core import rbac
from app.core.security import create_token
from app.models import AuditLog, RolePermission, User
from app.services import permissions

API = "/api/v1"
ADMIN_REQUIRED = "Admin role required"
REPORTS_REQUIRED = "Telecaller reports are for managers and administrators"
DOWNLOAD_REFUSED = "You don't have permission to download telecaller reports"  # QA-01

# The oracle: who passed each pilot route's inline role check before nehn-005 (admin.ensure_admin, telecaller_reports.REPORT_ROLES).
OLD_ADMIN = {"super_admin", "it_admin", "overseas_admin"}
OLD_REPORTS = {"telecaller_manager", "super_admin", "it_admin", "overseas_admin"}
DIVISION = {
    "it_admin": "it",
    "it_student": "it",
    "trainer": "it",
    "placement_team": "it",
    "hr_team": "it",
    "coordinator": "it",
    "placement_manager": "it",
    "overseas_admin": "overseas",
    "overseas_student": "overseas",
    "counselor": "overseas",
    "university_rep": "overseas",
    "agent": "overseas",
}


async def _user(db, role: str) -> User:
    user = User(email=f"n005-{uuid.uuid4().hex[:10]}@example.local", password_hash="!", full_name=f"N005 {role}", role=role, division=DIVISION.get(role, "global"), active=True, email_verified=True)
    db.add(user)
    await db.commit()
    return user


def _headers(user: User | None) -> dict:
    if user is None:
        return {}
    return {"Cookie": f"edusphere_access={create_token(str(user.id), user.role, user.division, 'access', user.session_version)}"}


@asynccontextmanager
async def _restored(db, role: str):
    """Put the role's grants back exactly as they were, whatever the test did."""
    before = set(await permissions.role_grants(db, role))
    try:
        yield
    finally:
        await db.execute(delete(RolePermission).where(RolePermission.role == role))
        for key in before:
            resource, action = rbac.parse_key(key)
            db.add(RolePermission(role=role, resource=resource, action=action))
        await db.commit()


# --- catalogue and seed ------------------------------------------------------------------------------------------------------------


def test_the_catalogue_names_the_pilot_resources_and_known_actions():
    assert set(rbac.CATALOGUE) == {"payments", "discounts", "reports.telecaller", "certificates"}  # nehn-030 added certificates
    for resource in rbac.CATALOGUE.values():
        assert set(resource["actions"]) <= set(rbac.ACTIONS)
    assert rbac.ACTIONS == ("view", "add", "edit", "delete", "download", "approve", "review", "issue", "manage")


def test_roles_are_the_29_existing_roles():
    assert len(rbac.ROLES) == 29 and "super_admin" in rbac.ROLES and "coordinator" in rbac.ROLES  # nehn-030 added coordinator


def test_the_default_grants_reproduce_the_old_inline_sets():
    holders = lambda key: {role for role, keys in rbac.DEFAULT_GRANTS.items() if key in keys} | {"super_admin"}  # noqa: E731
    for key in ("payments.view", "payments.add", "discounts.add"):
        assert holders(key) == OLD_ADMIN
    for key in ("reports.telecaller.view", "reports.telecaller.download"):
        assert holders(key) == OLD_REPORTS
    assert "super_admin" not in rbac.DEFAULT_GRANTS  # implicit, never rows


@pytest.mark.parametrize("key", ["payments.view", "reports.telecaller.download", "discounts.add"])
def test_parse_key_splits_on_the_last_dot(key):
    resource, action = rbac.parse_key(key)
    assert f"{resource}.{action}" == key and action in rbac.ACTIONS


def test_require_permission_refuses_a_key_outside_the_catalogue_at_import():
    from app.api.deps import require_permission

    with pytest.raises(ValueError):
        require_permission("payments", "fly")
    with pytest.raises(ValueError):
        require_permission("nonsense", "view")


@pytest.mark.asyncio
async def test_the_seeded_table_matches_the_default_grants(db_session):
    rows = (await db_session.scalars(select(RolePermission))).all()
    seeded: dict[str, set[str]] = {}
    for row in rows:
        seeded.setdefault(row.role, set()).add(f"{row.resource}.{row.action}")
    assert seeded == {role: set(keys) for role, keys in rbac.DEFAULT_GRANTS.items()}


@pytest.mark.asyncio
async def test_has_grant_denies_unknown_keys_and_allows_super_admin(db_session):
    assert await permissions.has_grant(db_session, "super_admin", "payments", "view")
    assert await permissions.has_grant(db_session, "it_admin", "payments", "view")
    assert not await permissions.has_grant(db_session, "it_student", "payments", "view")
    assert not await permissions.has_grant(db_session, "it_admin", "payments", "delete")  # not in the catalogue
    assert not await permissions.has_grant(db_session, "it_admin", "nonsense", "view")
    assert not await permissions.has_grant(db_session, "super_admin", "nonsense", "view")  # unknown key: deny, even for super_admin


# --- equivalence: every role x pilot route answers exactly as the inline checks did (AC1) --------------------------------------------


@pytest.mark.parametrize("role", rbac.ROLES)
@pytest.mark.asyncio
async def test_seed_equivalence_for_every_role(client, db_session, role):
    user = await _user(db_session, role)
    h = _headers(user)
    nobody = uuid.uuid4()
    admin_calls = [
        ("get", f"{API}/admin/payments", None, 200),
        ("post", f"{API}/admin/payments", {"user_id": str(nobody), "amount": 10}, 404),
        ("post", f"{API}/admin/payments/emi-schedule", {"user_id": str(nobody), "installments": []}, 404),
        ("post", f"{API}/admin/payments/{nobody}/discount", {"amount": 1, "reason": "x"}, 404),
    ]
    for method, url, body, allowed in admin_calls:
        response = await client.request(method, url, json=body, headers=h)
        expected = allowed if role in OLD_ADMIN else 403
        assert response.status_code == expected, f"{role} {method} {url}: {response.status_code} {response.text[:200]}"
        if expected == 403:
            assert response.json()["detail"] == ADMIN_REQUIRED
    for url, refused in ((f"{API}/telecaller/reports/source", REPORTS_REQUIRED), (f"{API}/telecaller/reports/source.csv", DOWNLOAD_REFUSED)):
        response = await client.get(url, headers=h)
        expected = 200 if role in OLD_REPORTS else 403
        assert response.status_code == expected, f"{role} {url}: {response.status_code} {response.text[:200]}"
        if expected == 403:
            assert response.json()["detail"] == refused


@pytest.mark.asyncio
async def test_anonymous_still_gets_401_on_the_pilot_routes(client):
    for url in ("/admin/payments", "/telecaller/reports/source", "/telecaller/reports/source.csv"):
        assert (await client.get(f"{API}{url}")).status_code == 401


# --- revoke and restore without a restart (AC2, AC3, AC7) ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoking_payments_view_refuses_it_admin_and_restoring_allows_it(client, db_session):
    root, it_admin = await _user(db_session, "super_admin"), await _user(db_session, "it_admin")
    async with _restored(db_session, "it_admin"):
        keys = set(rbac.DEFAULT_GRANTS["it_admin"])
        revoked = await client.put(f"{API}/admin/roles/it_admin/permissions", json={"permissions": sorted(keys - {"payments.view"})}, headers=_headers(root))
        assert revoked.status_code == 200, revoked.text
        assert "payments.view" not in revoked.json()["permissions"]
        refused = await client.get(f"{API}/admin/payments", headers=_headers(it_admin))
        assert refused.status_code == 403 and refused.json()["detail"] == ADMIN_REQUIRED
        # The rest of the role is untouched.
        assert (await client.post(f"{API}/admin/payments", json={"user_id": str(uuid.uuid4()), "amount": 1}, headers=_headers(it_admin))).status_code == 404
        restored = await client.put(f"{API}/admin/roles/it_admin/permissions", json={"permissions": sorted(keys)}, headers=_headers(root))
        assert restored.status_code == 200
        assert (await client.get(f"{API}/admin/payments", headers=_headers(it_admin))).status_code == 200


@pytest.mark.asyncio
async def test_revoking_download_keeps_the_json_report(client, db_session):
    root, manager = await _user(db_session, "super_admin"), await _user(db_session, "telecaller_manager")
    async with _restored(db_session, "telecaller_manager"):
        response = await client.put(f"{API}/admin/roles/telecaller_manager/permissions", json={"permissions": ["reports.telecaller.view"]}, headers=_headers(root))
        assert response.status_code == 200, response.text
        assert (await client.get(f"{API}/telecaller/reports/source", headers=_headers(manager))).status_code == 200
        csv = await client.get(f"{API}/telecaller/reports/source.csv", headers=_headers(manager))
        assert csv.status_code == 403 and csv.json()["detail"] == DOWNLOAD_REFUSED


@pytest.mark.asyncio
async def test_a_grant_to_a_new_role_opens_the_route_for_it(client, db_session):
    root, accountant = await _user(db_session, "super_admin"), await _user(db_session, "accountant")
    async with _restored(db_session, "accountant"):
        assert (await client.get(f"{API}/admin/payments", headers=_headers(accountant))).status_code == 403
        await client.put(f"{API}/admin/roles/accountant/permissions", json={"permissions": ["payments.view"]}, headers=_headers(root))
        assert (await client.get(f"{API}/admin/payments", headers=_headers(accountant))).status_code == 200


# --- the admin endpoints ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalogue_endpoint(client, db_session):
    root = await _user(db_session, "super_admin")
    response = await client.get(f"{API}/admin/permissions/catalogue", headers=_headers(root))
    assert response.status_code == 200
    body = response.json()
    assert body["actions"] == list(rbac.ACTIONS)
    assert {r["key"] for r in body["resources"]} == set(rbac.CATALOGUE)
    payments = next(r for r in body["resources"] if r["key"] == "payments")
    assert payments["actions"] == ["view", "add"] and payments["label"]


@pytest.mark.asyncio
async def test_read_a_roles_grants(client, db_session):
    root = await _user(db_session, "super_admin")
    response = await client.get(f"{API}/admin/roles/telecaller_manager/permissions", headers=_headers(root))
    assert response.status_code == 200
    assert response.json() == {"role": "telecaller_manager", "permissions": sorted(rbac.DEFAULT_GRANTS["telecaller_manager"]), "editable": True}
    sa = (await client.get(f"{API}/admin/roles/super_admin/permissions", headers=_headers(root))).json()
    assert sa["editable"] is False and set(sa["permissions"]) == set(rbac.all_keys())


@pytest.mark.parametrize("role", ["it_admin", "overseas_admin", "telecaller_manager", "it_student"])
@pytest.mark.asyncio
async def test_only_super_admin_reads_or_edits_grants(client, db_session, role):
    h = _headers(await _user(db_session, role))
    assert (await client.get(f"{API}/admin/permissions/catalogue", headers=h)).status_code == 403
    assert (await client.get(f"{API}/admin/roles/it_admin/permissions", headers=h)).status_code == 403
    # A refused caller never learns which role names exist.
    assert (await client.get(f"{API}/admin/roles/no_such_role/permissions", headers=h)).status_code == 403
    put = await client.put(f"{API}/admin/roles/{role}/permissions", json={"permissions": list(rbac.all_keys())}, headers=h)
    assert put.status_code == 403
    assert set(await permissions.role_grants(db_session, role)) == set(rbac.DEFAULT_GRANTS.get(role, ()))


@pytest.mark.asyncio
async def test_admin_endpoints_need_a_session(client):
    assert (await client.get(f"{API}/admin/permissions/catalogue")).status_code == 401
    assert (await client.put(f"{API}/admin/roles/it_admin/permissions", json={"permissions": []})).status_code == 401
    assert (await client.get(f"{API}/auth/me/permissions")).status_code == 401


@pytest.mark.asyncio
async def test_validation(client, db_session):
    h = _headers(await _user(db_session, "super_admin"))
    assert (await client.get(f"{API}/admin/roles/no_such_role/permissions", headers=h)).status_code == 404
    assert (await client.put(f"{API}/admin/roles/no_such_role/permissions", json={"permissions": []}, headers=h)).status_code == 404
    for bad in (["payments.fly"], ["nonsense.view"], ["payments"], ["payments.view", "payments.view"]):
        response = await client.put(f"{API}/admin/roles/it_admin/permissions", json={"permissions": bad}, headers=h)
        assert response.status_code == 422, bad
    assert (await client.put(f"{API}/admin/roles/it_admin/permissions", json={}, headers=h)).status_code == 422
    assert set(await permissions.role_grants(db_session, "it_admin")) == set(rbac.DEFAULT_GRANTS["it_admin"])


@pytest.mark.asyncio
async def test_super_admin_grants_cannot_be_reduced(client, db_session):
    root = await _user(db_session, "super_admin")
    response = await client.put(f"{API}/admin/roles/super_admin/permissions", json={"permissions": []}, headers=_headers(root))
    assert response.status_code == 409
    assert (await client.get(f"{API}/admin/payments", headers=_headers(root))).status_code == 200
    assert (await client.get(f"{API}/telecaller/reports/source.csv", headers=_headers(root))).status_code == 200


@pytest.mark.asyncio
async def test_a_change_is_audited_with_before_and_after(client, db_session):
    root = await _user(db_session, "super_admin")
    async with _restored(db_session, "partner"):
        response = await client.put(f"{API}/admin/roles/partner/permissions", json={"permissions": ["payments.view", "reports.telecaller.view"]}, headers=_headers(root))
        assert response.status_code == 200
        rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "role_permissions.update", AuditLog.user_id == root.id))).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.entity_type == "role" and row.entity_id == "partner"
        assert row.metadata_json == {"before": [], "after": ["payments.view", "reports.telecaller.view"], "added": ["payments.view", "reports.telecaller.view"], "removed": []}
        grant = await db_session.scalar(select(RolePermission).where(RolePermission.role == "partner", RolePermission.resource == "payments"))
        assert grant.granted_by_id == root.id and grant.granted_at is not None
        # The same set again changes nothing and writes nothing.
        again = await client.put(f"{API}/admin/roles/partner/permissions", json={"permissions": ["reports.telecaller.view", "payments.view"]}, headers=_headers(root))
        assert again.status_code == 200
        count = len((await db_session.scalars(select(AuditLog).where(AuditLog.action == "role_permissions.update", AuditLog.user_id == root.id))).all())
        assert count == 1


# --- the caller's own effective set ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_permissions(client, db_session):
    manager = await _user(db_session, "telecaller_manager")
    body = (await client.get(f"{API}/auth/me/permissions", headers=_headers(manager))).json()
    assert body == {"role": "telecaller_manager", "permissions": sorted(rbac.DEFAULT_GRANTS["telecaller_manager"])}
    student = (await client.get(f"{API}/auth/me/permissions", headers=_headers(await _user(db_session, "it_student")))).json()
    assert student == {"role": "it_student", "permissions": []}
    root = (await client.get(f"{API}/auth/me/permissions", headers=_headers(await _user(db_session, "super_admin")))).json()
    assert set(root["permissions"]) == set(rbac.all_keys())
