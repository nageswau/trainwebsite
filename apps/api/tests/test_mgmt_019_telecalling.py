"""mgmt-019 -- the company-wide Telecalling dashboard (EVID-017 §14, spec TC1-TC16; AC1 the totals equal the sum of the tel-023 rows).

The shared test database is never truncated, so each definition test reads only the rows of the telecallers it made; the totals tests
check sums over whatever is there."""

from datetime import timedelta

import pytest

from app.models import TelecallerProfile
from tests.bdm001_helpers import emp, make_user
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager
from tests.test_tel_021_metrics import add, assign, call, clock, follow_up, history, lead_appt, make_lead, meeting
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/telecalling"
TEL_023 = "/api/v1/telecaller/manager/performance"
FIGURES = ("leads", "calls", "connected", "interested", "follow_ups", "appointments", "converted", "lost")


def row_of(body: dict, user) -> dict:
    return next(row for row in body["telecallers"] if row["user_id"] == str(user.id))


async def dashboard(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_each_figure_follows_its_definition(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager, team="overseas")
    now, today, start, _ = await clock(db_session)
    yday, outside = start - timedelta(hours=12), start - timedelta(days=3)
    lead, won = await make_lead(db_session, tel), await make_lead(db_session, tel, status="converted")
    await add(
        db_session,
        assign(lead, yday, None, tel),
        assign(won, yday, None, tel),  # TC3: two leads assigned in the period
        call(lead, tel, yday),
        call(lead, tel, now - timedelta(minutes=2), "busy"),
        call(lead, tel, outside),  # TC4
        history(lead, "interested", tel, yday),
        history(lead, "interested", manager, yday),  # TC5: only the telecaller's move
        history(lead, "qualified", tel, yday),  # not Interested
        follow_up(lead, tel, yday, created_at=yday, status="done", completed_at=yday + timedelta(hours=1), completed_by_user_id=tel.id),  # TC6
        lead_appt(lead, tel, now + timedelta(days=1), yday),
        meeting(tel, yday),  # TC7: one counselling + one BDM request
        history(won, "converted", None, yday + timedelta(hours=1), "application_enrollment", "converted"),  # TC8
        history(lead, "not_interested", tel, yday),
        history(lead, "lost", tel, now - timedelta(minutes=1)),  # TC9: any closed outcome
        history(lead, "lost", tel, outside),
    )
    await as_role(client, db_session, "partner", "global")
    body = await dashboard(client, date_from=(today - timedelta(days=1)).isoformat(), date_to=today.isoformat())
    row = row_of(body, tel)
    assert {key: row[key] for key in FIGURES} == {
        "leads": 2,
        "calls": 2,
        "connected": 1,
        "interested": 1,
        "follow_ups": 1,
        "appointments": 2,
        "converted": 1,
        "lost": 2,
    }
    assert row["conversion"] == 50.0  # TC10: converted ÷ leads assigned
    assert (row["full_name"], row["team"], row["active"]) == (tel.full_name, "Overseas", True)


async def test_a_telecaller_with_no_activity_reads_zeros_and_no_conversion(client, db_session):
    manager = await make_tl_manager(db_session)
    idle = await make_telecaller(db_session, manager)
    gone = await make_user(db_session, "telecaller", "it", active=False)
    db_session.add(TelecallerProfile(user_id=gone.id, team="it", employee_id=emp(), reporting_manager_user_id=manager.id))
    await db_session.commit()
    await as_role(client, db_session, "super_admin", "global")
    body = await dashboard(client)
    row = row_of(body, idle)
    assert all(row[key] == 0 for key in FIGURES) and row["conversion"] is None
    assert row["team"] == "IT"
    assert row_of(body, gone)["active"] is False  # TC1: inactive telecallers stay listed


async def test_totals_are_the_sums_of_the_rows_and_equal_the_tel_023_totals(client, db_session):
    """AC1 and TC12, over every telecaller in the shared database."""
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    now, today, start, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    await add(db_session, assign(lead, now - timedelta(minutes=5), None, tel), call(lead, tel, now - timedelta(minutes=4)))
    await as_role(client, db_session, "super_admin", "global")
    params = {"date_from": (today - timedelta(days=30)).isoformat(), "date_to": today.isoformat()}
    body = await dashboard(client, **params)
    rows, teams, totals = body["telecallers"], body["teams"], body["totals"]
    for key in FIGURES:
        assert totals[key] == sum(row[key] for row in rows) == sum(team[key] for team in teams)
        for team in teams:
            assert team[key] == sum(row[key] for row in rows if row["team"] == team["label"])
    assert [team["team"] for team in teams] == ["it", "overseas"]  # both teams always listed
    assert sum(team["telecallers"] for team in teams) == len(rows)
    response = await client.get(TEL_023, params=params)
    assert response.status_code == 200, response.text
    tel_023 = response.json()["totals"]
    for ours, theirs in (("leads", "leads"), ("calls", "calls"), ("connected", "connected"), ("appointments", "appointments"), ("converted", "conversions")):
        assert totals[ours] == tel_023[theirs], ours
    assert len(rows) == len(response.json()["items"])
    expected = round(totals["converted"] * 100 / totals["leads"], 1) if totals["leads"] else None
    assert totals["conversion"] == expected


async def test_the_chain_is_calls_interested_counselling_registration_with_shares_of_calls(client, db_session):
    await as_role(client, db_session, "partner", "global")
    body = await dashboard(client)
    chain, totals = body["chain"], body["totals"]
    assert [(step["key"], step["label"]) for step in chain] == [
        ("calls", "Calls"),
        ("interested", "Interested"),
        ("counselling", "Counseling"),
        ("registration", "Registration"),
    ]
    assert chain[0]["value"] == totals["calls"] and chain[1]["value"] == totals["interested"]
    assert chain[3]["value"] == totals["converted"]
    assert chain[0]["share"] is None
    calls = chain[0]["value"]
    for step in chain[1:]:  # QA19-03: each step against the calls the chain starts from, never against the step before
        assert step["share"] == (round(step["value"] * 100 / calls, 1) if calls else None)


async def test_counselling_counts_only_counselling_bookings(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    now, today, _, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    await as_role(client, db_session, "partner", "global")
    before = (await dashboard(client, date_from=today.isoformat(), date_to=today.isoformat()))["chain"][2]["value"]
    await add(db_session, lead_appt(lead, tel, now + timedelta(days=1), now - timedelta(minutes=1)), meeting(tel, now - timedelta(minutes=1)))
    after = (await dashboard(client, date_from=today.isoformat(), date_to=today.isoformat()))["chain"][2]["value"]
    assert after - before == 1


async def test_the_period_defaults_to_this_month_and_obeys_the_tel_023_range_rules(client, db_session):
    _, today, _, _ = await clock(db_session)
    await as_role(client, db_session, "partner", "global")
    body = await dashboard(client)
    assert (body["date_from"], body["date_to"]) == (today.replace(day=1).isoformat(), today.isoformat())
    cases = (
        ({"date_from": today.isoformat(), "date_to": (today - timedelta(days=1)).isoformat()}, "The start date must not be after the end date"),
        ({"date_to": (today + timedelta(days=1)).isoformat()}, "The range can't end in the future"),
        ({"date_from": (today - timedelta(days=366)).isoformat(), "date_to": today.isoformat()}, "The range can't be longer than 366 days"),
    )
    for params, message in cases:
        response = await client.get(URL, params=params)
        assert (response.status_code, response.json()["detail"]) == (422, message)
    assert (await client.get(URL, params={"date_from": "2026-02-30"})).status_code == 422


@pytest.mark.parametrize(
    ("role", "division", "message"),
    [
        ("accountant", "global", "Operational access required"),
        ("telecaller_manager", "global", "Management access required"),
        ("telecaller", "it", "Management access required"),
        ("it_admin", "it", "Management access required"),
    ],
)
async def test_only_the_operational_tier_may_read_it(client, db_session, role, division, message):
    await as_role(client, db_session, role, division)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, message)


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


async def test_no_lead_details_leave_the_dashboard(client, db_session):
    """TC14: staff names and counts only."""
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    lead = await make_lead(db_session, tel)
    now, _, _, _ = await clock(db_session)
    await add(db_session, assign(lead, now - timedelta(minutes=1), None, tel))
    await as_user(client, await make_user(db_session, "partner", "global"))
    text = (await client.get(URL)).text
    assert lead.name not in text and lead.email not in text and str(lead.id) not in text
