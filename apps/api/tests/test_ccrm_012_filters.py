"""ccrm-012 (DEC-SCOPE-246 QS6): country / university / intake / stage / sub-status / date-range filters on the overseas Students and
Applications lists -- SQL-side, inside the caller's scope, a bad value 422."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.ccrm012_helpers import PORTAL, search_world


@pytest_asyncio.fixture
async def world(db_session):
    return await search_world(db_session)


async def _ids(c, role="counselor", section="applications", **params):
    r = await c.get(PORTAL.format(role, section), params=params)
    assert r.status_code == 200, r.text
    return r.json(), {str(row["id"]) for row in r.json()["rows"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["applications", "students"])
async def test_each_filter_narrows_the_counselors_list(world, section):
    one, two = str(world["app1"].id), str(world["app2"].id)
    async with client_for(world["a"].email) as c:
        assert (await _ids(c, section=section))[1] == {one, two}
        assert (await _ids(c, section=section, country=str(world["uk"].country_id)))[1] == {one}
        assert (await _ids(c, section=section, university=str(world["ca"].id)))[1] == {two}
        assert (await _ids(c, section=section, intake="Jan 2028"))[1] == {two}
        assert (await _ids(c, section=section, stage="offer"))[1] == {one}
        assert (await _ids(c, section=section, stage="offer", sub_status="conditional_offer"))[1] == {one}
        assert (await _ids(c, section=section, sub_status="unconditional_offer"))[1] == set()
        assert (await _ids(c, section=section, **{"from": "2026-01-01", "to": "2026-01-31"}))[1] == {two}
        assert (await _ids(c, section=section, **{"from": "2026-02-01"}))[1] == {one}
        assert (await _ids(c, section=section, university=str(world["ca"].id), intake="Sep 2027"))[1] == set()


@pytest.mark.asyncio
async def test_a_filter_never_widens_scope(world):
    async with client_for(world["a"].email) as c:
        _, ids = await _ids(c, university=str(world["ca"].id), intake="Sep 2027")  # counselor B's application matches both
    assert str(world["app_b"].id) not in ids


@pytest.mark.asyncio
async def test_options_come_from_the_counselors_own_applications(world):
    async with client_for(world["a"].email) as c:
        data, _ = await _ids(c, stage="offer")
    f = data["filters"]
    assert f["stage"] == "offer" and f["country"] is None and f["from"] is None
    assert {o["value"] for o in f["universities"]} == {str(world["uk"].id), str(world["ca"].id)}
    assert {o["value"] for o in f["countries"]} == {str(world["uk"].country_id), str(world["ca"].country_id)}
    assert [o["value"] for o in f["intakes"]] == ["Jan 2028", "Sep 2027"]
    assert "offer" in [o["value"] for o in f["stages"]] and "withdrawn" in [o["value"] for o in f["stages"]]
    assert {"value": "conditional_offer", "label": "Conditional offer", "stage": "offer"} in f["sub_statuses"]


@pytest.mark.asyncio
async def test_an_admin_option_list_covers_every_application(world):
    async with client_for(world["admin"].email) as c:
        data, ids = await _ids(c, "admin", university=str(world["ca"].id))
    assert {str(world["app2"].id), str(world["app_b"].id)} <= ids and str(world["app1"].id) not in ids
    assert {str(world["uk"].id), str(world["ca"].id)} <= {o["value"] for o in data["filters"]["universities"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "detail"), [
    ({"country": "garbage"}, "Unknown filter value"),
    ({"university": "00000000-0000-0000-0000-000000000000"}, "Unknown filter value"),
    ({"stage": "nowhere"}, "Unknown filter value"),
    ({"sub_status": "nowhere"}, "Unknown filter value"),
    ({"stage": "offer", "sub_status": "visa_applied"}, "Sub-status does not belong to that stage"),
    ({"from": "yesterday"}, "Unknown filter value"),
    ({"from": "2026-03-01", "to": "2026-02-01"}, "The start date must be on or before the end date"),
    ({"intake": "x" * 81}, "Unknown filter value"),
])
async def test_bad_filters_are_refused(world, params, detail):
    async with client_for(world["a"].email) as c:
        r = await c.get(PORTAL.format("counselor", "applications"), params=params)
    assert r.status_code == 422 and r.json()["detail"] == detail


@pytest.mark.asyncio
async def test_new_filters_are_not_available_elsewhere(world):
    async with client_for(world["a"].email) as c:
        r = await c.get(PORTAL.format("counselor", "documents"), params={"stage": "offer"})
        assert r.status_code == 422 and r.json()["detail"] == "Filter not available"
        r = await c.get(f"{PORTAL.format('counselor', 'applications')}?stage=offer&stage=enrolled")
        assert r.status_code == 422 and r.json()["detail"] == "Unknown filter value"
