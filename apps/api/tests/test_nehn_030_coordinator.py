"""nehn-030 -- the IT Coordinator role (DEC-ROLE-003; DEC-SCOPE-293; spec docs/superpowers/specs/2026-10-26-nehn-030-coordinator-role-design.md,
RBAC_MATRIX §2.204): provisioning and sign-in (AC1), deny-by-default everywhere else (AC2), the role on the matrix (AC3), and the
Certificates section behind the `certificates.view` grant (AC4)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import delete

from app.core import rbac
from app.models import Certificate, Program, RolePermission
from app.services import permissions
from app.services.provisioning import portal_password_url
from tests.bdm001_helpers import PASSWORD, USERS, email, make_user
from tests.upc001_helpers import as_role

PORTAL = "/api/v1/portal/it/coordinator"
NO_CERTIFICATES = "You do not have permission to view certificates"


def payload(**overrides) -> dict:
    body = {"role": "coordinator", "division": "it", "email": email("coordinator"), "full_name": "Demo Coordinator"}
    body.update(overrides)
    return body


async def _certificate(db) -> Certificate:
    """One issued certificate with a unique number, so the list can be checked for it."""
    tag = uuid.uuid4().hex[:8]
    program = Program(
        slug=f"n030-{tag}",
        title=f"N030 Programme {tag}",
        category="Testing",
        summary="-",
        duration="1 month",
        eligibility="-",
        fees=1000,
        certification="-",
        placement_assistance="-",
        trainer_name="-",
    )
    db.add(program)
    await db.flush()
    student = await make_user(db, "it_student", "it")
    cert = Certificate(
        certificate_no=f"N030-{tag}",
        student_id=student.id,
        program_id=program.id,
        issued_on=date.today(),
        verification_code=f"v{tag}",
        status="issued",
        criteria_snapshot={"eligible": False},
    )
    db.add(cert)
    await db.commit()
    return cert


# --- AC3: the role exists and is born on the matrix ---------------------------------------------------------------------------
def test_coordinator_is_an_it_role_with_only_the_certificate_bundle():
    assert "coordinator" in rbac.ROLES
    assert rbac.PERMISSIONS["coordinator"] == {"it:certificates:read"}
    assert not rbac.has_permission("coordinator", "users:read") and not rbac.has_permission("coordinator", "it:training:manage")


def test_the_catalogue_has_certificates_view_granted_to_the_coordinator_only():
    assert rbac.CATALOGUE["certificates"]["actions"] == ("view", "issue", "override", "configure")  # nehn-031 added issue, override, configure
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "certificates.view" in keys}
    assert holders == {"coordinator"}


# --- AC1: an admin provisions a coordinator, who signs in at /it -------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("actor", "division"), [("it_admin", "it"), ("super_admin", "global")])
async def test_admin_creates_a_coordinator_who_sets_a_password_and_signs_in(client, db_session, actor, division):
    await as_role(client, db_session, actor, division)
    response = await client.post(USERS, json=payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "coordinator" and body["division"] == "it"
    client.cookies.clear()
    reset = await client.post("/api/v1/auth/reset-password", json={"token": body["development_welcome_token"], "new_password": PASSWORD})
    assert reset.status_code == 200, reset.text
    assert reset.json()["login_portal"] is None  # the IT portal's own pages, not /admin
    signed_in = await client.post("/api/v1/auth/login", json={"email": body["email"], "password": PASSWORD, "division": "it"})
    assert signed_in.status_code == 200, signed_in.text
    dashboard = await client.get(f"{PORTAL}/dashboard")
    assert dashboard.status_code == 200, dashboard.text


@pytest.mark.asyncio
async def test_the_welcome_link_opens_the_it_portal(db_session):
    coordinator = await make_user(db_session, "coordinator", "it")
    assert "/it/reset-password" in portal_password_url(coordinator, "t")


@pytest.mark.asyncio
async def test_an_overseas_admin_cannot_create_a_coordinator(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.post(USERS, json=payload())).status_code == 403  # another division
    assert (await client.post(USERS, json=payload(division="overseas"))).status_code == 422  # not an overseas role


@pytest.mark.asyncio
async def test_a_coordinator_cannot_be_created_in_the_global_division(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.post(USERS, json=payload(division="global"))).status_code == 422


# --- AC2: nothing else is open to a coordinator ------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/users"),
        ("post", "/api/v1/admin/users"),
        ("get", "/api/v1/admin/payments"),
        ("get", "/api/v1/admin/roles/coordinator/permissions"),
        ("get", "/api/v1/portal/it/admin/dashboard"),
        ("get", "/api/v1/portal/it/admin/certificates"),
        ("get", "/api/v1/portal/it/trainer/dashboard"),
        ("get", "/api/v1/portal/it/hr/dashboard"),
        ("get", "/api/v1/portal/overseas/coordinator/dashboard"),
    ],
)
async def test_coordinator_is_refused_everywhere_else(client, db_session, method, path):
    await as_role(client, db_session, "coordinator", "it")
    response = await client.request(method, path, json={} if method == "post" else None)
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text[:200]}"


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["users", "students", "attendance", "reports", "nonsense"])
async def test_sections_outside_the_coordinator_portal_are_404(client, db_session, section):
    await as_role(client, db_session, "coordinator", "it")
    assert (await client.get(f"{PORTAL}/{section}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("trainer", "it"), ("it_admin", "it"), ("it_student", "it")])
async def test_other_roles_cannot_open_the_coordinator_portal(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(f"{PORTAL}/certificates")).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(f"{PORTAL}/certificates")).status_code == 401


# --- AC4: the Certificates section follows the grant -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_certificates_section_lists_issued_certificates(client, db_session):
    cert = await _certificate(db_session)
    await as_role(client, db_session, "coordinator", "it")
    response = await client.get(f"{PORTAL}/certificates")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Certificates"
    row = next(r for r in body["rows"] if r["number"] == cert.certificate_no)
    assert row["override"] == "Yes" and row["status"] == "issued"
    dashboard = (await client.get(f"{PORTAL}/dashboard")).json()
    assert dashboard["title"] == "Coordinator Dashboard"
    assert {m["label"] for m in dashboard["metrics"]} == {"Certificates issued", "Issued via override"}


@pytest.mark.asyncio
async def test_revoking_the_grant_closes_certificates_and_empties_the_dashboard(client, db_session):
    await _certificate(db_session)
    await as_role(client, db_session, "coordinator", "it")
    await db_session.execute(delete(RolePermission).where(RolePermission.role == "coordinator", RolePermission.action == "view"))
    await db_session.commit()
    try:
        refused = await client.get(f"{PORTAL}/certificates")
        assert refused.status_code == 403 and refused.json()["detail"] == NO_CERTIFICATES
        dashboard = await client.get(f"{PORTAL}/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["rows"] == [] and dashboard.json()["metrics"] == []
    finally:
        db_session.add(RolePermission(role="coordinator", resource="certificates", action="view"))
        await db_session.commit()
    assert await permissions.has_grant(db_session, "coordinator", "certificates", "view")
    assert (await client.get(f"{PORTAL}/certificates")).status_code == 200
