"""tel-022 -- telecaller targets API (spec §5; AC1-AC8; DEC-SCOPE-080 G1-G4). The test database is shared and never truncated, and team
defaults are global per team, so team-default tests use a random far-future date and assert on that date only; per-user rows are
isolated by their fresh user."""

import random
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, TelecallerProfile, TelTarget
from app.services.bdm_appointments import IST
from tests.tel001_helpers import emp, login, make_tl_manager, make_user

TARGETS, EFFECTIVE = "/api/v1/telecaller/targets", "/api/v1/telecaller/targets/effective"
KPIS = ["calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions"]


def _today() -> date:
    return datetime.now(IST).date()


def _far_day() -> date:
    return date(2100, 1, 1) + timedelta(days=random.randint(0, 100_000))


def _far_month() -> date:
    return date(random.randint(2100, 2900), random.randint(1, 12), 1)


def _next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


async def _telecaller(db, manager, *, team="it", active=True):
    user = await make_user(db, "telecaller", team, active=active)
    db.add(TelecallerProfile(user_id=user.id, team=team, employee_id=emp(), reporting_manager_user_id=manager.id))
    await db.commit()
    return user


async def _signed_in_manager(client, db):
    manager = await make_tl_manager(db)
    await login(client, manager)
    return manager


def _team_body(values, *, team="it", period="daily", effective_from=None):
    body = {"scope": "team", "team": team, "period": period, "values": values}
    if effective_from:
        body["effective_from"] = effective_from.isoformat()
    return body


def _user_body(user, values, *, period="daily", effective_from=None):
    body = {"scope": "user", "user_id": str(user.id), "period": period, "values": values}
    if effective_from:
        body["effective_from"] = effective_from.isoformat()
    return body


def _by_kpi(rows) -> dict:
    return {r["kpi"]: (r["value"], r["source"]) for r in rows}


async def _effective(client, **params):
    response = await client.get(EFFECTIVE, params={k: str(v) for k, v in params.items()})
    assert response.status_code == 200, response.text
    return response.json()


# --- POST: who may write (AC5, G3) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller_manager", "global"), ("super_admin", "global")])
async def test_manager_and_super_admin_set_a_team_default(client, db_session, role, division):
    user = await make_user(db_session, role, division)
    await login(client, user)
    day = _far_day()
    response = await client.post(TARGETS, json=_team_body({"calls": 80, "connected_calls": 40}, effective_from=day))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"scope": "team", "team": "it", "user": None, "period": "daily", "effective_from": day.isoformat(), "values": {"calls": 80, "connected_calls": 40}}
    rows = (await db_session.scalars(select(TelTarget).where(TelTarget.scope == "team", TelTarget.team == "it", TelTarget.effective_from == day))).all()
    assert {(r.kpi, r.value, r.set_by_user_id) for r in rows} == {("calls", 80, user.id), ("connected_calls", 40, user.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), ("it_admin", "it"), ("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm_manager", "global")])
async def test_other_roles_cannot_write_targets(client, db_session, role, division):
    """§22 line 713: a telecaller must not modify targets; division admins and others have no write either (G3)."""
    await login(client, await make_user(db_session, role, division))
    response = await client.post(TARGETS, json=_team_body({"calls": 80}))
    assert response.status_code == 403
    assert (await client.get(TARGETS)).status_code == 403


