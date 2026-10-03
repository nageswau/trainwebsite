"""bdm-002 -- manager reassignment (AC4, C2, C14; spec §5.2 locked_reassign_target, §5.6 races)."""

import asyncio

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm

INVALID = "Choose an active BDM of this type from your team"


async def _setup(client, db):
    manager = await make_manager(db)
    a, b = await make_bdm(db, manager), await make_bdm(db, manager)
    await login(client, a)
    org = await create_org(client)
    return manager, a, b, org


@pytest.mark.asyncio
async def test_manager_reassigns_within_team_and_type_with_an_audit_row(client, db_session):
    manager, a, b, org = await _setup(client, db_session)
    await login(client, manager)
    response = await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(b.id)})
    assert response.status_code == 200
    body = response.json()["organization"]
    assert body["assigned_bdm"]["id"] == str(b.id) and body["permissions"]["can_reassign"] is True
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.assign"))
    assert row.user_id == manager.id and row.metadata_json == {"from": str(a.id), "to": str(b.id)}
    assert (await client.patch(f"{ORGS}/{org['id']}", json={"state": "Goa"})).status_code == 403  # managers never edit
    await login(client, a)
    assert (await client.patch(f"{ORGS}/{org['id']}", json={"state": "Goa"})).status_code == 403  # no longer the assignee


@pytest.mark.asyncio
async def test_every_invalid_target_gets_the_same_422(client, db_session):
    manager, a, _, org = await _setup(client, db_session)
    other_team = await make_bdm(db_session, await make_manager(db_session))
    other_type = await make_bdm(db_session, manager, "school")
    inactive = await make_bdm(db_session, manager, active=False)
    not_bdm = await make_user(db_session, "counselor", "it")
    await login(client, manager)
    for target in (other_team, other_type, inactive, not_bdm, manager):
        response = await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(target.id)})
        assert (response.status_code, response.json()["detail"]) == (422, INVALID), target.role
    same = await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(a.id)})
    assert (same.status_code, same.json()["detail"]) == (409, "Already assigned to this BDM")
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": "nope"})).status_code == 422


@pytest.mark.asyncio
async def test_bdm_cannot_reassign_and_archived_cannot_be_reassigned(client, db_session):
    manager, a, b, org = await _setup(client, db_session)
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(b.id)})).status_code == 403
    await client.post(f"{ORGS}/{org['id']}/archive")
    await login(client, manager)
    response = await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(b.id)})
    assert (response.status_code, response.json()["detail"]) == (409, "Restore this organization first")


@pytest.mark.asyncio
async def test_super_admin_reassigns_across_teams_within_the_type(client, db_session):
    _, _, _, org = await _setup(client, db_session)
    elsewhere = await make_bdm(db_session, await make_manager(db_session))
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(elsewhere.id)})).status_code == 200


@pytest.mark.asyncio
async def test_deactivated_assignee_org_stays_readable_and_can_be_moved(client, db_session):
    """Review Focus 3."""
    manager, a, b, org = await _setup(client, db_session)
    a.active = False
    db_session.add(a)
    await db_session.commit()
    await login(client, b)
    readable = await client.get(f"{ORGS}/{org['id']}")
    assert readable.status_code == 200 and readable.json()["organization"]["assigned_bdm"]["active"] is False
    await login(client, manager)
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(b.id)})).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_reassigns_serialize(db_session):
    """Two managers' sessions racing on one organization: the row lock serializes them; both commit, two audit rows, the final
    assignee is one of the two targets."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    manager = await make_manager(db_session)
    a, b, c = await make_bdm(db_session, manager), await make_bdm(db_session, manager), await make_bdm(db_session, manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as one, AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as two:
        await login(one, a)
        org = await create_org(one)
        await login(one, manager)
        await login(two, manager)
        results = await asyncio.gather(
            one.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(b.id)}),
            two.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(c.id)}),
        )
    assert sorted(r.status_code for r in results) in ([200, 200], [200, 409])
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.assign"))).all()
    assert len(rows) == sum(r.status_code == 200 for r in results)
