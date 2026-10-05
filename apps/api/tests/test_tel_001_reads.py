"""tel-001 -- read routes and the phone self-edit (spec §5.7; AC4, TL3)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, User
from tests.tel001_helpers import create_telecaller, login, make_tl_manager, make_user, sign_in_as_created

ME, PROFILE, TEAM = "/api/v1/telecaller/me", "/api/v1/telecaller/profile", "/api/v1/telecaller/manager/team"
ADMIN_LIST, MANAGERS = "/api/v1/admin/telecallers", "/api/v1/admin/telecaller-managers"


async def _teams(client, db):
    """M1 has an IT and an Overseas telecaller (the Overseas one deactivated); M2 has one IT telecaller. Signed in as super_admin."""
    m1, m2 = await make_tl_manager(db), await make_tl_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    a = (await create_telecaller(client, m1.id, team="it")).json()
    b = (await create_telecaller(client, m1.id, team="overseas")).json()
    c = (await create_telecaller(client, m2.id, team="it")).json()
    assert (await client.patch(f"/api/v1/admin/users/{b['id']}", json={"active": False})).status_code == 200
    return m1, m2, a, b, c


async def _all_ids(client, url, **params) -> set:
    ids, offset = set(), 0
    while True:
        page = (await client.get(url, params={"limit": 100, "offset": offset, **params})).json()
        ids |= {r["id"] for r in page["items"]}
        offset += 100
        if offset >= page["total"]:
            return ids


# --- AC4 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_sees_only_direct_reports(client, db_session):
    m1, _, a, b, c = await _teams(client, db_session)
    await login(client, m1)
    body = (await client.get(TEAM)).json()
    assert body["total"] == 2 and {r["id"] for r in body["items"]} == {a["id"], b["id"]}
    assert {r["id"]: r["active"] for r in body["items"]} == {a["id"]: True, b["id"]: False}
    assert set(body["items"][0]) == {"id", "full_name", "email", "phone", "active", "team", "employee_id"}


@pytest.mark.asyncio
async def test_super_admin_sees_every_telecaller_on_the_team_route(client, db_session):
    _, _, a, b, c = await _teams(client, db_session)
    assert {a["id"], b["id"], c["id"]} <= await _all_ids(client, TEAM)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), ("bdm_manager", "global"), ("it_admin", "it")])
async def test_team_route_refuses_other_roles(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(TEAM)
    assert response.status_code == 403


# --- /me and the phone self-edit -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_me_returns_own_profile(client, db_session):
    m1, _, a, _, _ = await _teams(client, db_session)
    await sign_in_as_created(client, db_session, a)
    body = (await client.get(ME)).json()
    assert body["id"] == a["id"] and body["division"] == "it"
    assert body["telecaller_profile"]["reporting_manager"] == {"id": str(m1.id), "full_name": m1.full_name, "active": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("telecaller_manager", "global")])
async def test_me_and_profile_refuse_other_roles(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(ME)).status_code == 403
    assert (await client.patch(PROFILE, json={"phone": "123"})).status_code == 403


@pytest.mark.asyncio
async def test_self_update_sets_and_clears_phone_with_audit(client, db_session):
    _, _, a, _, _ = await _teams(client, db_session)
    await sign_in_as_created(client, db_session, a)
    response = await client.patch(PROFILE, json={"phone": " +91 98765 43210 "})
    assert response.status_code == 200 and response.json()["phone"] == "+91 98765 43210"
    assert (await client.patch(PROFILE, json={"phone": ""})).json()["phone"] is None
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == a["id"], AuditLog.action == "telecaller.profile_update"))).all()
    assert len(rows) == 2 and all(r.metadata_json == {"fields": ["phone"]} for r in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"employee_id": "HACK"}, {"team": "overseas"}, {"reporting_manager_user_id": "00000000-0000-0000-0000-000000000000"}, {"full_name": "X"}])
async def test_self_update_rejects_other_fields(client, db_session, extra):
    _, _, a, _, _ = await _teams(client, db_session)
    user_id = (await sign_in_as_created(client, db_session, a)).id
    before = (await client.get(ME)).json()
    response = await client.patch(PROFILE, json={"phone": "1", **extra})
    assert response.status_code == 422 and response.json()["detail"].startswith("Unknown field: ")
    db_session.expire_all()
    assert (await client.get(ME)).json() == before
    assert (await db_session.get(User, user_id)).phone == before["phone"]


# --- admin list and manager picker --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_list_is_scoped_to_the_admins_team(client, db_session):
    _, _, a, b, c = await _teams(client, db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    ids = await _all_ids(client, ADMIN_LIST)
    assert {a["id"], c["id"]} <= ids and b["id"] not in ids
    assert (await client.get(ADMIN_LIST, params={"team": "overseas"})).status_code == 403
    assert (await client.get(ADMIN_LIST, params={"team": "global"})).status_code == 422


@pytest.mark.asyncio
async def test_admin_list_filters_and_searches(client, db_session):
    _, _, a, b, _ = await _teams(client, db_session)
    found = (await client.get(ADMIN_LIST, params={"q": a["telecaller_profile"]["employee_id"]})).json()
    assert [r["id"] for r in found["items"]] == [a["id"]]
    assert b["id"] in await _all_ids(client, ADMIN_LIST, active="false")
    assert b["id"] not in await _all_ids(client, ADMIN_LIST, active="true")


@pytest.mark.asyncio
async def test_admin_list_flags_inactive_manager(client, db_session):
    m1, _, a, _, _ = await _teams(client, db_session)
    assert (await client.patch(f"/api/v1/admin/users/{m1.id}", json={"active": False})).status_code == 200
    found = (await client.get(ADMIN_LIST, params={"q": a["telecaller_profile"]["employee_id"]})).json()["items"][0]
    assert found["manager_active"] is False and found["reporting_manager"]["active"] is False


@pytest.mark.asyncio
async def test_manager_picker_lists_active_managers_only(client, db_session):
    active, inactive = await make_tl_manager(db_session, name="Picker Active"), await make_tl_manager(db_session, active=False, name="Picker Inactive")
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    ids = await _all_ids(client, MANAGERS)
    assert str(active.id) in ids and str(inactive.id) not in ids
    hit = (await client.get(MANAGERS, params={"q": active.email})).json()["items"]
    assert hit == [{"id": str(active.id), "full_name": "Picker Active", "email": active.email}]
    await login(client, await make_user(db_session, "telecaller", "it"))
    assert (await client.get(MANAGERS)).status_code == 403
