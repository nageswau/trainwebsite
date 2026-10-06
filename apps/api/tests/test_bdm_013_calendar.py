"""bdm-013 (DEC-SCOPE-079) -- GET /bdm/calendar: scope (K3), range rules (K2), which rows land on which days (K4, K5, AC1)."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from app.models import BdmAppointment, BdmTrip
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm006_helpers import bdm_with_org
from tests.bdm008_helpers import insert_task

CAL = "/api/v1/bdm/calendar"
MON = date(2031, 3, 3)  # a Monday far from today, so only this test's rows are in range


def week(start: date = MON) -> dict:
    return {"date_from": start.isoformat(), "date_to": (start + timedelta(days=6)).isoformat()}


async def insert_appt(db, bdm, org: dict, day: date, at: time = time(10, 0), *, appointment_type="college_meeting", status="scheduled"):
    appt = BdmAppointment(
        code=f"APT-T{uuid.uuid4().hex[:10]}", bdm_user_id=bdm.id, organization_id=org["id"], contact_name="Dr Rao",
        starts_at=datetime.combine(day, at, IST), appointment_type=appointment_type, status=status,
        outcome="interested" if status == "completed" else None,
    )
    db.add(appt)
    await db.commit()
    return appt


async def insert_trip(db, bdm, travel: date, ret: date, *, to_place="Vijayawada", approval="approved", travel_status="planned"):
    trip = BdmTrip(
        code=f"TRV-T{uuid.uuid4().hex[:10]}", bdm_user_id=bdm.id, travel_date=travel, return_date=ret, from_place="Hyderabad",
        to_place=to_place, purpose="College visits", mode="train", estimated_cost=1000, approval_status=approval, travel_status=travel_status,
    )
    db.add(trip)
    await db.commit()
    return trip


async def calendar(client, **params):
    return await client.get(CAL, params=params)


@pytest.mark.asyncio
async def test_bdm_week_has_every_item_type_on_its_day(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    seminar = await insert_appt(db_session, bdm, org, MON + timedelta(days=1), appointment_type="seminar_workshop")
    late = await insert_appt(db_session, bdm, org, MON + timedelta(days=2), time(23, 30))  # 18:00 UTC: still Wednesday in IST
    done = await insert_appt(db_session, bdm, org, MON, status="completed")
    trip = await insert_trip(db_session, bdm, MON + timedelta(days=1), MON + timedelta(days=3))
    follow_up = await insert_task(db_session, bdm.id, due_on=MON + timedelta(days=4), org_id=org["id"])
    task = await insert_task(db_session, bdm.id, due_on=MON + timedelta(days=4), kind="task", status="done")

    r = await calendar(client, **week())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bdm"]["id"] == str(bdm.id) and body["date_from"] == MON.isoformat() and body["truncated"] is False
    appts = {a["id"]: a for a in body["appointments"]}
    assert appts[str(seminar.id)]["seminar"] is True and appts[str(seminar.id)]["day"] == (MON + timedelta(days=1)).isoformat()
    assert appts[str(late.id)]["day"] == (MON + timedelta(days=2)).isoformat() and appts[str(late.id)]["seminar"] is False
    assert appts[str(done.id)]["status"] == "completed" and appts[str(done.id)]["organization"]["name"] == org["name"]
    assert [a["id"] for a in body["appointments"]] == [str(done.id), str(seminar.id), str(late.id)]  # by start time
    assert [(t["id"], t["travel_date"], t["return_date"], t["to_place"]) for t in body["trips"]] == [
        (str(trip.id), trip.travel_date.isoformat(), trip.return_date.isoformat(), "Vijayawada")]
    tasks = {t["id"]: t for t in body["tasks"]}
    assert tasks[str(follow_up.id)]["kind"] == "follow_up" and tasks[str(follow_up.id)]["organization"]["id"] == org["id"]
    assert tasks[str(task.id)]["status"] == "done" and tasks[str(task.id)]["organization"] is None
    assert "notes" not in tasks[str(task.id)] and "purpose" not in body["trips"][0]  # nothing beyond what the calendar shows


@pytest.mark.asyncio
async def test_cancelled_and_rejected_items_are_left_out(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    await insert_appt(db_session, bdm, org, MON, status="cancelled")
    await insert_trip(db_session, bdm, MON, MON + timedelta(days=1), travel_status="cancelled")
    await insert_trip(db_session, bdm, MON, MON + timedelta(days=1), approval="rejected")
    await insert_task(db_session, bdm.id, due_on=MON, status="cancelled")
    draft = await insert_trip(db_session, bdm, MON + timedelta(days=2), MON + timedelta(days=2), approval="draft")
    body = (await calendar(client, **week())).json()
    assert body["appointments"] == [] and body["tasks"] == []
    assert [t["id"] for t in body["trips"]] == [str(draft.id)] and body["trips"][0]["approval_status"] == "draft"


@pytest.mark.asyncio
async def test_rows_outside_the_range_are_left_out_and_a_trip_across_the_week_boundary_is_in_both_weeks(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    await insert_appt(db_session, bdm, org, MON - timedelta(days=1), time(23, 59))  # Sunday before, IST
    await insert_appt(db_session, bdm, org, MON + timedelta(days=7), time(0, 0))  # Monday after, IST
    await insert_task(db_session, bdm.id, due_on=MON + timedelta(days=7))
    crossing = await insert_trip(db_session, bdm, MON + timedelta(days=5), MON + timedelta(days=8))
    this_week = (await calendar(client, **week())).json()
    next_week = (await calendar(client, **week(MON + timedelta(days=7)))).json()
    assert this_week["appointments"] == [] and this_week["tasks"] == []
    assert [t["id"] for t in this_week["trips"]] == [str(crossing.id)] == [t["id"] for t in next_week["trips"]]
    assert len(next_week["appointments"]) == 1 and len(next_week["tasks"]) == 1


@pytest.mark.asyncio
async def test_empty_week_and_single_day(client, db_session):
    await bdm_with_org(client, db_session)
    body = (await calendar(client, date_from=MON.isoformat(), date_to=MON.isoformat())).json()
    assert (body["appointments"], body["trips"], body["tasks"]) == ([], [], [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("days", "status"), [(30, 200), (31, 422)])
async def test_range_cap_is_31_days(client, db_session, days, status):
    await bdm_with_org(client, db_session)
    r = await calendar(client, date_from=MON.isoformat(), date_to=(MON + timedelta(days=days)).isoformat())
    assert r.status_code == status, r.text
    if status == 422:
        assert r.json()["detail"] == "The calendar shows at most 31 days"


@pytest.mark.asyncio
async def test_bad_ranges_are_422(client, db_session):
    await bdm_with_org(client, db_session)
    r = await calendar(client, date_from=MON.isoformat(), date_to=(MON - timedelta(days=1)).isoformat())
    assert (r.status_code, r.json()["detail"]) == (422, "date_from must be on or before date_to")
    assert (await calendar(client, date_from=MON.isoformat())).status_code == 422
    assert (await calendar(client, date_from="2031-02-30", date_to=MON.isoformat())).status_code == 422


@pytest.mark.asyncio
async def test_a_bdm_cannot_name_a_bdm(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    r = await calendar(client, **week(), bdm_user_id=str(bdm.id))
    assert (r.status_code, r.json()["detail"]) == (422, "bdm_user_id is only for managers")


@pytest.mark.asyncio
async def test_manager_reads_a_team_bdm_and_gets_404_for_anyone_else(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    appt = await insert_appt(db_session, bdm, org, MON)
    outsider = await make_bdm(db_session, await make_manager(db_session))
    await login(client, manager)
    body = (await calendar(client, **week(), bdm_user_id=str(bdm.id))).json()
    assert body["bdm"]["id"] == str(bdm.id) and [a["id"] for a in body["appointments"]] == [str(appt.id)]
    for other in (outsider.id, uuid.uuid4(), manager.id):
        r = await calendar(client, **week(), bdm_user_id=str(other))
        assert (r.status_code, r.json()["detail"]) == (404, "BDM not found")
    r = await calendar(client, **week())
    assert (r.status_code, r.json()["detail"]) == (422, "Choose a BDM")


@pytest.mark.asyncio
async def test_super_admin_reads_any_bdm(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    await insert_appt(db_session, bdm, org, MON)
    await login(client, await make_user(db_session, "super_admin", "global"))
    body = (await calendar(client, **week(), bdm_user_id=str(bdm.id))).json()
    assert len(body["appointments"]) == 1
    r = await calendar(client, **week(), bdm_user_id=str(uuid.uuid4()))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_other_roles_and_signed_out_are_refused(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    r = await calendar(client, **week(), bdm_user_id=str(bdm.id))
    assert (r.status_code, r.json()["detail"]) == (403, "BDM role required")
    client.cookies.clear()
    assert (await calendar(client, **week())).status_code == 401


@pytest.mark.asyncio
async def test_bdm_without_profile_is_403(client, db_session):
    await login(client, await make_user(db_session, "bdm", "it"))
    r = await calendar(client, **week())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_each_source_is_capped_and_flagged(client, db_session, monkeypatch):
    from app.api import bdm_calendar

    monkeypatch.setattr(bdm_calendar, "MAX_ROWS", 2)
    _, bdm, _ = await bdm_with_org(client, db_session)
    for _ in range(3):
        await insert_task(db_session, bdm.id, due_on=MON)
    body = (await calendar(client, **week())).json()
    assert len(body["tasks"]) == 2 and body["truncated"] is True
