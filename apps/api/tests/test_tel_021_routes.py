"""tel-021 (DEC-SCOPE-105 DB3/DB6, API §12X): the dashboard and daily activity routes -- who may read whose figures, the date rule and
the response shape. The figures themselves are covered in test_tel_021_metrics.py."""

from datetime import timedelta

import pytest

from app.models import LeadCall
from app.services.bdm_appointments import db_now, today_ist
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager

DASHBOARD = "/api/v1/telecaller/dashboard"
ACTIVITY = "/api/v1/telecaller/activity"

pytestmark = pytest.mark.asyncio


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def test_the_dashboard_returns_tiles_targets_and_todays_appointments(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, telecaller=tel, status="assigned")
    db_session.add(LeadCall(lead_id=row.id, caller_user_id=tel.id, occurred_at=await db_now(db_session) - timedelta(minutes=1), duration_seconds=5,
                            call_type="outgoing", outcome="busy"))
    await db_session.commit()
    await as_user(client, tel)
    response = await client.get(DASHBOARD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["day"] == today_ist(await db_now(db_session)).isoformat()
    assert body["tiles"]["calls_today"] == {"done": 1, "to_do": 1} and body["tiles"]["not_connected"] == 1
    assert body["tiles"]["daily_target"]["achieved"] == 1
    assert {r["kpi"] for r in body["targets"]["daily"]} == {r["kpi"] for r in body["targets"]["monthly"]}
    assert body["appointments"] == []


async def test_only_a_telecaller_has_a_dashboard(client, db_session):
    manager, _, _ = await team(db_session)
    for user in (manager, await make_user(db_session, "student", "it")):
        await as_user(client, user)
        assert (await client.get(DASHBOARD)).status_code == 403


async def test_a_telecaller_reads_their_own_activity_for_a_past_day(client, db_session):
    _, tel, _ = await team(db_session)
    await as_user(client, tel)
    yday = today_ist(await db_now(db_session)) - timedelta(days=1)
    response = await client.get(ACTIVITY, params={"date": yday.isoformat()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["day"] == yday.isoformat() and body["user"] == {"id": str(tel.id), "full_name": tel.full_name}
    assert len(body["counts"]) == 13 and all(v == 0 for v in body["counts"].values())
    assert {r["kpi"] for r in body["targets"]} >= {"calls"}
    own = await client.get(ACTIVITY, params={"user_id": str(tel.id)})
    assert own.status_code == 200 and own.json()["day"] == today_ist(await db_now(db_session)).isoformat()


async def test_a_future_day_is_refused(client, db_session):
    _, tel, _ = await team(db_session)
    await as_user(client, tel)
    tomorrow = today_ist(await db_now(db_session)) + timedelta(days=1)
    response = await client.get(ACTIVITY, params={"date": tomorrow.isoformat()})
    assert response.status_code == 422 and "future" in response.json()["detail"]


async def test_a_telecaller_cannot_read_another_users_activity(client, db_session):
    _, tel, other = await team(db_session)
    await as_user(client, tel)
    assert (await client.get(ACTIVITY, params={"user_id": str(other.id)})).status_code == 403


async def test_a_manager_reads_a_direct_report_only(client, db_session):
    manager, tel, _ = await team(db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    await as_user(client, manager)
    assert (await client.get(ACTIVITY, params={"user_id": str(tel.id)})).status_code == 200
    assert (await client.get(ACTIVITY, params={"user_id": str(stranger.id)})).status_code == 404
    assert (await client.get(ACTIVITY)).status_code == 422


async def test_super_admin_reads_any_telecaller_and_other_roles_are_refused(client, db_session):
    _, tel, _ = await team(db_session)
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.get(ACTIVITY, params={"user_id": str(tel.id)})).status_code == 200
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get(ACTIVITY, params={"user_id": str(tel.id)})).status_code == 403
