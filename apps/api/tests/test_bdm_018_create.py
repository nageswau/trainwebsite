"""bdm-018 -- creating the School from a request links both ways atomically (spec §5.5; AC2, AC3, AC5)."""

import asyncio
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmOrganization, School, User
from tests.bdm001_helpers import login, make_user
from tests.bdm018_helpers import QUEUE, SCHOOLS, notices, pending_request, requests_of, school_payload


async def _count(db, model, *where) -> int:
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _org(db, org_id: str) -> BdmOrganization:
    db.expire_all()
    return await db.get_one(BdmOrganization, UUID(org_id))


@pytest.mark.asyncio
async def test_creating_from_a_request_links_the_school_and_completes_the_request(client, db_session):
    w = await pending_request(client, db_session)
    payload = school_payload(bdm_onboarding_request_id=w["item"]["id"])
    response = await client.post(SCHOOLS, json=payload)
    assert response.status_code == 201, response.text
    school = response.json()
    assert school["linked_bdm"] == {"full_name": w["owner"].full_name, "active": True, "organization_code": w["org"]["code"]}
    assert str((await _org(db_session, w["org"]["id"])).school_id) == school["id"]
    [row] = await requests_of(db_session, w["org"]["id"])
    assert (row.status, row.resolution, str(row.school_id)) == ("completed", "created", school["id"])
    [notice] = await notices(db_session, w["ids"]["owner"])
    assert notice.title == "School onboarded"


@pytest.mark.asyncio
async def test_a_resolved_request_refuses_before_anything_is_created(client, db_session):
    w = await pending_request(client, db_session)
    await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "Duplicate"})
    payload = school_payload(bdm_onboarding_request_id=w["item"]["id"])
    response = await client.post(SCHOOLS, json=payload)
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "request_resolved")
    assert await _count(db_session, School, School.name == payload["name"]) == 0
    assert await _count(db_session, User, User.email == payload["coordinator_email"]) == 0


@pytest.mark.asyncio
async def test_an_unknown_request_is_404_and_nothing_is_created(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    payload = school_payload(bdm_onboarding_request_id="00000000-0000-0000-0000-000000000000")
    assert (await client.post(SCHOOLS, json=payload)).status_code == 404
    assert await _count(db_session, School, School.name == payload["name"]) == 0


@pytest.mark.asyncio
async def test_a_failed_create_leaves_the_request_pending(client, db_session):
    w = await pending_request(client, db_session)
    taken = await make_user(db_session, "student", "it")
    payload = school_payload(bdm_onboarding_request_id=w["item"]["id"], coordinator_email=taken.email)
    assert (await client.post(SCHOOLS, json=payload)).status_code == 409
    [row] = await requests_of(db_session, w["org"]["id"])
    assert row.status == "pending"
    assert (await _org(db_session, w["org"]["id"])).school_id is None
    assert await _count(db_session, School, School.name == payload["name"]) == 0


@pytest.mark.asyncio
async def test_two_admins_creating_from_one_request_produce_one_school(client, db_session):
    w = await pending_request(client, db_session)
    other_admin = await make_user(db_session, "overseas_admin", "overseas")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second:
        await login(second, other_admin)
        payloads = [school_payload(bdm_onboarding_request_id=w["item"]["id"]) for _ in range(2)]
        responses = await asyncio.gather(client.post(SCHOOLS, json=payloads[0]), second.post(SCHOOLS, json=payloads[1]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    names = [p["name"] for p in payloads]
    assert await _count(db_session, School, School.name.in_(names)) == 1


@pytest.mark.asyncio
async def test_a_create_without_a_request_is_unchanged_and_unlinked(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    response = await client.post(SCHOOLS, json=school_payload(edusphere_bdm="Asha (legacy)"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["linked_bdm"] is None
    assert body["edusphere_bdm"] == "Asha (legacy)"  # H4: the API still accepts the legacy note
