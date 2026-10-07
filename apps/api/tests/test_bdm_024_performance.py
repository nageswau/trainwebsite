"""bdm-024 (DEC-SCOPE-111) -- GET /bdm/manager/performance: the §5 KPI x BDM-type table (Appendix B.6 P-01...P-08) for a period, and with
`type` the BDMs of that type; GET /bdm/manager/performance/bdms/{id}: one BDM's organizations and trips. The levels must agree (AC2)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm024_helpers import EXPECTED, IN, PERIOD, appt, perf_world
from tests.test_bdm_023_dashboard import org_of

PERFORMANCE = "/api/v1/bdm/manager/performance"
TYPES = ["agent", "school", "college"]
FIGURES = ["meetings", "trips", "new_organizations", "mous", "leads", "students", "revenue"]
ROW_FIGURE = {"P-02": "meetings", "P-03": "trips", "P-04": "new_organizations", "P-05": "mous", "P-06": "leads", "P-07": "students",
              "P-08": "revenue"}


def bdm_url(bdm_id) -> str:
    return f"{PERFORMANCE}/bdms/{bdm_id}"


async def read(client, url: str = PERFORMANCE, **params) -> dict:
    response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def table(body: dict) -> dict[str, list]:
    return {row["key"]: [cell["value"] for cell in row["cells"]] for row in body["rows"]}


def total(values) -> int | str:
    """Sum of figures (revenue arrives as decimal strings)."""
    items = list(values)
    if items and isinstance(items[0], str):
        return str(sum((Decimal(v) for v in items), Decimal("0.00")))
    return sum(items)


# --- access (P1) -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_managers_and_super_admin_read_performance(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager)
    await login(client, bdm)
    for url in (PERFORMANCE, bdm_url(bdm.id), "/api/v1/bdm/manager/hierarchy"):
        r = await client.get(url)
        assert (r.status_code, r.json()["detail"]) == (403, "BDM manager role required")
    client.cookies.clear()
    assert (await client.get(PERFORMANCE)).status_code == 401


@pytest.mark.asyncio
async def test_only_super_admin_may_choose_a_manager(client, db_session):
    manager, other = await make_manager(db_session), await make_manager(db_session)
    await login(client, manager)
    r = await client.get(PERFORMANCE, params={"manager_user_id": str(other.id)})
    assert (r.status_code, r.json()["detail"]) == (422, "Only a super admin can choose a manager")
    client.cookies.clear()
    await login(client, await make_user(db_session, "super_admin", "global"))
    r = await client.get(PERFORMANCE, params={"manager_user_id": str(uuid.uuid4())})
    assert (r.status_code, r.json()["detail"]) == (404, "Manager not found")


# --- period (P2) --------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_period_defaults_to_the_current_ist_month(client, db_session):
    from datetime import datetime

    await login(client, await make_manager(db_session))
    body = await read(client)
    today = datetime.now(IST).date()
    assert body["from"] == today.replace(day=1).isoformat()
    assert body["to"][:7] == today.isoformat()[:7] and body["to"] >= today.isoformat()
    assert body["type"] is None and body["bdms"] == [] and body["manager"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "detail"), [
    ({"from": "2025-03-31", "to": "2025-03-01"}, "The period must start on or before its end"),
    ({"to": "2001-01-01"}, "The period must start on or before its end"),  # `from` defaults to this month, after `to`
    ({"from": "2024-01-01", "to": "2025-01-02"}, "The period can be at most 366 days"),
])
async def test_an_invalid_period_is_refused(client, db_session, params, detail):
    await login(client, await make_manager(db_session))
    r = await client.get(PERFORMANCE, params=params)
    assert (r.status_code, r.json()["detail"]) == (422, detail)
    assert (await client.get(PERFORMANCE, params={"from": "not-a-date"})).status_code == 422
    assert (await client.get(PERFORMANCE, params={"type": "telecaller"})).status_code == 422


@pytest.mark.asyncio
async def test_a_full_leap_year_is_allowed(client, db_session):
    await login(client, await make_manager(db_session))
    await read(client, **{"from": "2024-01-01", "to": "2024-12-31"})  # 366 days


# --- AC1 the table, AC3 untracked, AC4 the period ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_table_matches_the_source_rows_and_columns(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    body = await read(client, **PERIOD)
    assert [r["key"] for r in body["rows"]] == list(EXPECTED)
    assert [r["label"] for r in body["rows"]] == ["BDMs", "Meetings", "Travel Trips", "New Organizations", "MoUs", "Leads", "Students", "Revenue"]
    assert all([c["type"] for c in r["cells"]] == TYPES for r in body["rows"])
    assert all(c["definition"] for r in body["rows"] for c in r["cells"])
    assert table(body) == EXPECTED
    assert (body["from"], body["to"]) == (PERIOD["from"], PERIOD["to"])


@pytest.mark.asyncio
async def test_untracked_revenue_is_labelled_not_zero(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    revenue = next(r for r in (await read(client, **PERIOD))["rows"] if r["key"] == "P-08")
    assert [c["tracked"] for c in revenue["cells"]] == [False, False, True]
    assert [c["value"] for c in revenue["cells"][:2]] == [None, None]


@pytest.mark.asyncio
async def test_the_period_filter_changes_the_figures(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    april = table(await read(client, **{"from": "2025-04-01", "to": "2025-04-30"}))
    assert april["P-02"] == [0, 0, 1]  # the meeting just after March
    assert april["P-03"] == [0, 0, 1] and april["P-05"] == [0, 0, 1]
    assert april["P-06"] == [0, 0, 0] and april["P-07"] == [0, 1, 1]  # st2 converted, one school student added
    assert april["P-08"][2] == "700.00"
    assert april["P-01"] == [1, 1, 1]  # P-01 is the team today, not the period


@pytest.mark.asyncio
async def test_a_manager_with_no_bdms_reads_zeros(client, db_session):
    await login(client, await make_manager(db_session))
    rows = table(await read(client, **PERIOD))
    assert all(v in (0, None, "0.00") for values in rows.values() for v in values)
    assert rows["P-08"] == [None, None, "0.00"]


# --- AC2 the drill-down agrees at each level (P8) ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_type_drills_to_its_bdms_and_they_sum_to_the_cell(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    top = await read(client, **PERIOD)
    for column, bdm_type in enumerate(TYPES):
        body = await read(client, **PERIOD, type=bdm_type)
        assert body["type"] == bdm_type
        for key, figure in ROW_FIGURE.items():
            cell = table(top)[key][column]
            values = [b["figures"][figure] for b in body["bdms"]]
            assert (None if cell is None else total(values)) == cell or (cell is None and set(values) == {None}), (bdm_type, key)
        assert table(top)["P-01"][column] == sum(b["active"] for b in body["bdms"])
    agents = (await read(client, **PERIOD, type="agent"))["bdms"]
    assert {b["id"]: (b["active"], b["figures"]["meetings"], b["figures"]["students"]) for b in agents} == {
        str(w["a1"].id): (True, 0, 4), str(w["a2"].id): (False, 1, 0)}


@pytest.mark.asyncio
async def test_a_bdm_drills_to_their_organizations_and_trips(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    row = next(b for b in (await read(client, **PERIOD, type="college"))["bdms"] if b["id"] == str(w["c1"].id))
    body = await read(client, bdm_url(w["c1"].id), **PERIOD)
    assert body["bdm"]["id"] == str(w["c1"].id) and body["bdm"]["bdm_type"] == "college" and body["bdm"]["active"] is True
    assert body["totals"] == row["figures"]
    assert [o["id"] for o in body["organizations"]] == [w["org_c"]["id"]]  # org_c2 has nothing in the period
    org = body["organizations"][0]
    assert org["name"] == w["org_c"]["name"] and org["code"] == w["org_c"]["code"]
    assert org["figures"] == {"meetings": 1, "trips": None, "new_organizations": 1, "mous": 1, "leads": 2, "students": 1, "revenue": "1250.50"}
    assert [t["id"] for t in body["trips"]] == [str(w["trip"].id)]
    assert body["trips"][0]["travel_date"] == "2025-03-05" and body["trips"][0]["code"] == w["trip"].code
    for figure in FIGURES:
        if figure != "trips":
            assert total(o["figures"][figure] for o in body["organizations"]) == body["totals"][figure], figure
    assert body["totals"]["trips"] == len(body["trips"])


@pytest.mark.asyncio
async def test_a_bdm_of_another_team_is_not_found(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, w["manager"])
    for other in (w["x"].id, w["manager"].id, uuid.uuid4()):
        r = await client.get(bdm_url(other), params=PERIOD)
        assert (r.status_code, r.json()["detail"]) == (404, "BDM not found")
    assert (await client.get(bdm_url("not-a-uuid"))).status_code == 422
    client.cookies.clear()
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await read(client, bdm_url(w["x"].id), **PERIOD))["totals"]["meetings"] == 1


@pytest.mark.asyncio
async def test_students_follow_the_current_assignee_and_meetings_their_owner(client, db_session):
    w = await perf_world(client, db_session)
    c3 = await make_bdm(db_session, w["manager"], "college")
    from tests.bdm024_helpers import link

    await link(db_session, w["org_c"], assigned_bdm_user_id=c3.id)
    await login(client, w["manager"])
    bdms = {b["id"]: b["figures"] for b in (await read(client, **PERIOD, type="college"))["bdms"]}
    assert bdms[str(w["c1"].id)]["meetings"] == 1 and bdms[str(w["c1"].id)]["students"] == 0
    assert bdms[str(c3.id)]["students"] == 1 and bdms[str(c3.id)]["revenue"] == "1250.50" and bdms[str(c3.id)]["meetings"] == 0


# --- team scope -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_team_is_excluded_and_super_admin_can_narrow(client, db_session):
    w = await perf_world(client, db_session)
    await login(client, await make_user(db_session, "super_admin", "global"))
    one = await read(client, **PERIOD, manager_user_id=str(w["manager"].id))
    assert one["manager"] == {"id": str(w["manager"].id), "full_name": w["manager"].full_name}
    assert table(one) == EXPECTED
    everyone = table(await read(client, **PERIOD))
    assert everyone["P-02"][2] >= 2  # this team's and the other team's college meetings


@pytest.mark.asyncio
async def test_the_query_count_does_not_grow_with_the_team(client, db_session):
    async def statements(url: str, **params) -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await read(client, url, **params)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    manager = await make_manager(db_session)
    first = await make_bdm(db_session, manager)
    org = await org_of(client, first)
    await login(client, manager)
    small = await statements(PERFORMANCE, **PERIOD, type="college")
    for _ in range(3):
        bdm = await make_bdm(db_session, manager)
        await appt(db_session, bdm.id, org, IN)
    assert await statements(PERFORMANCE, **PERIOD, type="college") == small
