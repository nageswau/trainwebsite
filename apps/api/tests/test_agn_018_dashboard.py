"""AGN-018 (DEC-SCOPE-060) -- the agency dashboard endpoint: hand-counted KPIs, staff scope, gate, header (spec §8)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn017_helpers import deactivate, set_org_status
from tests.agn018_helpers import DASHBOARD_API, MASTER, S1, S2, S3, dashboard_world

KEYS = list(MASTER)
CRM = "/api/v1/workflows/overseas/agent/crm"


@pytest_asyncio.fixture
async def world(db_session):
    return await dashboard_world(db_session)


async def _get(email, url=DASHBOARD_API, **params):
    async with client_for(email) as c:
        response = await c.get(url, params=params)
    assert response.status_code == 200, response.text
    return response


def _counts(body):
    return {k: body[k] for k in KEYS}


@pytest.mark.asyncio
async def test_master_counts_equal_hand_counts(world):
    body = (await _get(world["master"].email)).json()
    assert body["scope"] == "agency" and _counts(body) == MASTER
    assert body["member_code"] == world["member"].code and body["reports_available"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "expected"), [("s1", S1), ("s2", S2), ("s3", S3)])
async def test_staff_counts_only_their_students(world, who, expected):
    body = (await _get(world[who]["user"].email)).json()
    assert body["scope"] == "own" and _counts(body) == expected
    assert body["reports_available"] is False  # AGN-003: off for staff until their Master switches it on


@pytest.mark.asyncio
async def test_staff_response_has_no_master_fields(world):
    response = await _get(world["s1"]["user"].email)
    body = response.json()
    assert body["staff"] is None and body["unassigned_students"] is None and body["commission"] is None
    assert "commission" not in response.text.replace('"commission":null', "")


@pytest.mark.asyncio
async def test_staff_cannot_select_the_agency_variant(world):
    """Review Focus 3: the variant comes only from the caller's membership."""
    body = (await _get(world["s1"]["user"].email, scope="agency", role="master")).json()
    assert body["scope"] == "own" and _counts(body) == S1


@pytest.mark.asyncio
async def test_no_store_and_no_uuids(world):
    response = await _get(world["master"].email)
    assert response.headers["cache-control"] == "private, no-store"
    for value in (world["master"].id, world["s1"]["member"].id, world["s1"]["user"].id, world["apps"]["a1"].id, world["u1"].id):
        assert str(value) not in response.text


@pytest.mark.asyncio
async def test_empty_agency_is_zeros(db_session):
    ctx = await mk_active_org(db_session)
    body = (await _get(ctx["master"].email)).json()
    assert _counts(body) == dict.fromkeys(KEYS, 0)
    assert body["by_country"] == {"items": [], "other": 0} and body["by_university"] == {"items": [], "other": 0}
    assert body["staff"] == [] and body["unassigned_students"] == 0
    assert body["commission"] == {"claimable": [], "claims": 0, "revenue": []}


@pytest.mark.asyncio
async def test_refusals(db_session, client):
    assert (await client.get(DASHBOARD_API)).status_code == 401
    for role, division in (("super_admin", "global"), ("counselor", "overseas")):
        user = await mk_user(db_session, role=role, division=division)
        async with client_for(user.email) as c:
            assert (await c.get(DASHBOARD_API)).status_code == 403, role
    ctx = await mk_active_org(db_session)
    async with client_for(ctx["master"].email) as c:
        await set_org_status(db_session, ctx["org"], "suspended")
        assert (await c.get(DASHBOARD_API)).status_code == 403


@pytest.mark.asyncio
async def test_deactivated_member_is_refused(world, db_session):
    async with client_for(world["s1"]["user"].email) as c:
        await deactivate(db_session, world["s1"]["member"])
        assert (await c.get(DASHBOARD_API)).status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "s1"])
async def test_linked_kpis_equal_their_list_totals(world, who):
    email = world["master"].email if who == "master" else world[who]["user"].email
    body = (await _get(email)).json()

    async def total(path, **params):
        return (await _get(email, f"{CRM}/{path}", limit=1, **params)).json()["total"]

    assert await total("students") == body["students"]
    assert await total("applications") == body["applications"]
    assert await total("applications", status="enrolled") == body["enrollments"]
    assert await total("documents", view="pending") == body["pending_documents"]
    assert await total("tasks", view="open") == body["pending_actions"]
