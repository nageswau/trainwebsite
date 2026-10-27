"""nehn-007 -- per-user permission overrides: effective = (role grants + active allows) - active denies, applied by every grant check
and `/auth/me/permissions`; super_admin-only endpoints to read, replace and report them. DEC-SCOPE-297; spec
docs/superpowers/specs/2026-10-27-nehn-007-per-user-permission-overrides-design.md."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, UserPermissionOverride
from app.services import permissions
from tests.test_nehn_005_permissions import ADMIN_REQUIRED, API, DOWNLOAD_REFUSED, _headers, _user

AUDIT = "user_permission_overrides.update"


def _path(user) -> str:
    return f"{API}/admin/users/{user.id}/permissions"


def _override(permission: str, effect: str, reason: str = "QA cover", expires_at: str | None = None) -> dict:
    item = {"permission": permission, "effect": effect, "reason": reason}
    if expires_at is not None:
        item["expires_at"] = expires_at
    return item


def _later(**delta) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


async def _put(client, root, user, *items):
    return await client.put(_path(user), json={"overrides": list(items)}, headers=_headers(root))


# --- resolution through the real routes (AC1, AC2, AC3) ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_deny_removes_one_permission_for_that_user_only(client, db_session):
    root = await _user(db_session, "super_admin")
    denied, other = await _user(db_session, "telecaller_manager"), await _user(db_session, "telecaller_manager")
    response = await _put(client, root, denied, _override("reports.telecaller.download", "deny"))
    assert response.status_code == 200, response.text
    refused = await client.get(f"{API}/telecaller/reports/source.csv", headers=_headers(denied))
    assert refused.status_code == 403 and refused.json()["detail"] == DOWNLOAD_REFUSED
    assert (await client.get(f"{API}/telecaller/reports/source", headers=_headers(denied))).status_code == 200
    assert (await client.get(f"{API}/telecaller/reports/source.csv", headers=_headers(other))).status_code == 200
    mine = (await client.get(f"{API}/auth/me/permissions", headers=_headers(denied))).json()
    assert mine == {"role": "telecaller_manager", "permissions": ["reports.telecaller.view"]}


@pytest.mark.asyncio
async def test_an_allow_grants_one_user_a_permission_their_role_lacks(client, db_session):
    root = await _user(db_session, "super_admin")
    allowed, other = await _user(db_session, "hr_team"), await _user(db_session, "hr_team")
    assert (await client.get(f"{API}/admin/payments", headers=_headers(allowed))).status_code == 403
    assert (await _put(client, root, allowed, _override("payments.view", "allow"))).status_code == 200
    assert (await client.get(f"{API}/admin/payments", headers=_headers(allowed))).status_code == 200
    refused = await client.get(f"{API}/admin/payments", headers=_headers(other))
    assert refused.status_code == 403 and refused.json()["detail"] == ADMIN_REQUIRED
    mine = (await client.get(f"{API}/auth/me/permissions", headers=_headers(allowed))).json()
    assert mine["permissions"] == ["payments.view"]


@pytest.mark.asyncio
async def test_a_deny_closes_the_portal_payments_section(client, db_session):
    root, admin = await _user(db_session, "super_admin"), await _user(db_session, "it_admin")
    assert (await client.get(f"{API}/portal/it/admin/payments", headers=_headers(admin))).status_code == 200
    await _put(client, root, admin, _override("payments.view", "deny"))
    assert (await client.get(f"{API}/portal/it/admin/payments", headers=_headers(admin))).status_code == 403


@pytest.mark.asyncio
async def test_an_expired_override_stops_applying_without_action(client, db_session):
    root, user = await _user(db_session, "super_admin"), await _user(db_session, "hr_team")
    assert (await _put(client, root, user, _override("payments.view", "allow", expires_at=_later(hours=1)))).status_code == 200
    assert await permissions.user_has_grant(db_session, user, "payments", "view")
    row = await db_session.scalar(select(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.get(f"{API}/admin/payments", headers=_headers(user))).status_code == 403
    body = (await client.get(_path(user), headers=_headers(root))).json()
    assert body["overrides"] == [] and body["effective"] == []
    report = (await client.get(f"{API}/admin/permissions/overrides", headers=_headers(root))).json()
    assert str(user.id) not in {r["user_id"] for r in report}


@pytest.mark.asyncio
async def test_no_override_rows_means_the_role_answer(db_session):
    for role in ("it_admin", "telecaller_manager", "hr_team", "coordinator"):
        user = await _user(db_session, role)
        assert await permissions.user_grants(db_session, user) == await permissions.role_grants(db_session, role)
        for key in rbac.all_keys():
            resource, action = rbac.parse_key(key)
            assert await permissions.user_has_grant(db_session, user, resource, action) == await permissions.has_grant(db_session, role, resource, action)


# --- the admin endpoints (AC4) -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_shows_role_overrides_and_effective(client, db_session):
    root, admin = await _user(db_session, "super_admin"), await _user(db_session, "it_admin")
    expiry = _later(days=7)
    await _put(client, root, admin, _override("payments.add", "deny", "Under review"), _override("certificates.view", "allow", "Cover", expiry))
    body = (await client.get(_path(admin), headers=_headers(root))).json()
    assert body["user"] == {"id": str(admin.id), "full_name": admin.full_name, "email": admin.email, "role": "it_admin"}
    assert body["editable"] is True
    assert body["role_permissions"] == sorted(rbac.DEFAULT_GRANTS["it_admin"])
    assert [(o["permission"], o["effect"], o["reason"]) for o in body["overrides"]] == [("certificates.view", "allow", "Cover"), ("payments.add", "deny", "Under review")]
    assert datetime.fromisoformat(body["overrides"][0]["expires_at"]) == datetime.fromisoformat(expiry)
    assert body["overrides"][1]["expires_at"] is None
    assert body["effective"] == sorted((set(rbac.DEFAULT_GRANTS["it_admin"]) | {"certificates.view"}) - {"payments.add"})


@pytest.mark.asyncio
async def test_the_report_lists_every_active_override(client, db_session):
    root = await _user(db_session, "super_admin")
    first, second = await _user(db_session, "hr_team"), await _user(db_session, "trainer")
    await _put(client, root, first, _override("payments.view", "allow", "Month-end cover"))
    await _put(client, root, second, _override("certificates.view", "allow", "Pilot"))
    report = (await client.get(f"{API}/admin/permissions/overrides", headers=_headers(root))).json()
    mine = [r for r in report if r["user_id"] in {str(first.id), str(second.id)}]
    assert {(r["user_id"], r["permission"], r["effect"], r["reason"], r["role"]) for r in mine} == {
        (str(first.id), "payments.view", "allow", "Month-end cover", "hr_team"),
        (str(second.id), "certificates.view", "allow", "Pilot", "trainer"),
    }
    assert all(r["full_name"] and r["email"] for r in mine)


@pytest.mark.parametrize("role", ["it_admin", "overseas_admin", "telecaller_manager", "hr_team"])
@pytest.mark.asyncio
async def test_only_super_admin_reads_or_edits_overrides(client, db_session, role):
    caller, target = await _user(db_session, role), await _user(db_session, "hr_team")
    h = _headers(caller)
    assert (await client.get(_path(target), headers=h)).status_code == 403
    assert (await client.get(f"{API}/admin/users/{uuid.uuid4()}/permissions", headers=h)).status_code == 403
    assert (await client.get(f"{API}/admin/permissions/overrides", headers=h)).status_code == 403
    put = await client.put(_path(caller), json={"overrides": [_override("payments.view", "allow")]}, headers=h)
    assert put.status_code == 403
    assert await permissions.user_grants(db_session, caller) == await permissions.role_grants(db_session, role)


@pytest.mark.asyncio
async def test_endpoints_need_a_session(client):
    target = f"{API}/admin/users/{uuid.uuid4()}/permissions"
    assert (await client.get(target)).status_code == 401
    assert (await client.put(target, json={"overrides": []})).status_code == 401
    assert (await client.get(f"{API}/admin/permissions/overrides")).status_code == 401


@pytest.mark.asyncio
async def test_validation(client, db_session):
    root, user = await _user(db_session, "super_admin"), await _user(db_session, "hr_team")
    h = _headers(root)
    missing = f"{API}/admin/users/{uuid.uuid4()}/permissions"
    assert (await client.get(missing, headers=h)).status_code == 404
    assert (await client.put(missing, json={"overrides": []}, headers=h)).status_code == 404
    assert (await client.get(f"{API}/admin/users/not-a-uuid/permissions", headers=h)).status_code == 422
    bad_bodies = [
        {},
        {"overrides": [_override("payments.fly", "allow")]},
        {"overrides": [_override("nonsense.view", "deny")]},
        {"overrides": [_override("payments.view", "maybe")]},
        {"overrides": [_override("payments.view", "allow", reason="   ")]},
        {"overrides": [_override("payments.view", "allow", reason="x" * 501)]},
        {"overrides": [_override("payments.view", "allow"), _override("payments.view", "deny")]},
        {"overrides": [_override("payments.view", "allow", expires_at=_later(hours=-1))]},
        {"overrides": [_override("payments.view", "allow", expires_at="2030-01-01T00:00:00")]},  # no timezone
        {"overrides": [{**_override("payments.view", "allow"), "extra": 1}]},
    ]
    for body in bad_bodies:
        response = await client.put(_path(user), json=body, headers=h)
        assert response.status_code == 422, body
    assert await permissions.user_grants(db_session, user) == []


@pytest.mark.asyncio
async def test_super_admin_users_cannot_carry_overrides(client, db_session):
    root, other_root = await _user(db_session, "super_admin"), await _user(db_session, "super_admin")
    body = (await client.get(_path(other_root), headers=_headers(root))).json()
    assert body["editable"] is False and set(body["effective"]) == set(rbac.all_keys())
    refused = await _put(client, root, other_root, _override("payments.view", "deny"))
    assert refused.status_code == 409
    assert (await client.get(f"{API}/admin/payments", headers=_headers(other_root))).status_code == 200


@pytest.mark.asyncio
async def test_a_change_is_audited_and_a_no_op_writes_nothing(client, db_session):
    root, user = await _user(db_session, "super_admin"), await _user(db_session, "trainer")
    first = await _put(client, root, user, _override("payments.view", "allow", "Cover"))
    assert first.status_code == 200
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == AUDIT, AuditLog.entity_id == str(user.id)))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == root.id and row.entity_type == "user"
    assert row.metadata_json["before"] == [] and [o["permission"] for o in row.metadata_json["after"]] == ["payments.view"]
    stored = await db_session.scalar(select(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id))
    assert stored.created_by_id == root.id and stored.reason == "Cover"
    assert (await _put(client, root, user, _override("payments.view", "allow", "Cover"))).status_code == 200
    assert len((await db_session.scalars(select(AuditLog).where(AuditLog.action == AUDIT, AuditLog.entity_id == str(user.id)))).all()) == 1
    # A changed reason is a real change; clearing removes the override.
    assert (await _put(client, root, user, _override("payments.view", "allow", "Cover till Friday"))).status_code == 200
    cleared = await _put(client, root, user)
    assert cleared.status_code == 200 and cleared.json()["overrides"] == []
    assert len((await db_session.scalars(select(AuditLog).where(AuditLog.action == AUDIT, AuditLog.entity_id == str(user.id)))).all()) == 3
    assert (await client.get(f"{API}/admin/payments", headers=_headers(user))).status_code == 403
