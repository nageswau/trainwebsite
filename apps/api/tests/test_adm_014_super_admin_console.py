"""ADM-014 -- Super Admin cross-division console.

Most of this feature already existed: `apps/web/app/admin/[module]/page.tsx` +
`SUPER_ADMIN_NAV` already cover the full described console (users/students/staff,
programs/batches/universities/recruiters, CMS/blogs/events, leads/applications/payments,
reports/notifications, roles/settings/security-logs/backups) as a single cross-division
view, and `/admin/users`' existing division-scoping (division admins forced to their own
`User.division`, only `super_admin` unrestricted) already satisfies `ADM-014-AC01`/`AC03`
for at least this representative section -- confirmed directly below, not assumed.

The real, confirmed gap, named explicitly in this feature's own AC02 ("a cross-division
privileged action (e.g. security-log export) is itself audit-logged"): no distinct
"security-log export" write action existed anywhere in the codebase -- only the existing
read-only `GET /admin/audit` view (confirmed while building `SEC-001`, deliberately left
out of that feature's scope). Added `POST /admin/audit/export` (Super-Admin-only, unlike
the broader `ensure_admin`-gated read view), which builds a downloadable JSON export via
the same `storage` service pattern `SEC-002`'s GDPR export uses, and self-audit-logs the
export action in the same transaction as the write.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, User


async def _create_user(db_session, *, role: str, division: str, **overrides) -> User:
    defaults = dict(
        email=f"adm014-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, division: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_super_admin_can_export_the_audit_log_and_it_is_self_audit_logged(db_session, client):
    admin = await _create_user(db_session, role="super_admin", division="global")
    await _login(client, admin.email, "global")

    response = await client.post("/api/v1/admin/audit/export")
    assert response.status_code == 201
    body = response.json()
    assert body["url"]
    assert body["row_count"] >= 1

    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "admin.audit_export", AuditLog.user_id == admin.id).order_by(AuditLog.created_at.desc()))
    assert log is not None
    assert log.outcome == "exported"
    assert log.metadata_json["row_count"] == body["row_count"]


@pytest.mark.asyncio
async def test_it_admin_cannot_export_the_audit_log(db_session, client):
    admin = await _create_user(db_session, role="it_admin", division="it")
    await _login(client, admin.email, "it")
    response = await client.post("/api/v1/admin/audit/export")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_cannot_export_the_audit_log(db_session, client):
    admin = await _create_user(db_session, role="overseas_admin", division="overseas")
    await _login(client, admin.email, "overseas")
    response = await client.post("/api/v1/admin/audit/export")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_non_admin_role_cannot_export_the_audit_log(db_session, client):
    student = await _create_user(db_session, role="it_student", division="it")
    await _login(client, student.email, "it")
    response = await client.post("/api/v1/admin/audit/export")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_requires_authentication(client):
    response = await client.post("/api/v1/admin/audit/export")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_division_admin_never_sees_the_other_divisions_users(db_session, client):
    it_admin = await _create_user(db_session, role="it_admin", division="it")
    overseas_only_user = await _create_user(db_session, role="overseas_student", division="overseas")

    await _login(client, it_admin.email, "it")
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(overseas_only_user.id) not in ids
    assert all(row["division"] == "it" for row in response.json())


@pytest.mark.asyncio
async def test_super_admin_sees_both_divisions_users(db_session, client):
    admin = await _create_user(db_session, role="super_admin", division="global")
    it_user = await _create_user(db_session, role="it_student", division="it")
    overseas_user = await _create_user(db_session, role="overseas_student", division="overseas")

    await _login(client, admin.email, "global")
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(it_user.id) in ids
    assert str(overseas_user.id) in ids
