"""bdm-001 -- read routes (spec §5.7; AC06, AC10, AC11, AC15, AC16)."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import User
from tests.bdm001_helpers import PASSWORD, create_bdm, login, make_manager, make_user

ME, TEAM, BDMS, MANAGERS = "/api/v1/bdm/me", "/api/v1/bdm/manager/team", "/api/v1/admin/bdms", "/api/v1/admin/bdm-managers"


async def _team_of_two(client, db):
    """Manager M1 with 2 BDMs (one deactivated), manager M2 with 1. Leaves the client signed in as a super_admin."""
    m1, m2 = await make_manager(db), await make_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    a = (await create_bdm(client, m1.id)).json()
    b = (await create_bdm(client, m1.id, bdm_type="agent")).json()
    c = (await create_bdm(client, m2.id, bdm_type="school")).json()
    # bdm-025: PATCH no longer deactivates a BDM (the handover dialog does); this setup only needs an inactive BDM row.
    await _set_active(db, b["id"], False)
    return m1, m2, a, b, c


async def _set_active(db, user_id, active: bool) -> None:
    user = await db.get(User, uuid.UUID(str(user_id)))
    user.active = active
    await db.commit()


async def _sign_in_as_created(client, db, created: dict) -> User:
    """An admin-created BDM has an unusable password; give it the test password so it can sign in."""
    user = await db.scalar(select(User).where(User.id == uuid.UUID(created["id"])))
    user.password_hash = hash_password(PASSWORD)
    await db.commit()
    await login(client, user)
    return user


@pytest.mark.asyncio
async def test_manager_team_is_exactly_their_reports(client, db_session):
    m1, _, a, b, c = await _team_of_two(client, db_session)
    await login(client, m1)
    body = (await client.get(TEAM)).json()
    assert body["total"] == 2
    assert {r["id"] for r in body["items"]} == {a["id"], b["id"]}
    assert {r["id"]: r["active"] for r in body["items"]} == {a["id"]: True, b["id"]: False}
    assert set(body["items"][0]) == {"id", "full_name", "email", "phone", "active", "bdm_type", "employee_id", "designation", "department", "territory"}


@pytest.mark.asyncio
async def test_super_admin_sees_every_bdm_in_team_route(client, db_session):
    _, _, a, b, c = await _team_of_two(client, db_session)
    ids = set()
    offset = 0
    while True:
        page = (await client.get(TEAM, params={"limit": 100, "offset": offset})).json()
        ids |= {r["id"] for r in page["items"]}
        offset += 100
        if offset >= page["total"]:
            break
    assert {a["id"], b["id"], c["id"]} <= ids


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("bdm", "it"), ("counselor", "overseas"), ("it_admin", "it")])
async def test_team_route_refuses_other_roles(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(TEAM)).status_code == 403


@pytest.mark.asyncio
async def test_bdm_me_returns_own_profile_only(client, db_session):
    m1, _, a, _, _ = await _team_of_two(client, db_session)
    await _sign_in_as_created(client, db_session, a)
    body = (await client.get(ME)).json()
    assert set(body) == {"id", "full_name", "email", "phone", "active", "division", "bdm_profile"}
    assert body["id"] == a["id"] and body["division"] == "it"
    assert body["bdm_profile"]["employee_id"] == a["bdm_profile"]["employee_id"]
    assert body["bdm_profile"]["reporting_manager"] == {"id": str(m1.id), "full_name": m1.full_name, "active": True}


@pytest.mark.asyncio
async def test_bdm_me_without_profile_and_other_roles_are_403(client, db_session):
    await login(client, await make_user(db_session, "bdm", "it"))
    response = await client.get(ME)
    assert response.status_code == 403 and "not set up" in response.json()["detail"]
    await login(client, await make_manager(db_session))
    assert (await client.get(ME)).status_code == 403


@pytest.mark.asyncio
async def test_admin_bdms_scoped_by_creator_types_and_flags_inactive_manager(client, db_session):
    _, m2, a, _, c = await _team_of_two(client, db_session)
    await _set_active(db_session, m2.id, False)  # bdm-025: a manager with BDMs is no longer deactivated through PATCH (legacy state)
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    school = (await client.get(BDMS, params={"bdm_type": "school", "limit": 100})).json()
    rows = {r["id"]: r for r in school["items"]}
    assert all(r["bdm_type"] == "school" for r in school["items"])
    assert rows[c["id"]]["manager_active"] is False and rows[c["id"]]["reporting_manager"]["active"] is False
    every = (await client.get(BDMS, params={"limit": 100})).json()["items"]
    assert all(r["bdm_type"] in ("agent", "school") for r in every)
    assert a["id"] not in {r["id"] for r in every}
    assert (await client.get(BDMS, params={"bdm_type": "college"})).status_code == 403
    assert (await client.get(BDMS, params={"bdm_type": "it"})).status_code == 422
    inactive = (await client.get(BDMS, params={"active": "false", "limit": 100})).json()["items"]
    assert inactive and all(r["active"] is False for r in inactive)


@pytest.mark.asyncio
async def test_admin_bdms_refuses_non_admins(client, db_session):
    await login(client, await make_manager(db_session))
    assert (await client.get(BDMS)).status_code == 403


@pytest.mark.asyncio
async def test_manager_picker_lists_active_managers_with_email(client, db_session):
    """QA-03 (owner, 2026-10-02): same-name managers are told apart by email, shown as a detail line."""
    inactive = await make_manager(db_session, active=False)
    inactive_id = inactive.id
    await login(client, await make_user(db_session, "it_admin", "it"))
    body = (await client.get(MANAGERS, params={"limit": 100})).json()
    assert str(inactive_id) not in {r["id"] for r in body["items"]}
    assert body["items"] and all(set(r) == {"id", "full_name", "email", "bdm_count"} for r in body["items"])  # bdm-025 adds bdm_count
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get(MANAGERS)).status_code == 403


@pytest.mark.asyncio
async def test_manager_picker_search_reaches_any_manager(client, db_session):
    """QA-02: the picker is no longer capped at the first 100 -- `q` matches name or email, literally and case-insensitively."""
    tag = uuid.uuid4().hex[:8]
    target = await make_manager(db_session, name=f"Zz Search {tag}")
    target_id, target_email = str(target.id), target.email
    await make_manager(db_session, name=f"Zz Search {tag}")  # a same-name twin
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    by_name = (await client.get(MANAGERS, params={"q": f"search {tag.upper()}"})).json()
    assert by_name["total"] == 2 and {r["full_name"] for r in by_name["items"]} == {f"Zz Search {tag}"}
    by_email = (await client.get(MANAGERS, params={"q": target_email.upper()})).json()
    assert [r["id"] for r in by_email["items"]] == [target_id]
    assert (await client.get(MANAGERS, params={"q": "%_%"})).json()["total"] == 0  # wildcards are literal, not "match all"
    assert (await client.get(MANAGERS, params={"q": "x" * 201})).status_code == 422


@pytest.mark.asyncio
async def test_admin_bdms_search_by_name_email_or_employee_id_within_scope(client, db_session):
    """QA-04: the admin list can be searched, and the search never widens the caller's type scope."""
    m1, _, a, b, c = await _team_of_two(client, db_session)
    for q in (a["email"].upper(), a["bdm_profile"]["employee_id"].lower()):
        ids = {r["id"] for r in (await client.get(BDMS, params={"q": q, "limit": 100})).json()["items"]}
        assert a["id"] in ids, q
    unique_name = f"Qx Named {uuid.uuid4().hex[:8]}"
    named = (await create_bdm(client, m1.id, full_name=unique_name)).json()
    by_name = (await client.get(BDMS, params={"q": unique_name.lower()})).json()
    assert [r["id"] for r in by_name["items"]] == [named["id"]]
    exact = (await client.get(BDMS, params={"q": a["bdm_profile"]["employee_id"]})).json()
    assert [r["id"] for r in exact["items"]] == [a["id"]] and exact["total"] == 1
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.get(BDMS, params={"q": a["bdm_profile"]["employee_id"]})).json()["total"] == 0  # a College BDM
    assert (await client.get(BDMS, params={"q": c["bdm_profile"]["employee_id"]})).json()["total"] == 1
    assert (await client.get(BDMS, params={"q": "x" * 201})).status_code == 422