@pytest.mark.asyncio
async def test_manager_overrides_only_direct_reports(client, db_session):
    other_manager = await make_tl_manager(db_session)
    stranger = await _telecaller(db_session, other_manager)
    manager = await _signed_in_manager(client, db_session)
    mine = await _telecaller(db_session, manager)
    assert (await client.post(TARGETS, json=_user_body(mine, {"calls": 90}))).status_code == 200
    for target in (stranger, await make_user(db_session, "it_admin", "it")):
        response = await client.post(TARGETS, json=_user_body(target, {"calls": 90}))
        assert response.status_code == 404 and response.json()["detail"] == "Telecaller not found"
    response = await client.post(TARGETS, json={**_user_body(mine, {"calls": 1}), "user_id": str(uuid.uuid4())})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_overrides_anyone_and_inactive_is_refused(client, db_session):
    manager = await make_tl_manager(db_session)
    active, inactive = await _telecaller(db_session, manager), await _telecaller(db_session, manager, active=False)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(TARGETS, json=_user_body(active, {"calls": 90}))).status_code == 200
    response = await client.post(TARGETS, json=_user_body(inactive, {"calls": 90}))
    assert response.status_code == 422 and response.json()["detail"] == "This telecaller is inactive"


# --- POST: validation (AC4, AC6) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (_team_body({"calls": -1}), "Values: Calls must be 0 or more"),
        (_team_body({"calls": 100_001}), "Values: Calls must be 100000 or less"),
        (_team_body({"calls": 1.5}), "Values: Calls must be a whole number"),
        (_team_body({"emails": 3}), "Values: unknown KPI emails"),
        (_team_body({}), "Values: enter at least one target"),
        (_team_body({"calls": None}), "A team default cannot be removed; enter a number"),
        ({"scope": "team", "period": "daily", "values": {"calls": 1}}, "Choose a team"),
        ({"scope": "team", "team": "it", "user_id": str(uuid.uuid4()), "period": "daily", "values": {"calls": 1}}, "A team default cannot name a telecaller"),
        ({"scope": "user", "period": "daily", "values": {"calls": 1}}, "Choose a telecaller"),
        ({"scope": "user", "team": "it", "user_id": str(uuid.uuid4()), "period": "daily", "values": {"calls": 1}}, "A telecaller override cannot name a team"),
        ({**_team_body({"calls": 1}), "period": "weekly"}, "Period: Input should be 'daily' or 'monthly'"),
        ({**_team_body({"calls": 1}), "colour": "red"}, "Unknown field: colour"),
    ],
)
async def test_invalid_bodies_are_422(client, db_session, body, message):
    await _signed_in_manager(client, db_session)
    response = await client.post(TARGETS, json=body)
    assert response.status_code == 422 and response.json()["detail"] == message


@pytest.mark.asyncio
async def test_effective_dates_start_next_day_or_month(client, db_session):
    """G2 / AC6: daily ≥ tomorrow, monthly = the 1st of a month ≥ next month; the default is the earliest allowed date."""
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    today, tomorrow = _today(), _today() + timedelta(days=1)
    first_next = _next_month(today)
    for period, day, message in [
        ("daily", today, f"Daily targets can start on {tomorrow:%d %b %Y} or later"),
        ("daily", today - timedelta(days=3), f"Daily targets can start on {tomorrow:%d %b %Y} or later"),
        ("monthly", today.replace(day=1), f"Monthly targets can start on {first_next:%d %b %Y} or later"),
        ("monthly", first_next + timedelta(days=1), "A monthly target starts on the 1st of a month"),
    ]:
        response = await client.post(TARGETS, json=_user_body(me, {"calls": 1}, period=period, effective_from=day))
        assert response.status_code == 422 and response.json()["detail"] == message, (period, day)
    daily = (await client.post(TARGETS, json=_user_body(me, {"calls": 5}))).json()
    monthly = (await client.post(TARGETS, json=_user_body(me, {"calls": 150}, period="monthly"))).json()
    assert daily["effective_from"] == tomorrow.isoformat() and monthly["effective_from"] == first_next.isoformat()


@pytest.mark.asyncio
async def test_resaving_a_pending_date_replaces_it_and_is_audited(client, db_session):
    """AC8: one row per (subject, period, KPI, date); every save writes one audit row with ids and keys only."""
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    for value in (90, 95):
        assert (await client.post(TARGETS, json=_user_body(me, {"calls": value, "conversions": 3}))).status_code == 200
    rows = (await db_session.scalars(select(TelTarget).where(TelTarget.user_id == me.id).execution_options(populate_existing=True))).all()
    assert sorted((r.kpi, r.value) for r in rows) == [("calls", 95), ("conversions", 3)]
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "telecaller.target_set", AuditLog.entity_id == str(me.id)))).all()
    assert len(audits) == 2 and audits[0].user_id == manager.id
    assert audits[0].metadata_json == {"scope": "user", "period": "daily", "effective_from": (_today() + timedelta(days=1)).isoformat(), "kpis": ["calls", "conversions"]}


