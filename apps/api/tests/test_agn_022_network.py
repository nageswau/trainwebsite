"""AGN-022 -- Overseas Admin agent network oversight (DEC-SCOPE-063; spec §8)."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AgentStudent, AuditLog, User
from tests.agn001_helpers import login, mk_user
from tests.agn008_helpers import mk_application
from tests.agn022_helpers import APPLICATIONS, COMMISSION, DEPOSITS, DETAIL, NETWORK, ORGS, STUDENTS, ZERO, network_world

FORBIDDEN_KEYS = {"email", "phone", "phone_digits", "date_of_birth", "notes"}


async def _reads(db, org_id, action):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == action))


async def _admin(client, db, role="overseas_admin"):
    admin = await mk_user(db, role=role)
    await login(client, admin.email)
    return admin


def _item(body, org_id):
    return next(i for i in body["items"] if i["id"] == str(org_id))


@pytest.mark.asyncio
async def test_the_list_adds_counts_that_match_the_fixture(client, db_session):  # AC1, AC8
    w = await network_world(db_session)
    await _admin(client, db_session)
    body = (await client.get(ORGS, params={"q": w["org"].prefix, "limit": 100})).json()
    item = _item(body, w["org"].id)
    assert item["staff_count"] == NETWORK["staff_count"]
    assert item["counts"] == {k: NETWORK[k] for k in ("students", "applications", "enrollments")}
    assert set(item) == {"id", "name", "prefix", "status", "created_at", "masters", "staff_count", "counts"}  # existing keys kept


@pytest.mark.asyncio
async def test_other_agencies_and_empty_orgs_count_on_their_own(client, db_session):  # AC1, AC3
    w = await network_world(db_session)
    await _admin(client, db_session)
    empty = _item((await client.get(ORGS, params={"q": w["empty"]["org"].prefix})).json(), w["empty"]["org"].id)
    assert {"staff_count": empty["staff_count"], **empty["counts"]} == ZERO
    noise = _item((await client.get(ORGS, params={"q": w["other"]["org"].prefix})).json(), w["other"]["org"].id)
    assert noise["counts"] == {"students": 1, "applications": 1, "enrollments": 1}  # the noise agency's own rows only


@pytest.mark.asyncio
async def test_the_detail_matches_the_fixture(client, db_session):  # AC1, AC2, AC7
    w = await network_world(db_session)
    await _admin(client, db_session)
    r = await client.get(DETAIL.format(oid=w["org"].id))
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["staff_count"] == NETWORK["staff_count"]
    assert body["counts"] == {k: NETWORK[k] for k in ("students", "applications", "enrollments")}
    assert body["commission"] == COMMISSION and body["deposits"] == DEPOSITS
    assert [m["code"] for m in body["masters"]] == [w["member"].code]
    assert body["status"] == "active" and body["prefix"] == w["org"].prefix
    assert "staff" not in body  # R-API-3: a count, not a name list


@pytest.mark.asyncio
async def test_an_empty_org_is_all_zeros(client, db_session):  # AC3
    w = await network_world(db_session)
    await _admin(client, db_session, role="super_admin")
    body = (await client.get(DETAIL.format(oid=w["empty"]["org"].id))).json()
    assert {"staff_count": body["staff_count"], **body["counts"]} == ZERO
    assert body["commission"] == {"claimable": [], "claims": 0, "revenue": []}
    assert body["deposits"] == {"currency": "INR", "count": 0, "collected": 0.0, "remitted": 0.0, "refunded": 0.0}


@pytest.mark.asyncio
async def test_unknown_and_malformed_org_ids(client, db_session):
    await _admin(client, db_session)
    r = await client.get(DETAIL.format(oid=uuid.uuid4()))
    assert r.status_code == 404 and r.json() == {"detail": "Organisation not found"}
    assert (await client.get(DETAIL.format(oid="not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_students_are_listed_read_only_and_each_read_is_audited(client, db_session):  # AC6, AC7
    w = await network_world(db_session)
    admin = await _admin(client, db_session)
    r = await client.get(STUDENTS.format(oid=w["org"].id), params={"limit": 2})
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["total"] == 4 and len(body["items"]) == 2 and body["limit"] == 2 and body["offset"] == 0
    assert not FORBIDDEN_KEYS & set(body["items"][0])
    archived = (await client.get(STUDENTS.format(oid=w["org"].id), params={"status": "archived"})).json()
    assert archived["total"] == 1 and archived["items"][0]["assigned_code"] == w["s1"]["member"].code and archived["items"][0]["has_login"] is False
    first = await db_session.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(w["org"].id), AuditLog.action == "agent_network.students_read").order_by(AuditLog.created_at).limit(1)
    )
    assert first.user_id == admin.id and first.entity_type == "agent_org" and first.outcome == "read"
    assert first.metadata_json == {"status": "active", "limit": 2, "offset": 0, "returned": 2}
    assert await _reads(db_session, w["org"].id, "agent_network.students_read") == 2


@pytest.mark.asyncio
async def test_student_application_count_ignores_other_agencies(client, db_session):  # Review Focus 1
    w = await network_world(db_session)
    await _admin(client, db_session)
    r2 = await db_session.scalar(select(AgentStudent).where(AgentStudent.agent_id == w["master"].id, AgentStudent.student_id.is_not(None)))
    await mk_application(db_session, agent=w["other"]["master"], university=w["u1"], student=await db_session.get(User, r2.student_id), status="enquiry")
    rows = (await client.get(STUDENTS.format(oid=w["org"].id), params={"limit": 100})).json()["items"]
    assert next(r for r in rows if r["has_login"])["applications"] == 2  # a3, a4 -- never the other agency's row


@pytest.mark.asyncio
async def test_applications_exclude_bridged_and_other_agencies_and_filter_by_stage(client, db_session):  # AC1, AC7
    w = await network_world(db_session)
    await _admin(client, db_session)
    r = await client.get(APPLICATIONS.format(oid=w["org"].id), params={"limit": 100})
    assert r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["total"] == 9  # a1..a8 and a10 (withdrawn rows are listed); the bridged and noise rows are not
    assert not FORBIDDEN_KEYS & set(body["items"][0])
    enrolled = (await client.get(APPLICATIONS.format(oid=w["org"].id), params={"status": "enrolled"})).json()
    assert enrolled["total"] == 1 and enrolled["items"][0]["id"] == str(w["apps"]["a4"].id)
    assert {"student_name", "university", "country", "status", "enrollment_date"} <= set(enrolled["items"][0])
    assert await _reads(db_session, w["org"].id, "agent_network.applications_read") == 2
    legacy = await client.get(APPLICATIONS.format(oid=w["org"].id), params={"status": "offer_received"})
    assert legacy.status_code == 422 and await _reads(db_session, w["org"].id, "agent_network.applications_read") == 2  # Review Focus 3


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [DETAIL, STUDENTS, APPLICATIONS])
async def test_every_new_route_is_admin_only(client, db_session, path):  # AC5
    w = await network_world(db_session)
    url = path.format(oid=w["org"].id)
    assert (await client.get(url)).status_code == 401
    for user in [w["master"], w["s1"]["user"], await mk_user(db_session, role="counselor"), await mk_user(db_session, role="overseas_student")]:
        await login(client, user.email)
        r = await client.get(url)
        assert r.status_code == 403 and r.json() == {"detail": "Overseas Admin role required"}
    assert (await client.get(path.format(oid=uuid.uuid4()))).status_code == 403  # no existence leak
    assert await _reads(db_session, w["org"].id, "agent_network.students_read") == 0
    assert await _reads(db_session, w["org"].id, "agent_network.applications_read") == 0


@pytest.mark.asyncio
async def test_a_failed_audit_write_returns_no_data(client, db_session, monkeypatch):  # AC6: fail closed
    from app.api import admin as admin_api

    w = await network_world(db_session)
    await _admin(client, db_session)
    real = admin_api.AuditLog
    monkeypatch.setattr(admin_api, "AuditLog", lambda **kw: real(**{**kw, "user_id": uuid.uuid4()}))  # FK violation at commit
    with pytest.raises(IntegrityError):
        await client.get(STUDENTS.format(oid=w["org"].id))


@pytest.mark.asyncio
async def test_drill_down_paging_and_filters_are_validated(client, db_session):
    w = await network_world(db_session)
    await _admin(client, db_session)
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "deleted"}):
        assert (await client.get(STUDENTS.format(oid=w["org"].id), params=params)).status_code == 422
    assert (await client.get(STUDENTS.format(oid=uuid.uuid4()))).status_code == 404
    assert await _reads(db_session, w["org"].id, "agent_network.students_read") == 0
