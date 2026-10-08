"""rec-001 -- /recruiter/me, /recruiter/profile, /recruiter/manager/team, /admin/recruiters, /admin/placement-managers (spec §4; AC3–AC6)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.rec001_helpers import as_role, emp, login, make_pm, make_recruiter, make_user

ME, PROFILE, TEAM = "/api/v1/recruiter/me", "/api/v1/recruiter/profile", "/api/v1/recruiter/manager/team"
ADMIN_LIST, PICKER = "/api/v1/admin/recruiters", "/api/v1/admin/placement-managers"


# --- the recruiter's own reads (AC3, AC5) ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_reads_their_own_profile_with_manager(client, db_session):
    manager = await make_pm(db_session)
    employee_id = emp()
    recruiter = await make_recruiter(db_session, manager, employee_id=employee_id)
    await login(client, recruiter)
    response = await client.get(ME)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(recruiter.id) and body["division"] == "it"
    assert body["recruiter_profile"] == {"employee_id": employee_id, "reporting_manager": {"id": str(manager.id), "full_name": manager.full_name, "active": True}}


@pytest.mark.asyncio
async def test_a_backfilled_recruiter_keeps_working_with_no_manager(client, db_session):
    """AC5."""
    recruiter = await make_recruiter(db_session)
    await login(client, recruiter)
    response = await client.get(ME)
    assert response.status_code == 200
    assert response.json()["recruiter_profile"] == {"employee_id": None, "reporting_manager": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("placement_manager", "global"), ("it_admin", "it"), ("it_student", "it")])
async def test_other_roles_cannot_use_recruiter_self_routes(client, db_session, role, division):
    """AC6 / Q-28: hr_team gets nothing new."""
    await as_role(client, db_session, role, division)
    assert (await client.get(ME)).status_code == 403
    assert (await client.patch(PROFILE, json={"phone": "123"})).status_code == 403


@pytest.mark.asyncio
async def test_recruiter_without_a_profile_is_refused(client, db_session):
    recruiter = await make_user(db_session, "placement_team", "it")
    await login(client, recruiter)
    response = await client.get(ME)
    assert response.status_code == 403 and "not set up" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recruiter_edits_only_their_phone_and_the_audit_names_the_field(client, db_session):
    recruiter = await make_recruiter(db_session, employee_id=emp())
    await login(client, recruiter)
    response = await client.patch(PROFILE, json={"phone": "  +91 98765 43210 "})
    assert response.status_code == 200, response.text
    assert response.json()["phone"] == "+91 98765 43210"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter.profile_update", AuditLog.user_id == recruiter.id))
    assert audit.metadata_json == {"fields": ["phone"]}
    assert (await client.patch(PROFILE, json={"phone": "1", "employee_id": "X"})).status_code == 422
    assert (await client.patch(PROFILE, json={"phone": "bad\x00"})).status_code == 422


# --- manager team (AC4) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_sees_only_their_direct_reports(client, db_session):
    manager, other = await make_pm(db_session), await make_pm(db_session)
    mine = await make_recruiter(db_session, manager, employee_id=emp())
    inactive_mine = await make_recruiter(db_session, manager, employee_id=emp(), active=False)
    await make_recruiter(db_session, other, employee_id=emp())
    await make_recruiter(db_session)  # no manager
    await login(client, manager)
    response = await client.get(TEAM)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["id"] for row in body["items"]} == {str(mine.id), str(inactive_mine.id)}
    assert body["total"] == 2 and body["limit"] == 50 and body["offset"] == 0
    narrowed = await client.get(TEAM, params={"q": mine.full_name})
    assert [row["id"] for row in narrowed.json()["items"]] == [str(mine.id)]


@pytest.mark.asyncio
async def test_super_admin_sees_every_recruiter_on_the_team_route(client, db_session):
    recruiter = await make_recruiter(db_session, employee_id=emp())
    await as_role(client, db_session, "super_admin", "global")
    response = await client.get(TEAM, params={"q": recruiter.full_name})
    assert [row["id"] for row in response.json()["items"]] == [str(recruiter.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("placement_team", "it"), ("hr_team", "it"), ("it_admin", "it"), ("telecaller_manager", "global")])
async def test_non_managers_cannot_read_a_team(client, db_session, role, division):
    """Negative: a recruiter calling a manager route → 403."""
    await as_role(client, db_session, role, division)
    assert (await client.get(TEAM)).status_code == 403


# --- admin list + picker --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("it_admin", "it")])
async def test_admin_lists_recruiters_with_manager_or_none(client, db_session, role, division):
    manager = await make_pm(db_session)
    with_manager = await make_recruiter(db_session, manager, employee_id=emp())
    without = await make_recruiter(db_session)
    await as_role(client, db_session, role, division)
    rows = {}
    for recruiter in (with_manager, without):
        page = (await client.get(ADMIN_LIST, params={"q": recruiter.full_name})).json()
        assert page["total"] == 1
        rows[recruiter.id] = page["items"][0]
    assert rows[with_manager.id]["reporting_manager"] == {"id": str(manager.id), "full_name": manager.full_name, "active": True}
    assert rows[without.id]["reporting_manager"] is None and rows[without.id]["employee_id"] is None


@pytest.mark.asyncio
async def test_admin_list_filters_by_active_and_employee_id(client, db_session):
    employee_id = emp()
    inactive = await make_recruiter(db_session, employee_id=employee_id, active=False)
    await as_role(client, db_session, "super_admin", "global")
    assert [r["id"] for r in (await client.get(ADMIN_LIST, params={"q": employee_id.lower()})).json()["items"]] == [str(inactive.id)]
    assert (await client.get(ADMIN_LIST, params={"q": employee_id, "active": "true"})).json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("placement_team", "it"), ("placement_manager", "global"), ("hr_team", "it")])
async def test_admin_routes_refuse_other_roles(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(ADMIN_LIST)).status_code == 403
    assert (await client.get(PICKER)).status_code == 403


@pytest.mark.asyncio
async def test_manager_picker_lists_only_active_placement_managers_with_counts(client, db_session):
    manager = await make_pm(db_session)
    inactive = await make_pm(db_session, active=False)
    await make_recruiter(db_session, manager, employee_id=emp())
    await make_recruiter(db_session, manager, employee_id=emp(), active=False)
    await make_user(db_session, "telecaller_manager", "global", name=manager.full_name + " twin")
    await as_role(client, db_session, "it_admin", "it")
    items = (await client.get(PICKER, params={"q": manager.full_name})).json()["items"]
    assert items == [{"id": str(manager.id), "full_name": manager.full_name, "email": manager.email, "recruiter_count": 2}]
    assert (await client.get(PICKER, params={"q": inactive.full_name})).json()["total"] == 0
