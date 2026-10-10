"""upc-001 -- partnership reads, the manager's phone self-edit, the admin list and the head picker (spec §5; AC4, N3, PU3)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc001_helpers import USERS, as_role, create_manager, login, make_head, sign_in_as_created

ME, PROFILE, TEAM = "/api/v1/partnership/me", "/api/v1/partnership/profile", "/api/v1/partnership/head/team"
ADMIN_LIST, HEADS = "/api/v1/admin/partnership-managers", "/api/v1/admin/partnership-heads"


async def _manager(client, db, head, **overrides):
    await as_role(client, db, "super_admin", "global")
    response = await create_manager(client, head.id, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


# --- /partnership/me + profile ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_own_profile(client, db_session):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    await sign_in_as_created(client, db_session, created)
    body = (await client.get(ME)).json()
    assert body["id"] == created["id"] and body["division"] == "overseas"
    assert body["partnership_profile"]["employee_id"] == created["partnership_profile"]["employee_id"]
    assert body["partnership_profile"]["reporting_head"] == {"id": str(head.id), "full_name": head.full_name, "active": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("partnership_head", "global"), ("counselor", "overseas"), ("overseas_admin", "overseas")])
async def test_other_roles_cannot_read_me(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(ME)
    assert response.status_code == 403 and response.json()["detail"] == "Partnership manager role required"


@pytest.mark.asyncio
async def test_manager_without_profile_is_403(client, db_session):
    await as_role(client, db_session, "partnership_manager", "overseas")
    response = await client.get(ME)
    assert response.status_code == 403 and "not set up" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manager_sets_and_clears_phone_with_a_value_free_audit(client, db_session):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    user = await sign_in_as_created(client, db_session, created)
    response = await client.patch(PROFILE, json={"phone": "  +91 98765 43210 "})
    assert response.status_code == 200 and response.json()["phone"] == "+91 98765 43210"
    assert (await client.patch(PROFILE, json={"phone": ""})).json()["phone"] is None
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "partnership.profile_update"))
    assert row.metadata_json == {"fields": ["phone"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"phone": "call me"}, {"employee_id": "X"}, {"phone": "1", "full_name": "X"}])
async def test_profile_patch_accepts_only_a_valid_phone(client, db_session, body):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    await sign_in_as_created(client, db_session, created)
    assert (await client.patch(PROFILE, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_generic_account_form_cannot_change_a_managers_name(client, db_session):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    await sign_in_as_created(client, db_session, created)
    refused = await client.patch("/api/v1/auth/me", json={"full_name": "Someone Else"})
    assert refused.status_code == 403 and refused.json()["detail"].startswith("Partnership managers can change only their phone")
    allowed = await client.patch("/api/v1/auth/me", json={"full_name": "Rahul Partnerships", "phone": "+91 1"})
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_other_role_cannot_patch_partnership_profile(client, db_session):
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.patch(PROFILE, json={"phone": "1"})).status_code == 403


# --- AC4 / N3: head team ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_sees_only_direct_reports_including_inactive(client, db_session):
    h1, h2 = await make_head(db_session), await make_head(db_session)
    mine = await _manager(client, db_session, h1)
    inactive = await _manager(client, db_session, h1)
    await client.patch(f"{USERS}/{inactive['id']}", json={"active": False})
    theirs = await _manager(client, db_session, h2)
    await login(client, h1)
    body = (await client.get(TEAM, params={"limit": 100})).json()
    ids = {row["id"] for row in body["items"]}
    assert {mine["id"], inactive["id"]} == ids and theirs["id"] not in ids and body["total"] == 2
    assert {row["active"] for row in body["items"]} == {True, False}
    assert set(body["items"][0]) == {"id", "full_name", "email", "phone", "active", "employee_id", "work"}  # upc-032 RA14 adds `work`


@pytest.mark.asyncio
async def test_super_admin_sees_every_manager_on_the_team_route(client, db_session):
    h1, h2 = await make_head(db_session), await make_head(db_session)
    a, b = await _manager(client, db_session, h1), await _manager(client, db_session, h2)
    for created in (a, b):
        found = (await client.get(TEAM, params={"q": created["partnership_profile"]["employee_id"]})).json()
        assert [row["id"] for row in found["items"]] == [created["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("partnership_manager", "overseas"), ("overseas_admin", "overseas"), ("telecaller_manager", "global")])
async def test_non_heads_get_403_on_the_team_route(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(TEAM)
    assert response.status_code == 403 and response.json()["detail"] == "Partnership head role required"


# --- admin list + head picker -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("overseas_admin", "overseas")])
async def test_admin_list_shows_head_and_head_active(client, db_session, role, division):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    head.active = False
    await db_session.commit()
    await as_role(client, db_session, role, division)
    body = (await client.get(ADMIN_LIST, params={"q": created["partnership_profile"]["employee_id"]})).json()
    assert body["total"] == 1 and body["limit"] == 50 and body["offset"] == 0
    row = body["items"][0]
    assert row["reporting_head"] == {"id": str(head.id), "full_name": head.full_name, "active": False} and row["head_active"] is False


@pytest.mark.asyncio
async def test_admin_list_filters_active(client, db_session):
    head = await make_head(db_session)
    created = await _manager(client, db_session, head)
    await client.patch(f"{USERS}/{created['id']}", json={"active": False})
    q = created["partnership_profile"]["employee_id"]
    assert (await client.get(ADMIN_LIST, params={"q": q, "active": "true"})).json()["total"] == 0
    assert (await client.get(ADMIN_LIST, params={"q": q, "active": "false"})).json()["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [ADMIN_LIST, HEADS])
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("partnership_head", "global"), ("partnership_manager", "overseas"), ("counselor", "overseas")])
async def test_admin_reads_refuse_other_roles(client, db_session, url, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(url)).status_code == 403


@pytest.mark.asyncio
async def test_head_picker_lists_active_heads_only_and_searches(client, db_session):
    name = "Picker Head Zq"
    active, inactive = await make_head(db_session, name=name), await make_head(db_session, active=False, name=name)
    await as_role(client, db_session, "overseas_admin", "overseas")
    body = (await client.get(HEADS, params={"q": "picker head zq"})).json()
    ids = {row["id"] for row in body["items"]}
    assert str(active.id) in ids and str(inactive.id) not in ids
    assert set(body["items"][0]) == {"id", "full_name", "email"}


@pytest.mark.asyncio
async def test_pagination_bounds_are_validated(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(ADMIN_LIST, params={"limit": 101})).status_code == 422
    assert (await client.get(ADMIN_LIST, params={"offset": -1})).status_code == 422
