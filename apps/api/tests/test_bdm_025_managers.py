"""bdm-025 -- manager change and approvals (AC3), manager deactivation (AC4, L4), PATCH /admin/users refusals (AC1, spec §5.7)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import BdmProfile, Notification, User
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm025_helpers import MANAGERS, as_super, audit_rows, fresh, team, trip

USERS = "/api/v1/admin/users"
APPROVALS = "/api/v1/bdm/manager/approvals"


async def _manager_of(db, bdm_id) -> uuid.UUID:
    return (await db.scalar(select(BdmProfile).where(BdmProfile.user_id == bdm_id).execution_options(populate_existing=True))).reporting_manager_user_id


async def _approve(client, trip_id):
    return await client.post(f"/api/v1/bdm/manager/trips/{trip_id}/approve")


@pytest.mark.asyncio
async def test_patch_deactivating_a_bdm_is_422(client, db_session):
    _, a, _ = await team(db_session)
    await as_super(client, db_session)
    response = await client.patch(f"{USERS}/{a.id}", json={"active": False})
    assert response.status_code == 422
    assert response.json()["detail"] == "Deactivate a BDM from the BDMs page, choosing who takes over their open work"
    assert (await fresh(db_session, User, a.id)).active is True
    assert (await client.patch(f"{USERS}/{a.id}", json={"full_name": "Renamed"})).status_code == 200  # other edits unchanged


@pytest.mark.asyncio
async def test_patch_deactivating_a_manager_with_bdms_is_422(client, db_session):
    manager, _, _ = await team(db_session)
    empty = await make_manager(db_session)
    await as_super(client, db_session)
    response = await client.patch(f"{USERS}/{manager.id}", json={"active": False})
    assert response.status_code == 422
    assert response.json()["detail"] == "This manager has 2 BDMs. Move them to another manager first (BDMs page → BDM managers)"
    assert (await fresh(db_session, User, manager.id)).active is True
    assert (await client.patch(f"{USERS}/{empty.id}", json={"active": False})).status_code == 200


@pytest.mark.asyncio
async def test_manager_deactivate_moves_the_whole_team(client, db_session):
    old, a, b = await team(db_session)
    gone = await make_bdm(db_session, old, active=False)
    new = await make_manager(db_session)
    admin = await as_super(client, db_session)
    response = await client.post(f"{MANAGERS}/{old.id}/deactivate", json={"reassign_to": str(new.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(old.id), "active": False, "moved_bdms": 3}
    for bdm in (a, b, gone):
        assert await _manager_of(db_session, bdm.id) == new.id
    assert (await fresh(db_session, User, old.id)).active is False
    [audit] = await audit_rows(db_session, "bdm_manager.deactivate", old.id)
    assert audit.user_id == admin.id and audit.metadata_json["reassign_to"] == str(new.id)
    assert sorted(audit.metadata_json["moved_bdm_ids"]) == sorted(str(x.id) for x in (a, b, gone))
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == new.id))).all()
    assert note.title == "3 BDMs now report to you" and note.action_url == "/bdm/manager/team"


@pytest.mark.asyncio
async def test_manager_deactivate_refusals(client, db_session):
    old, a, _ = await team(db_session)
    other_inactive = await make_manager(db_session, active=False)
    await as_super(client, db_session)
    url = f"{MANAGERS}/{old.id}/deactivate"
    for body in ({}, {"reassign_to": str(old.id)}, {"reassign_to": str(other_inactive.id)}, {"reassign_to": str(a.id)},
                 {"reassign_to": str(uuid.uuid4())}):
        response = await client.post(url, json=body)
        assert response.status_code == 422 and response.json()["detail"] == "Choose another active BDM manager", body
    assert await _manager_of(db_session, a.id) == old.id
    assert (await client.post(f"{MANAGERS}/{a.id}/deactivate", json={})).status_code == 404
    response = await client.post(f"{MANAGERS}/{other_inactive.id}/deactivate", json={})
    assert response.status_code == 409 and response.json()["detail"] == "This manager is already inactive"
    empty = await make_manager(db_session)
    assert (await client.post(f"{MANAGERS}/{empty.id}/deactivate", json={})).json() == {"id": str(empty.id), "active": False, "moved_bdms": 0}
    for role, division in (("it_admin", "it"), ("overseas_admin", "overseas")):
        client.cookies.clear()
        await login(client, await make_user(db_session, role, division))
        assert (await client.post(url, json={"reassign_to": str((await make_manager(db_session)).id)})).status_code == 403
    client.cookies.clear()
    await login(client, old)
    assert (await client.post(url, json={})).status_code == 403
    assert (await fresh(db_session, User, old.id)).active is True


@pytest.mark.asyncio
async def test_pending_trip_follows_a_manager_change(client, db_session):
    """AC3: the approver is resolved at decision time (bdm-010 T2), so a manager change moves the pending approval."""
    old, a, _ = await team(db_session)
    pending = await trip(db_session, a, approval="submitted")
    new = await make_manager(db_session)
    await as_super(client, db_session)
    response = await client.patch(f"{USERS}/{a.id}", json={"bdm_profile": {"reporting_manager_user_id": str(new.id)}})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    await login(client, old)
    assert str(pending.id) not in {r["id"] for r in (await client.get(APPROVALS)).json()["items"]}
    assert (await _approve(client, pending.id)).status_code == 404
    client.cookies.clear()
    await login(client, new)
    assert str(pending.id) in {r["id"] for r in (await client.get(APPROVALS)).json()["items"]}
    assert (await _approve(client, pending.id)).status_code == 200


@pytest.mark.asyncio
async def test_pending_trip_follows_a_bulk_manager_move(client, db_session):
    old, a, _ = await team(db_session)
    pending = await trip(db_session, a, approval="submitted")
    new = await make_manager(db_session)
    await as_super(client, db_session)
    assert (await client.post(f"{MANAGERS}/{old.id}/deactivate", json={"reassign_to": str(new.id)})).status_code == 200
    client.cookies.clear()
    await login(client, new)
    assert (await _approve(client, pending.id)).status_code == 200


@pytest.mark.asyncio
async def test_manager_list_carries_bdm_count(client, db_session):
    manager, _, _ = await team(db_session)
    await make_bdm(db_session, manager, active=False)
    await as_super(client, db_session)
    rows = {r["id"]: r for r in (await client.get(MANAGERS, params={"q": manager.email, "limit": 5})).json()["items"]}
    assert rows[str(manager.id)]["bdm_count"] == 3
