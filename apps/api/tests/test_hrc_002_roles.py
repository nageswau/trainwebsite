"""hrc-002 (DEC-SCOPE-374, spec docs/superpowers/specs/2026-11-04-hrc-002-recruitment-roles-design.md): the HR Manager, Placement Officer
and Interviewer roles -- provisioning (R1), least privilege (R2), own dashboards (R3, AC1), the recruitment grant keys (R4, AC2) and the
two-role edge case (R6)."""

import uuid

import pytest

from app.core import rbac
from app.models import Company, Job, UserRoleAssignment
from tests.bdm001_helpers import PASSWORD, USERS, email, login, make_user
from tests.upc001_helpers import as_role

NEW_ROLES = ("hr_manager", "placement_officer", "interviewer")
SEGMENT = {"hr_manager": "hr-manager", "placement_officer": "placement-officer", "interviewer": "interviewer"}
RECRUITMENT_KEYS = ("jobs.approve", "jobs.publish", "candidates.export", "candidates.import", "candidates.merge", "results.release")


def payload(role: str, **overrides) -> dict:
    body = {"role": role, "division": "it", "email": email(role.replace("_", "-")), "full_name": f"Demo {role}"}
    return body | overrides


def dashboard(role: str) -> str:
    return f"/api/v1/portal/it/{SEGMENT[role]}/dashboard"


# --- R1: provisioning ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", NEW_ROLES)
async def test_super_admin_creates_each_role_and_it_signs_in(client, db_session, role):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=payload(role))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == role and body["division"] == "it"
    reset = await client.post("/api/v1/auth/reset-password", json={"token": body["development_welcome_token"], "new_password": PASSWORD})
    assert reset.status_code == 200, reset.text
    assert reset.json()["login_portal"] is None  # signs in at /it, not /admin
    signed_in = await client.post("/api/v1/auth/login", json={"email": body["email"], "password": PASSWORD, "division": "it"})
    assert signed_in.status_code == 200, signed_in.text
    assert (await client.get(dashboard(role))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("placement_officer", "interviewer"))
async def test_it_admin_creates_officers_and_interviewers(client, db_session, role):
    await as_role(client, db_session, "it_admin", "it")
    response = await client.post(USERS, json=payload(role))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_only_a_super_admin_creates_an_hr_manager(client, db_session):
    await as_role(client, db_session, "it_admin", "it")
    response = await client.post(USERS, json=payload("hr_manager"))
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Only a Super Admin can create HR managers"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", NEW_ROLES)
async def test_new_roles_belong_to_it_only(client, db_session, role):
    await as_role(client, db_session, "super_admin", "global")
    for division in ("overseas", "global"):
        response = await client.post(USERS, json=payload(role, division=division))
        assert response.status_code == 422, response.text