# --- effective read (AC1, AC2, AC3, AC7) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_override_beats_the_team_default(client, db_session):
    """AC1: IT team Calls/day 80, Telecaller A 90 → A sees 90 (override), B sees 80 (team default)."""
    manager = await _signed_in_manager(client, db_session)
    a, b = await _telecaller(db_session, manager), await _telecaller(db_session, manager)
    day = _far_day()
    assert (await client.post(TARGETS, json=_team_body({"calls": 80}, effective_from=day))).status_code == 200
    assert (await client.post(TARGETS, json=_user_body(a, {"calls": 90}, effective_from=day))).status_code == 200
    assert _by_kpi((await _effective(client, user_id=a.id, date=day))["daily"])["calls"] == (90, "user")
    body = await _effective(client, user_id=b.id, date=day)
    assert _by_kpi(body["daily"])["calls"] == (80, "team")
    assert [r["kpi"] for r in body["daily"]] == KPIS and [r["kpi"] for r in body["monthly"]] == KPIS
    assert body["user"] == {"id": str(b.id), "full_name": b.full_name} and body["team"] == "it" and body["date"] == day.isoformat()
    team = await _effective(client, team="it", date=day)
    assert _by_kpi(team["daily"])["calls"] == (80, "team") and team["user"] is None


@pytest.mark.asyncio
async def test_a_change_applies_from_its_date_and_past_days_keep_theirs(client, db_session):
    """AC2 + AC3: a past-dated value stays for past days; a new value applies from tomorrow, never to today."""
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    today, tomorrow = _today(), _today() + timedelta(days=1)
    db_session.add(TelTarget(scope="user", user_id=me.id, period="daily", kpi="calls", value=70, effective_from=today - timedelta(days=10), set_by_user_id=manager.id))
    await db_session.commit()
    assert (await client.post(TARGETS, json=_user_body(me, {"calls": 95}))).status_code == 200
    assert _by_kpi((await _effective(client, user_id=me.id, date=today - timedelta(days=5)))["daily"])["calls"] == (70, "user")
    assert _by_kpi((await _effective(client, user_id=me.id))["daily"])["calls"] == (70, "user")
    assert _by_kpi((await _effective(client, user_id=me.id, date=tomorrow))["daily"])["calls"] == (95, "user")
    assert _by_kpi((await _effective(client, user_id=me.id, date=today - timedelta(days=11)))["daily"])["calls"][0] != 70


@pytest.mark.asyncio
async def test_removing_an_override_falls_back_to_the_team_default(client, db_session):
    """AC7: a null value ends the override from its date; earlier dates keep it."""
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager, team="overseas")
    day = _far_day()
    assert (await client.post(TARGETS, json=_team_body({"follow_ups": 25}, team="overseas", effective_from=day))).status_code == 200
    assert (await client.post(TARGETS, json=_user_body(me, {"follow_ups": 30}, effective_from=day))).status_code == 200
    later = day + timedelta(days=7)
    assert (await client.post(TARGETS, json=_user_body(me, {"follow_ups": None}, effective_from=later))).status_code == 200
    assert _by_kpi((await _effective(client, user_id=me.id, date=day))["daily"])["follow_ups"] == (30, "user")
    assert _by_kpi((await _effective(client, user_id=me.id, date=later))["daily"])["follow_ups"][1] == "team"


