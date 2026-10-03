"""bdm-002 -- contacts (C1, C10; spec §5.3; Review Focus 1)."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmOrganizationContact
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, make_bdm


async def _org(client, db, contacts=None):
    bdm = await make_bdm(db, await make_manager(db))
    await login(client, bdm)
    return bdm, await create_org(client, **({"contacts": contacts} if contacts else {}))


@pytest.mark.asyncio
async def test_add_edit_make_primary_and_delete(client, db_session):
    _, org = await _org(client, db_session)
    base = f"{ORGS}/{org['id']}/contacts"
    added = await client.post(base, json={"name": "Ms Iyer", "role": "placement_officer", "is_primary": True})
    assert added.status_code == 201
    body = added.json()["organization"]
    assert body["primary_contact"]["name"] == "Ms Iyer" and [c["is_primary"] for c in body["contacts"]] == [True, False]
    iyer, rao = body["contacts"]
    assert (await client.patch(f"{base}/{rao['id']}", json={"designation": "Principal (acting)"})).json()["organization"]["contacts"][1]["designation"] == "Principal (acting)"
    assert (await client.patch(f"{base}/{rao['id']}", json={"is_primary": True})).json()["organization"]["primary_contact"]["name"] == "Dr Rao"
    refused = await client.patch(f"{base}/{rao['id']}", json={"is_primary": False})
    assert (refused.status_code, refused.json()["detail"]) == (422, "Choose another primary contact instead")
    deleted = await client.delete(f"{base}/{rao['id']}")  # the primary: Ms Iyer is promoted
    assert deleted.status_code == 200 and deleted.json()["organization"]["primary_contact"]["name"] == "Ms Iyer"


@pytest.mark.asyncio
async def test_last_contact_and_cap(client, db_session):
    _, org = await _org(client, db_session)
    base = f"{ORGS}/{org['id']}/contacts"
    last = await client.delete(f"{base}/{org['contacts'][0]['id']}")
    assert (last.status_code, last.json()["detail"]) == (409, "An organization needs at least one contact")
    for i in range(19):
        assert (await client.post(base, json={"name": f"C{i}"})).status_code == 201
    capped = await client.post(base, json={"name": "C20"})
    assert (capped.status_code, capped.json()["detail"]) == (409, "An organization can have at most 20 contacts")


@pytest.mark.asyncio
async def test_contact_of_another_organization_is_404(client, db_session):
    _, mine = await _org(client, db_session)
    other = await create_org(client)
    response = await client.patch(f"{ORGS}/{mine['id']}/contacts/{other['contacts'][0]['id']}", json={"name": "X"})
    assert (response.status_code, response.json()["detail"]) == (404, "Contact not found")
    assert (await client.delete(f"{ORGS}/{mine['id']}/contacts/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_concurrent_deletes_of_the_last_two_leave_one(db_session):
    """Review Focus 1: the organization row lock serializes the two deletes; exactly one succeeds."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as one, AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as two:
        bdm, org = await _org(one, db_session, contacts=[{"name": "A"}, {"name": "B"}])
        await login(two, bdm)
        base = f"{ORGS}/{org['id']}/contacts"
        results = await asyncio.gather(one.delete(f"{base}/{org['contacts'][0]['id']}"), two.delete(f"{base}/{org['contacts'][1]['id']}"))
    assert sorted(r.status_code for r in results) == [200, 409]
    remaining = await db_session.scalar(select(func.count()).select_from(BdmOrganizationContact).where(BdmOrganizationContact.organization_id == uuid.UUID(org["id"])))
    assert remaining == 1


@pytest.mark.asyncio
async def test_contacts_follow_edit_rights_and_archive(client, db_session):
    bdm, org = await _org(client, db_session)
    other = await make_bdm(db_session, await make_manager(db_session))
    await login(client, other)
    assert (await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "X"})).status_code == 403
    await login(client, bdm)
    await client.post(f"{ORGS}/{org['id']}/archive")
    response = await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "X"})
    assert (response.status_code, response.json()["detail"]) == (409, "Restore this organization first")