# --- R3 / AC1: own dashboards --------------------------------------------------------------------------------------------------
async def _open_job(db, title: str) -> Job:
    title = f"{title} {uuid.uuid4().hex[:8]}"  # the test database is shared and never truncated
    company = Company(name=f"HRC2 Co {title}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=title, location="Pune", description="x", status="sourcing")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.mark.asyncio
async def test_hr_manager_dashboard_oversees_all_recruitment(client, db_session):
    job = await _open_job(db_session, "HRC2 Manager Role")
    await as_role(client, db_session, "hr_manager", "it")
    body = (await client.get(dashboard("hr_manager"))).json()
    assert body["title"] == "HR Manager Dashboard"
    assert [m["label"] for m in body["metrics"]] == ["Open requirements", "Applications", "Interviews", "Offers"]
    row = next(r for r in body["rows"] if r["role"] == job.title)
    assert row == {"job_id": job.requirement_code, "role": job.title, "company": f"HRC2 Co {job.title}", "location": "Pune", "status": "Sourcing"}


@pytest.mark.asyncio
async def test_placement_officer_dashboard_shows_the_shared_job_id(client, db_session):
    job = await _open_job(db_session, "HRC2 Officer Role")
    await as_role(client, db_session, "placement_officer", "it")
    body = (await client.get(dashboard("placement_officer"))).json()
    assert body["title"] == "Placement Officer Dashboard"
    assert [m["label"] for m in body["metrics"]] == ["Open requirements", "Your candidates"]  # hrc-012 (DEC-SCOPE-382 O3): a count, no candidate field
    assert any(r["job_id"] == job.requirement_code for r in body["rows"])


@pytest.mark.asyncio
async def test_interviewer_dashboard_has_no_data_yet(client, db_session):
    await _open_job(db_session, "HRC2 Interviewer Role")
    await as_role(client, db_session, "interviewer", "it")
    body = (await client.get(dashboard("interviewer"))).json()
    assert body["title"] == "Interviewer Dashboard"
    assert body["rows"] == [] and body["metrics"] == []
    assert body["subtitle"] == "No interviews are assigned to you yet."


@pytest.mark.asyncio
@pytest.mark.parametrize("role", NEW_ROLES)
async def test_a_role_cannot_open_another_roles_portal(client, db_session, role):
    await as_role(client, db_session, role, "it")
    for other in [r for r in NEW_ROLES if r != role]:
        assert (await client.get(dashboard(other))).status_code == 403
    for legacy in ("placement", "hr", "admin"):
        assert (await client.get(f"/api/v1/portal/it/{legacy}/dashboard")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", NEW_ROLES)
async def test_dashboards_have_no_other_sections(client, db_session, role):
    await as_role(client, db_session, role, "it")
    assert (await client.get(f"/api/v1/portal/it/{SEGMENT[role]}/candidates")).status_code == 404


# --- R2: least privilege (the - scenario) ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", NEW_ROLES)
async def test_new_roles_are_refused_candidate_search_and_hold_no_grants(client, db_session, role):
    await as_role(client, db_session, role, "it")
    assert (await client.post("/api/v1/recruiter/candidates/search", json={})).status_code == 403
    assert (await client.get("/api/v1/recruiter/candidates")).status_code == 403
    assert (await client.get("/api/v1/hr/students")).status_code == 403
    me = await client.get("/api/v1/auth/me/permissions")
    assert me.json() == {"role": role, "permissions": list(rbac.DEFAULT_GRANTS.get(role, ()))}  # hrc-007: the HR Manager approves jobs


# --- R4 / AC2: the recruitment grant keys ---------------------------------------------------------------------------------------
def test_catalogue_holds_every_recruitment_key_with_no_default_holder():
    """R4: no default holder until the owning item adds one -- hrc-007 (DEC-SCOPE-380 A12) made the HR Manager the `jobs.approve` holder."""
    keys = rbac.all_keys()
    for key in (*RECRUITMENT_KEYS, "candidates.compensation.view"):
        assert key in keys, key
    # each owning item added its key's default holder, as R4 planned: hrc-007 (DEC-SCOPE-380 A12) jobs.approve, hrc-014 (DEC-SCOPE-377 D3) merge,
    # hrc-008 (DEC-SCOPE-385 V4) jobs.publish, hrc-013 (DEC-SCOPE-391 I1) candidates.import
    owned = {"hr_manager": {"jobs.approve"}, "placement_manager": {"candidates.merge", "jobs.publish", "candidates.import"},
             "placement_team": {"candidates.import"}}  # fmt: skip
    for role, grants in rbac.DEFAULT_GRANTS.items():
        assert set(grants) & set(RECRUITMENT_KEYS) == owned.get(role, set()), role
    extra = {"hr_manager": {"candidates.erase"}}  # hrc-035 (DEC-SCOPE-396 K7): not a hrc-002 recruitment key, but the HR Manager's default
    for role in NEW_ROLES:
        assert role in rbac.ROLES and set(rbac.DEFAULT_GRANTS.get(role, ())) == owned.get(role, set()) | extra.get(role, set())


@pytest.mark.asyncio
async def test_super_admin_grants_jobs_approve_to_hr_manager(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    catalogue = (await client.get("/api/v1/admin/permissions/catalogue")).json()
    assert set(NEW_ROLES) <= set(catalogue["roles"])
    assert {"publish", "export", "import", "merge", "release"} <= set(catalogue["actions"])
    response = await client.put("/api/v1/admin/roles/hr_manager/permissions", json={"permissions": ["jobs.approve"]})
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == ["jobs.approve"]
    manager = await make_user(db_session, "hr_manager", "it")
    await login(client, manager)
    assert (await client.get("/api/v1/auth/me/permissions")).json()["permissions"] == ["jobs.approve"]
    await as_role(client, db_session, "super_admin", "global")
    await client.put("/api/v1/admin/roles/hr_manager/permissions", json={"permissions": list(rbac.DEFAULT_GRANTS["hr_manager"])})  # shared DB: restore


# --- R6: a user holding two roles -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_extra_role_assignment_does_not_widen_recruitment_access(client, db_session):
    interviewer = await make_user(db_session, "interviewer", "it")
    db_session.add(UserRoleAssignment(user_id=interviewer.id, division="it", role="placement_team", is_active=True, approval_status="approved"))
    await db_session.commit()
    await login(client, interviewer)
    assert (await client.post("/api/v1/recruiter/candidates/search", json={})).status_code == 403
    assert (await client.get("/api/v1/portal/it/placement/dashboard")).status_code == 403
    assert (await client.get(dashboard("interviewer"))).status_code == 200
