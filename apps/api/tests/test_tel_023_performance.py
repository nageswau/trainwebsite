"""tel-023 (DEC-SCOPE-112, API §12AF): the manager performance comparison -- P1-P6 over a date range per telecaller in scope (PF1-PF4),
the CSV export and its audit row. The shared test database is never truncated, so each test reads only the rows of users it created."""

import csv
import io
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services import telecaller_metrics as metrics
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager
from tests.test_tel_021_metrics import add, assign, audit, call, clock, history, lead_appt, make_lead, meeting

URL = "/api/v1/telecaller/manager/performance"
CSV_URL = f"{URL}.csv"
COUNTS = ("leads", "calls", "connected", "qualified", "appointments", "conversions")

pytestmark = pytest.mark.asyncio


def row_of(body: dict, user) -> dict:
    return next(item for item in body["items"] if item["user_id"] == str(user.id))


def ids(body: dict) -> list[str]:
    return [item["user_id"] for item in body["items"]]


def has(body: dict, user) -> bool:
    return any(item["user_id"] == str(user.id) for item in body["items"])


async def test_leads_received_follows_the_b1_rule_over_the_range(db_session):
    manager = await make_tl_manager(db_session)
    tel, other = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    now, _, start, _ = await clock(db_session)
    two_days = start - timedelta(days=2)
    kept = await make_lead(db_session, tel)
    moved_away = await make_lead(db_session, other)
    created_own = await make_lead(db_session, tel)
    before_range = await make_lead(db_session, tel)
    await add(db_session,
              assign(kept, two_days + timedelta(hours=1), None, tel), assign(kept, now - timedelta(minutes=1), None, tel),  # counted once
              assign(moved_away, two_days + timedelta(hours=2), None, tel), assign(moved_away, two_days + timedelta(hours=3), tel, other),
              audit("lead.create", created_own, two_days + timedelta(hours=4), tel, assigned=True),
              assign(before_range, two_days - timedelta(days=1), None, tel))
    assert await metrics.leads_received(db_session, tel.id, two_days, now + timedelta(minutes=1)) == 3
    assert await metrics.leads_received(db_session, other.id, two_days, now + timedelta(minutes=1)) == 1


