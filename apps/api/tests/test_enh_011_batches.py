import uuid

import pytest
from enh011_helpers import BATCHES, create_batch, login, skills_world
from sqlalchemy import select

from app.models import AuditLog

# ENH-011 spec §5.1/§5.3: a Career Counselor's batches -- create, list, detail, edit. AC-01, AC-12.


@pytest.mark.asyncio
async def test_counselor_creates_soft_and_digital_batches(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    soft = await create_batch(client, w["a"]["school"].id, title="  Leadership  ", topic="Teamwork", trainer_name="R. Iyer", end_date="2026-12-01")
    digital = await create_batch(client, w["a"]["school"].id, module_type="digital_skills", title="Web design basics")
    assert soft["title"] == "Leadership" and soft["topic"] == "Teamwork" and soft["trainer_name"] == "R. Iyer"
    assert soft["status"] == "open" and soft["enrolled_count"] == 0 and soft["school"] == {"id": str(w["a"]["school"].id), "name": w["a"]["school"].name}
    assert digital["module_type"] == "digital_skills" and digital["end_date"] is None
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_batch_create", AuditLog.entity_id == soft["id"]))).one()
    assert audit.user_id == w["counselor"].id and audit.metadata_json == {"school_id": str(w["a"]["school"].id), "module_type": "soft_skills"}


@pytest.mark.asyncio
async def test_school_outside_portfolio_is_403(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    response = await client.post(BATCHES, json={"school_id": str(w["b"]["school"].id), "module_type": "soft_skills", "title": "X", "start_date": "2026-10-01"})
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["academic", "coordinator", "parent"])
async def test_non_counselor_roles_are_403_before_any_lookup(client, db_session, who):
    w = await skills_world(db_session)
    user = w["academic"] if who == "academic" else w["a"][who]
    await login(client, user.email)
    assert (await client.post(BATCHES, json={})).status_code == 403
    assert (await client.get(BATCHES)).status_code == 403
    assert (await client.get(f"{BATCHES}/{uuid.uuid4()}")).status_code == 403
    assert (await client.patch(f"{BATCHES}/{uuid.uuid4()}", json={"title": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):
    assert (await client.get(BATCHES)).status_code == 401


@pytest.mark.asyncio
async def test_list_is_portfolio_scoped_filtered_and_paged(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor_b"].email)
    await create_batch(client, w["b"]["school"].id, title="B only")
    await login(client, w["counselor"].email)
    first = await create_batch(client, w["a"]["school"].id, title="First")
    second = await create_batch(client, w["a"]["school"].id, module_type="digital_skills", title="Second")
    body = (await client.get(BATCHES)).json()
    assert [i["id"] for i in body["items"]] == [second["id"], first["id"]] and body["total"] == 2 and (body["limit"], body["offset"]) == (25, 0)
    assert [i["id"] for i in (await client.get(BATCHES, params={"module_type": "soft_skills"})).json()["items"]] == [first["id"]]
    await client.patch(f"{BATCHES}/{first['id']}", json={"status": "closed"})
    assert [i["id"] for i in (await client.get(BATCHES, params={"status": "closed"})).json()["items"]] == [first["id"]]
    paged = (await client.get(BATCHES, params={"limit": 1, "offset": 1})).json()
    assert paged["total"] == 2 and [i["id"] for i in paged["items"]] == [first["id"]]
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"module_type": "ielts"}, {"status": "archived"}):
        assert (await client.get(BATCHES, params=bad)).status_code == 422


@pytest.mark.asyncio
async def test_detail_returns_empty_collections_and_outside_portfolio_is_404(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    assert detail["id"] == batch["id"] and detail["enrollments"] == [] and detail["sessions"] == [] and detail["assessments"] == []
    await login(client, w["counselor_b"].email)
    assert (await client.get(f"{BATCHES}/{batch['id']}")).status_code == 404
    assert (await client.patch(f"{BATCHES}/{batch['id']}", json={"title": "x"})).status_code == 404
    assert (await client.get(f"{BATCHES}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_patch_edits_closes_reopens_and_validates(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id, end_date="2026-10-31")
    url = f"{BATCHES}/{batch['id']}"
    edited = (await client.patch(url, json={"title": "Debate", "trainer_name": None, "status": "closed"})).json()
    assert edited["title"] == "Debate" and edited["trainer_name"] is None and edited["status"] == "closed"
    assert (await client.patch(url, json={"status": "open"})).json()["status"] == "open"
    assert (await client.patch(url, json={"school_id": str(w["a"]["school"].id)})).status_code == 422
    assert (await client.patch(url, json={"module_type": "digital_skills"})).status_code == 422
    # A date sent alone is checked against the stored other date.
    assert (await client.patch(url, json={"start_date": "2026-11-01"})).status_code == 422
    assert (await client.patch(url, json={"end_date": "2026-09-01"})).status_code == 422
    assert (await client.patch(url, json={"title": "   "})).status_code == 422
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_batch_update", AuditLog.entity_id == batch["id"]))).all()