@pytest.mark.asyncio
async def test_pages_are_stable_and_shaped(client, db_session):
    m1, _, a, b, _ = await _team_of_two(client, db_session)
    await login(client, m1)
    first = (await client.get(TEAM, params={"limit": 1})).json()
    second = (await client.get(TEAM, params={"limit": 1, "offset": 1})).json()
    assert (first["limit"], first["offset"], first["total"]) == (1, 0, 2)
    assert (second["limit"], second["offset"]) == (1, 1)
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {a["id"], b["id"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_bounds_are_422(client, db_session, params):
    await login(client, await make_user(db_session, "super_admin", "global"))
    for url in (TEAM, BDMS, MANAGERS):
        assert (await client.get(url, params=params)).status_code == 422, url


@pytest.mark.asyncio
async def test_team_filters_by_type_and_search_and_defaults_are_unchanged(client, db_session):
    """bdm-002 (AC8): optional bdm_type / q on the team route, ANDed with team scope."""
    m1, _, a, b, _ = await _team_of_two(client, db_session)
    await login(client, m1)
    assert (await client.get(TEAM)).json()["total"] == 2
    assert [r["id"] for r in (await client.get(TEAM, params={"bdm_type": "agent"})).json()["items"]] == [b["id"]]
    assert [r["id"] for r in (await client.get(TEAM, params={"q": a["bdm_profile"]["employee_id"]})).json()["items"]] == [a["id"]]
    assert (await client.get(TEAM, params={"bdm_type": "it"})).status_code == 422
