"""AGN-018 (DEC-SCOPE-062) -- the agency dashboard endpoint: hand-counted KPIs, staff scope, gate, header (spec §8)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world, mk_application
from tests.agn017_helpers import deactivate, set_org_status
from tests.agn018_helpers import DASHBOARD_API, MASTER, S1, S2, S3, dashboard_world, mk_place

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


# --- breakdowns, staff table, commission ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breakdowns_by_country_and_university(world):
    body = (await _get(world["master"].email)).json()
    assert body["by_country"] == {"items": [{"label": "Aland", "count": 4}, {"label": "Betaland", "count": 3}], "other": 0}
    assert body["by_university"] == {"items": [{"label": "Alpha University", "count": 4}, {"label": "Beta University", "count": 3}], "other": 0}
    s2 = (await _get(world["s2"]["user"].email)).json()
    assert s2["by_country"] == {"items": [{"label": "Aland", "count": 1}], "other": 0}


@pytest.mark.asyncio
async def test_breakdown_keeps_ten_and_sums_the_rest(db_session):
    ctx = await mk_active_org(db_session)
    record = await mk_record(db_session, agent=ctx["master"], full_name="Many")
    for i in range(12):
        place = await mk_place(db_session, university=f"Uni {i:02d}", country=f"Country {i:02d}")
        for _ in range(2 if i < 3 else 1):
            await mk_application(db_session, agent=ctx["master"], university=place, record=record)
    body = (await _get(ctx["master"].email)).json()
    items = body["by_university"]["items"]
    assert len(items) == 10 and [i["label"] for i in items[:4]] == ["Uni 00", "Uni 01", "Uni 02", "Uni 03"]
    assert body["by_university"]["other"] == 2 and sum(i["count"] for i in items) + 2 == body["applications"] == 15


@pytest.mark.asyncio
async def test_staff_rows_equal_each_members_own_dashboard(world):
    body = (await _get(world["master"].email)).json()
    rows = {r["name"]: r for r in body["staff"]}
    assert list(rows) == ["Staff One", "Staff Two", "Staff Three"] and body["unassigned_students"] == 1
    fields = ("students", "applications", "offers", "enrollments")
    for key in ("s1", "s2", "s3"):
        own = (await _get(world[key]["user"].email)).json()
        row = rows[world[key]["user"].full_name]
        assert row["code"] == world[key]["member"].code and row["active"] is True
        assert {k: row[k] for k in fields} == {k: own[k] for k in fields}


@pytest.mark.asyncio
async def test_staff_row_counts_an_application_once(db_session):
    """Review Focus 1: an application reachable through the agency record AND the linked login counts once."""
    w = await agency_world(db_session)
    await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"], status="offer")
    body = (await _get(w["master"].email)).json()
    row = next(r for r in body["staff"] if r["code"] == w["staff"]["member"].code)
    assert row["applications"] == 1 and row["offers"] == 1


@pytest.mark.asyncio
async def test_deactivated_staff_row(world, db_session):
    """Review Focus 2: shown (inactive) while they still hold active students; gone once they hold none."""
    await deactivate(db_session, world["s1"]["member"])
    await deactivate(db_session, world["s3"]["member"])
    rows = {r["name"]: r for r in (await _get(world["master"].email)).json()["staff"]}
    assert rows["Staff One"]["active"] is False and "Staff Three" not in rows


@pytest.mark.asyncio
async def test_commission_is_per_currency(world):
    """Review Focus 4: never summed across currencies; the noise agency's paid commission is not here."""
    commission = (await _get(world["master"].email)).json()["commission"]
    assert commission == {
        "claimable": [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 200.0}],
        "claims": 1,
        "revenue": [{"currency": "INR", "count": 1, "amount": 12000.0}, {"currency": "USD", "count": 1, "amount": 500.0}],
    }
