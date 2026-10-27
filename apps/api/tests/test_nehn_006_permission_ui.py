"""nehn-006 (DEC-SCOPE-295) -- the backend side of the permission-matrix screen: the catalogue names the roles the matrix edits, and
the admin portal's Payments section follows `payments.view` like `/admin/payments` does, so a revoked role's page is refused by the API.
Spec docs/superpowers/specs/2026-10-27-nehn-006-permission-matrix-ui-design.md."""

import pytest

from app.core import rbac
from tests.test_nehn_005_permissions import API, _headers, _restored, _user

PAYMENTS_REFUSED = "You do not have permission to view payments"


@pytest.mark.asyncio
async def test_the_catalogue_lists_every_role_for_the_matrix(client, db_session):
    root = await _user(db_session, "super_admin")
    body = (await client.get(f"{API}/admin/permissions/catalogue", headers=_headers(root))).json()
    assert body["roles"] == list(rbac.ROLES)
    assert body["actions"] == list(rbac.ACTIONS)  # the existing fields are unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("it_admin", "it"), ("overseas_admin", "overseas")])
async def test_the_portal_payments_section_follows_payments_view(client, db_session, role, division):
    root, admin = await _user(db_session, "super_admin"), await _user(db_session, role)
    url = f"{API}/portal/{division}/admin/payments"
    assert (await client.get(url, headers=_headers(admin))).status_code == 200  # the seed grant: unchanged for day one
    async with _restored(db_session, role):
        keys = sorted(set(rbac.DEFAULT_GRANTS[role]) - {"payments.view"})
        assert (await client.put(f"{API}/admin/roles/{role}/permissions", json={"permissions": keys}, headers=_headers(root))).status_code == 200
        refused = await client.get(url, headers=_headers(admin))
        assert refused.status_code == 403 and refused.json()["detail"] == PAYMENTS_REFUSED
        # The rest of the admin portal is untouched.
        assert (await client.get(f"{API}/portal/{division}/admin/dashboard", headers=_headers(admin))).status_code == 200
        restored = await client.put(f"{API}/admin/roles/{role}/permissions", json={"permissions": sorted(rbac.DEFAULT_GRANTS[role])}, headers=_headers(root))
        assert restored.status_code == 200
        assert (await client.get(url, headers=_headers(admin))).status_code == 200


@pytest.mark.asyncio
async def test_super_admin_always_reads_the_portal_payments_section(client, db_session):
    root = await _user(db_session, "super_admin")
    assert (await client.get(f"{API}/portal/it/admin/payments", headers=_headers(root))).status_code == 200
