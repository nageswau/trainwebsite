"""AGN-022 -- Overseas Admin agent network oversight (DEC-SCOPE-063; spec §8)."""

import uuid

import pytest

from tests.agn001_helpers import login, mk_user
from tests.agn022_helpers import COMMISSION, DEPOSITS, DETAIL, NETWORK, ORGS, ZERO, network_world


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