async def test_figures_equal_the_sum_of_the_tel_021_daily_figures(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    now, today, start, _ = await clock(db_session)
    yday = start - timedelta(hours=12)
    lead = await make_lead(db_session, tel)
    await add(db_session, assign(lead, yday, None, tel),
              call(lead, tel, yday), call(lead, tel, yday, "busy"), call(lead, tel, now - timedelta(minutes=2)),
              history(lead, "qualified", tel, yday), lead_appt(lead, tel, now + timedelta(days=2), yday), meeting(tel, now - timedelta(minutes=3)),
              call(lead, tel, start - timedelta(days=3)))  # outside the range
    await as_user(client, manager)
    first = today - timedelta(days=1)
    response = await client.get(URL, params={"date_from": first.isoformat(), "date_to": today.isoformat()})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    row = row_of(response.json(), tel)
    daily = [await metrics.daily_activity(db_session, tel.id, day, now) for day in (first, today)]
    assert row["calls"] == sum(d["calls"] for d in daily) == 3
    assert row["connected"] == sum(d["connected_calls"] for d in daily) == 2
    assert row["qualified"] == sum(d["qualified_leads"] for d in daily) == 1
    assert row["appointments"] == sum(d["new_appointments"] for d in daily) == 2
    assert row["conversions"] == sum(d["converted_leads"] for d in daily) == 0
    assert row["leads"] == 1
    assert row["full_name"] == tel.full_name and row["team"] == "IT" and row["active"] is True and row["status"] == "Active"


async def test_conversions_are_credited_per_db2(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    now, today, _, _ = await clock(db_session)
    won = await make_lead(db_session, tel, status="converted")
    await add(db_session, history(won, "converted", None, now - timedelta(minutes=5), from_stage="application_enrollment", event="system"))
    await as_user(client, manager)
    body = (await client.get(URL, params={"date_from": today.isoformat(), "date_to": today.isoformat()})).json()
    assert row_of(body, tel)["conversions"] == 1


async def test_defaults_totals_and_inactive_rows(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    gone = await make_telecaller(db_session, manager, team="overseas")
    gone.active = False
    now, today, _, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    await add(db_session, call(lead, tel, now - timedelta(minutes=1)), call(lead, gone, now - timedelta(minutes=1)))
    await as_user(client, manager)
    body = (await client.get(URL)).json()
    assert body["date_from"] == today.replace(day=1).isoformat() and body["date_to"] == today.isoformat()
    assert (body["sort"], body["dir"], body["team"]) == ("calls", "desc", None)
    assert {item["user_id"] for item in body["items"]} == {str(tel.id), str(gone.id)}
    inactive = row_of(body, gone)
    assert inactive["active"] is False and inactive["status"] == "Inactive" and inactive["team"] == "Overseas"
    assert body["totals"]["full_name"] == "Total" and body["totals"]["calls"] == 2
    assert all(body["totals"][key] == sum(item[key] for item in body["items"]) for key in COUNTS)
    assert [c["key"] for c in body["columns"]] == ["full_name", "team", "status", *COUNTS]


async def test_sorting_by_any_column_with_ties_by_name(client, db_session):
    manager = await make_tl_manager(db_session)
    busy, idle = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    now, _, _, _ = await clock(db_session)
    lead = await make_lead(db_session, busy)
    await add(db_session, call(lead, busy, now - timedelta(minutes=1)), call(lead, busy, now - timedelta(minutes=2)))
    await as_user(client, manager)
    desc = (await client.get(URL, params={"sort": "calls", "dir": "desc"})).json()
    asc = (await client.get(URL, params={"sort": "calls", "dir": "asc"})).json()
    assert ids(desc) == [str(busy.id), str(idle.id)] and ids(asc) == [str(idle.id), str(busy.id)]  # idle first: 0 calls, ascending
    by_name = (await client.get(URL, params={"sort": "name", "dir": "asc"})).json()
    assert [item["full_name"] for item in by_name["items"]] == sorted(item["full_name"] for item in by_name["items"])


async def test_a_manager_sees_only_direct_reports_and_team_only_narrows(client, db_session):
    manager = await make_tl_manager(db_session)
    mine_it, mine_ovs = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager, team="overseas")
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    await as_user(client, manager)
    body = (await client.get(URL)).json()
    assert {item["user_id"] for item in body["items"]} == {str(mine_it.id), str(mine_ovs.id)}
    assert not has(body, stranger)
    narrowed = (await client.get(URL, params={"team": "overseas"})).json()
    assert [item["user_id"] for item in narrowed["items"]] == [str(mine_ovs.id)] and narrowed["team"] == "overseas"
    assert body["teams"] == ["it", "overseas"]


async def test_a_division_admin_sees_their_team_only(client, db_session):
    it_tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    ovs_tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    body = (await client.get(URL)).json()
    assert has(body, it_tel) and not has(body, ovs_tel) and body["teams"] == ["it"]
    assert all(item["team"] == "IT" for item in body["items"])
    assert (await client.get(URL, params={"team": "overseas"})).status_code == 403
    assert (await client.get(CSV_URL, params={"team": "overseas"})).status_code == 403


async def test_super_admin_sees_every_team(client, db_session):
    it_tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    ovs_tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    body = (await client.get(URL)).json()
    assert has(body, it_tel) and has(body, ovs_tel)
    assert not has((await client.get(URL, params={"team": "it"})).json(), ovs_tel)


async def test_telecallers_and_other_roles_are_refused(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    for user in (tel, await make_user(db_session, "counselor", "it"), await make_user(db_session, "student", "it")):
        await as_user(client, user)
        for url in (URL, CSV_URL):
            response = await client.get(url)
            assert response.status_code == 403 and response.json()["detail"] == "Telecaller performance is for managers and administrators"


@pytest.mark.parametrize("params", [
    {"date_from": "2026-13-01"}, {"date_to": "nope"}, {"team": "school"}, {"sort": "email"}, {"dir": "up"},
])
async def test_malformed_inputs_are_422(client, db_session, params):
    await as_user(client, await make_tl_manager(db_session))
    assert (await client.get(URL, params=params)).status_code == 422
    assert (await client.get(CSV_URL, params=params)).status_code == 422


async def test_range_rules_are_422(client, db_session):
    await as_user(client, await make_tl_manager(db_session))
    _, today, _, _ = await clock(db_session)
    cases = {
        (today, today - timedelta(days=1)): "after",
        (today - timedelta(days=1), today + timedelta(days=1)): "future",
        (today - timedelta(days=366), today): "366",
    }
    for (first, last), word in cases.items():
        response = await client.get(URL, params={"date_from": first.isoformat(), "date_to": last.isoformat()})
        assert response.status_code == 422 and word in response.json()["detail"], response.text
    exactly = await client.get(URL, params={"date_from": (today - timedelta(days=365)).isoformat(), "date_to": today.isoformat()})
    assert exactly.status_code == 200, exactly.text


async def test_the_csv_matches_the_screen_and_is_audited(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    tel.full_name = "=HYPERLINK(evil)"
    now, today, _, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    await add(db_session, call(lead, tel, now - timedelta(minutes=1)))
    await as_user(client, manager)
    params = {"date_from": today.isoformat(), "date_to": today.isoformat(), "sort": "name", "dir": "asc"}
    screen = (await client.get(URL, params=params)).json()
    response = await client.get(CSV_URL, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == f'attachment; filename="telecaller-performance-{today}-to-{today}.csv"'
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text[1:])))
    assert rows[0] == [c["label"] for c in screen["columns"]]
    assert [r[0] for r in rows[1:-1]] == ["'=HYPERLINK(evil)" if i["full_name"].startswith("=") else i["full_name"] for i in screen["items"]]
    assert rows[-1][0] == "Total" and rows[-1][4] == str(screen["totals"]["calls"])
    logged = (await db_session.execute(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "telecaller_performance.export"))).scalars().all()
    assert len(logged) == 1 and logged[0].metadata_json["rows"] == len(screen["items"])
    assert logged[0].entity_type == "telecaller_performance"