@pytest.mark.asyncio
async def test_monthly_targets_resolve_from_the_first_of_the_month(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    month = _far_month()
    assert (await client.post(TARGETS, json=_user_body(me, {"conversions": 12}, period="monthly", effective_from=month))).status_code == 200
    body = await _effective(client, user_id=me.id, date=month + timedelta(days=20))
    assert _by_kpi(body["monthly"])["conversions"] == (12, "user") and body["month"] == month.isoformat()
    assert _by_kpi(body["daily"])["conversions"] != (12, "user")


@pytest.mark.asyncio
async def test_not_set_is_null(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    body = await _effective(client, user_id=me.id, date=date(1999, 1, 1))
    assert all(r["value"] is None and r["source"] is None for r in body["daily"] + body["monthly"])


# --- effective read: access (AC5) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_reads_only_their_own(client, db_session):
    manager = await make_tl_manager(db_session)
    me, colleague = await _telecaller(db_session, manager), await _telecaller(db_session, manager)
    await login(client, me)
    body = await _effective(client)
    assert body["user"]["id"] == str(me.id) and body["date"] == _today().isoformat()
    assert (await _effective(client, user_id=me.id))["user"]["id"] == str(me.id)
    assert (await client.get(EFFECTIVE, params={"user_id": str(colleague.id)})).status_code == 403
    assert (await client.get(EFFECTIVE, params={"team": "it"})).status_code == 403


@pytest.mark.asyncio
async def test_manager_effective_read_needs_one_subject_in_scope(client, db_session):
    stranger = await _telecaller(db_session, await make_tl_manager(db_session))
    await _signed_in_manager(client, db_session)
    assert (await client.get(EFFECTIVE)).status_code == 422
    assert (await client.get(EFFECTIVE, params={"team": "it", "user_id": str(stranger.id)})).status_code == 422
    assert (await client.get(EFFECTIVE, params={"user_id": str(stranger.id)})).status_code == 404
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(EFFECTIVE, params={"team": "it"})).status_code == 403


# --- history ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_history_is_scoped_and_filtered(client, db_session):
    other_manager = await make_tl_manager(db_session)
    stranger = await _telecaller(db_session, other_manager)
    db_session.add(TelTarget(scope="user", user_id=stranger.id, period="daily", kpi="calls", value=1, effective_from=_far_day(), set_by_user_id=other_manager.id))
    await db_session.commit()
    manager = await _signed_in_manager(client, db_session)
    me = await _telecaller(db_session, manager)
    assert (await client.post(TARGETS, json=_user_body(me, {"calls": 90, "conversions": 2}))).status_code == 200
    assert (await client.post(TARGETS, json=_user_body(me, {"calls": 300}, period="monthly"))).status_code == 200
    page = (await client.get(TARGETS, params={"user_id": str(me.id)})).json()
    assert page["total"] == 3 and page["limit"] == 50 and page["offset"] == 0
    first = page["items"][0]
    assert first["period"] == "monthly" and first["value"] == 300 and first["scope"] == "user" and first["team"] is None
    assert first["user"] == {"id": str(me.id), "full_name": me.full_name} and first["set_by"] == {"id": str(manager.id), "full_name": manager.full_name}
    assert set(first) == {"id", "scope", "team", "user", "period", "kpi", "value", "effective_from", "set_by", "updated_at"}
    assert (await client.get(TARGETS, params={"user_id": str(me.id), "period": "daily", "kpi": "conversions"})).json()["total"] == 1
    assert (await client.get(TARGETS, params={"user_id": str(stranger.id)})).status_code == 404
    scoped = (await client.get(TARGETS, params={"scope": "user", "limit": 100})).json()
    assert all(item["user"]["id"] == str(me.id) for item in scoped["items"])
    teams = (await client.get(TARGETS, params={"scope": "team", "team": "overseas", "limit": 5})).json()
    assert all(item["scope"] == "team" and item["team"] == "overseas" for item in teams["items"])
    count = await db_session.scalar(select(func.count()).select_from(TelTarget).where(TelTarget.scope == "team", TelTarget.team == "overseas"))
    assert teams["total"] == count
