"""bdm-023 (DEC-SCOPE-104) -- GET /bdm/manager/dashboard: the 8 overview tiles (T-M01...T-M08) and the alert list (AL-1...AL-7) of
Appendix B.4, for a manager's team (super_admin: all teams, or one manager's).

Each test builds a fresh manager and team, so team-scoped figures are exact even on the shared test database. Every seeded rule has a
near-miss row next to it that must not count."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import event, update

from app.core.database import engine
from app.models import BdmAppointment, BdmAppointmentEvent, BdmDailyReport, BdmMou, BdmMouEvent, BdmProfile, BdmTask, BdmTrip
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm008_helpers import insert_task, ist_day
from tests.test_bdm_014_my_day import insert_appt, insert_trip

DASHBOARD = "/api/v1/bdm/manager/dashboard"
TILE_KEYS = ["T-M01", "T-M02", "T-M03", "T-M04", "T-M05", "T-M06", "T-M07", "T-M08"]
ALERT_KEYS = ["AL-1", "AL-2", "AL-3", "AL-4", "AL-5", "AL-6", "AL-7"]


def now() -> datetime:
    return datetime.now(IST)


async def org_of(client, bdm, **overrides) -> dict:
    """An organization assigned to `bdm` (created through the API as that BDM; the caller signs in again afterwards)."""
    client.cookies.clear()
    await login(client, bdm)
    org = await create_org(client, **overrides)
    client.cookies.clear()
    return org


async def appt_at(db, bdm_id, org: dict, starts_at: datetime, status: str = "scheduled") -> BdmAppointment:
    appt = BdmAppointment(
        code=f"APT-D{uuid.uuid4().hex[:10]}", bdm_user_id=bdm_id, organization_id=org["id"], contact_name="Dr Rao", starts_at=starts_at,
        appointment_type="college_meeting", status=status, outcome="interested" if status == "completed" else None,
    )
    db.add(appt)
    await db.commit()
    return appt


async def completed_event(db, appt: BdmAppointment, actor_id, at: datetime) -> None:
    db.add(BdmAppointmentEvent(appointment_id=appt.id, actor_user_id=actor_id, from_status="scheduled", to_status="completed", created_at=at))
    await db.commit()


async def mou(db, org: dict, bdm_id, status: str, *, waiting_days: float = 0) -> BdmMou:
    row = BdmMou(organization_id=org["id"], created_by_user_id=bdm_id, status=status, status_changed_at=now() - timedelta(days=waiting_days),
                 signed_on=ist_day() if status == "signed" else None)
    db.add(row)
    await db.commit()
    return row


async def mou_event(db, row: BdmMou, actor_id, from_status: str, to_status: str) -> None:
    db.add(BdmMouEvent(mou_id=row.id, actor_user_id=actor_id, kind="status", from_status=from_status, to_status=to_status, changed=[]))
    await db.commit()


async def backdate_profile(db, user_id, days: int) -> None:
    await db.execute(update(BdmProfile).where(BdmProfile.user_id == user_id).values(created_at=now() - timedelta(days=days)))
    await db.commit()


async def report(db, bdm_id, day) -> None:
    db.add(BdmDailyReport(bdm_user_id=bdm_id, report_date=day, bdm_type="college", counts=[]))
    await db.commit()


async def read(client, **params) -> dict:
    response = await client.get(DASHBOARD, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def tiles(body: dict) -> dict:
    return {t["key"]: t["value"] for t in body["tiles"]}


def alert(body: dict, key: str) -> dict:
    return next(a for a in body["alerts"] if a["key"] == key)


def ids(body: dict, key: str) -> list[str]:
    return [i["id"] for i in alert(body, key)["items"]]


# --- access (R1, R2) ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_managers_and_super_admin_read_the_dashboard(client, db_session):
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager))
    r = await client.get(DASHBOARD)
    assert (r.status_code, r.json()["detail"]) == (403, "BDM manager role required")

    client.cookies.clear()
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get(DASHBOARD)).status_code == 403

    client.cookies.clear()
    await login(client, manager)
    body = await read(client)
    assert [t["key"] for t in body["tiles"]] == TILE_KEYS
    assert [a["key"] for a in body["alerts"]] == ALERT_KEYS
    assert body["manager"] is None and body["month"] == ist_day().replace(day=1).isoformat() and body["today"] == ist_day().isoformat()
    assert all(t["label"] and t["definition"] for t in body["tiles"])


@pytest.mark.asyncio
async def test_only_super_admin_may_choose_a_manager(client, db_session):
    manager, other = await make_manager(db_session), await make_manager(db_session)
    await login(client, manager)
    r = await client.get(DASHBOARD, params={"manager_user_id": str(other.id)})
    assert (r.status_code, r.json()["detail"]) == (422, "Only a super admin can choose a manager")

    client.cookies.clear()
    await login(client, await make_user(db_session, "super_admin", "global"))
    for not_a_manager in (uuid.uuid4(), (await make_bdm(db_session, manager)).id):
        r = await client.get(DASHBOARD, params={"manager_user_id": str(not_a_manager)})
        assert (r.status_code, r.json()["detail"]) == (404, "Manager not found")
    assert (await client.get(DASHBOARD, params={"manager_user_id": "not-a-uuid"})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_reads_all_teams_or_one_managers_team(client, db_session):
    manager = await make_manager(db_session, name="Meera Manager")
    bdm = await make_bdm(db_session, manager)
    org = await org_of(client, bdm)
    late = await appt_at(db_session, bdm.id, org, now() - timedelta(hours=2))  # AL-6

    await login(client, await make_user(db_session, "super_admin", "global"))
    everyone = await read(client)
    assert everyone["manager"] is None and alert(everyone, "AL-6")["count"] >= 1 and tiles(everyone)["T-M01"] >= 1

    one = await read(client, manager_user_id=str(manager.id))
    assert one["manager"] == {"id": str(manager.id), "full_name": "Meera Manager"}
    assert tiles(one)["T-M01"] == 1 and ids(one, "AL-6") == [str(late.id)]


@pytest.mark.asyncio
async def test_a_manager_with_no_bdms_sees_zeros_and_no_alerts(client, db_session):
    await login(client, await make_manager(db_session))
    body = await read(client)
    assert set(tiles(body).values()) == {0}
    assert all(a["count"] == 0 and a["items"] == [] for a in body["alerts"])


# --- tiles (T-M01...T-M08) ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tiles_count_exactly_for_the_team(client, db_session):
    manager, outsider_manager = await make_manager(db_session), await make_manager(db_session)
    a, b = await make_bdm(db_session, manager), await make_bdm(db_session, manager)
    await make_bdm(db_session, manager, active=False)  # T-M01 counts active BDMs only
    x = await make_bdm(db_session, outsider_manager)
    org_a, org_a2, org_a3, org_x = await org_of(client, a), await org_of(client, a), await org_of(client, a), await org_of(client, x)

    await insert_appt(db_session, a.id, org_a, at=time(10))                                  # T-M02
    await insert_appt(db_session, a.id, org_a, at=time(11), status="cancelled")              # not T-M02
    await insert_appt(db_session, a.id, org_a, at=time(9), status="completed")               # T-M02, T-M06
    await insert_appt(db_session, a.id, org_a, day_offset=-40, status="completed")           # an earlier month: not T-M06
    await insert_appt(db_session, a.id, org_a, day_offset=1, status="confirmed")             # T-M03
    await insert_appt(db_session, a.id, org_a, day_offset=3, status="rescheduled")           # T-M03
    await insert_appt(db_session, a.id, org_a, day_offset=2, status="cancelled")             # not T-M03
    await insert_appt(db_session, x.id, org_x, at=time(10))                                  # another team

    await insert_trip(db_session, a.id, 0, 1)                                                # T-M04 (a), T-M05
    await insert_trip(db_session, b.id, 0, approval="approved", travel_status="in_progress") # T-M04 (b), T-M05
    await insert_trip(db_session, a.id, 0)                                                   # T-M05; a is counted once in T-M04
    await insert_trip(db_session, a.id, 0, travel_status="cancelled")                        # neither
    await insert_trip(db_session, a.id, 0, approval="rejected")                              # neither
    await insert_trip(db_session, a.id, 0, approval="submitted")                             # T-M05 only (not approved)
    await insert_trip(db_session, x.id, 0)                                                   # another team

    await mou(db_session, org_a, a.id, "discussion_started")                                 # T-M07
    signed = await mou(db_session, org_a2, a.id, "signed")                                   # not T-M07
    await mou_event(db_session, signed, a.id, "draft_shared", "signed")                      # T-M08
    await mou_event(db_session, signed, a.id, "signed", "signed")                            # an edit, not a transition
    await mou(db_session, org_a3, a.id, "prospect")                                          # not T-M07
    outsider = await mou(db_session, org_x, x.id, "proposal_sent")
    await mou_event(db_session, outsider, x.id, "draft_shared", "signed")                    # another team

    await login(client, manager)
    assert tiles(await read(client)) == {
        "T-M01": 2, "T-M02": 2, "T-M03": 2, "T-M04": 2, "T-M05": 4, "T-M06": 1, "T-M07": 1, "T-M08": 1,
    }


@pytest.mark.asyncio
async def test_mous_of_archived_organizations_are_not_in_progress(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager)
    org = await org_of(client, bdm)
    await mou(db_session, org, bdm.id, "under_negotiation", waiting_days=9)
    await login(client, manager)
    assert tiles(await read(client))["T-M07"] == 1

    from app.models import BdmOrganization  # noqa: PLC0415 -- only this test archives
    await db_session.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(archived_at=now()))
    await db_session.commit()
    assert tiles(await read(client))["T-M07"] == 0


# --- alerts (AL-1...AL-7) -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_alert_lists_exactly_its_records(client, db_session):
    manager, outsider_manager = await make_manager(db_session), await make_manager(db_session)
    a = await make_bdm(db_session, manager)
    late_bdm = await make_bdm(db_session, manager)       # AL-7: no report yesterday
    reporting = await make_bdm(db_session, manager)      # submitted yesterday
    await make_bdm(db_session, manager)                  # profile created today: yesterday was before they started
    gone = await make_bdm(db_session, manager, active=False)
    x = await make_bdm(db_session, outsider_manager)
    for user in (a, late_bdm, reporting, gone, x):
        await backdate_profile(db_session, user.id, 3)
    await report(db_session, reporting.id, ist_day(-1))
    await report(db_session, a.id, ist_day(-1))
    await report(db_session, late_bdm.id, ist_day(-2))   # an older report does not cover yesterday
    org, org2, org3, org4, org_x = (await org_of(client, a), await org_of(client, a), await org_of(client, a), await org_of(client, a),
                                    await org_of(client, x))

    soon = await appt_at(db_session, a.id, org, now() + timedelta(hours=2))                         # AL-1
    moved = await appt_at(db_session, a.id, org, now() + timedelta(hours=5), "rescheduled")         # AL-1
    await appt_at(db_session, a.id, org, now() + timedelta(hours=30))                               # beyond 24 h
    await appt_at(db_session, a.id, org, now() + timedelta(hours=3), "confirmed")                   # confirmed
    await appt_at(db_session, x.id, org_x, now() + timedelta(hours=2))                              # another team

    waiting = await insert_trip(db_session, a.id, 2, approval="submitted")                         # AL-2
    await insert_trip(db_session, a.id, 2, approval="draft")
    await insert_trip(db_session, x.id, 2, approval="submitted")

    overdue = await insert_task(db_session, a.id, due_on=ist_day(-2), org_id=org["id"])            # AL-3
    loose = await insert_task(db_session, a.id, due_on=ist_day(-1))                                # AL-3, no organization
    await insert_task(db_session, a.id, due_on=ist_day())                                          # due today: not overdue
    await insert_task(db_session, a.id, due_on=ist_day(-3), status="done")
    await insert_task(db_session, a.id, due_on=ist_day(-3), kind="task")
    await insert_task(db_session, x.id, due_on=ist_day(-3))

    stale = await mou(db_session, org, a.id, "proposal_sent", waiting_days=6)                      # AL-4
    stale_draft = await mou(db_session, org2, a.id, "draft_shared", waiting_days=5.1)              # AL-4
    await mou(db_session, org3, a.id, "proposal_sent", waiting_days=2)                             # not yet 5 days
    await mou(db_session, org4, a.id, "under_negotiation", waiting_days=10)                        # another status
    await mou(db_session, org_x, x.id, "proposal_sent", waiting_days=10)

    done_now = await appt_at(db_session, a.id, org, now() - timedelta(days=1), "completed")         # AL-5: completed today
    await completed_event(db_session, done_now, a.id, now() - timedelta(minutes=5))
    done_before = await appt_at(db_session, a.id, org, now() - timedelta(days=2), "completed")
    await completed_event(db_session, done_before, a.id, now() - timedelta(days=1, hours=1))

    pending = await appt_at(db_session, a.id, org, now() - timedelta(hours=3))                      # AL-6
    await appt_at(db_session, a.id, org, now() - timedelta(hours=4), "cancelled")
    await appt_at(db_session, a.id, org, now() - timedelta(hours=5), "no_show")

    await login(client, manager)
    body = await read(client)
    assert ids(body, "AL-1") == [str(soon.id), str(moved.id)]
    assert ids(body, "AL-2") == [str(waiting.id)]
    assert ids(body, "AL-3") == [str(overdue.id), str(loose.id)]
    assert ids(body, "AL-4") == [str(stale.id), str(stale_draft.id)]
    assert ids(body, "AL-5") == [str(done_now.id)]
    assert ids(body, "AL-6") == [str(pending.id)]
    assert ids(body, "AL-7") == [str(late_bdm.id)]
    assert [alert(body, k)["count"] for k in ALERT_KEYS] == [2, 1, 2, 2, 1, 1, 1]

    first = alert(body, "AL-1")
    assert (first["label"], first["tone"], first["record"]) == ("Appointment not confirmed", "warning", "appointment")
    assert first["items"][0]["bdm"] == {"id": str(a.id), "full_name": a.full_name}
    assert first["items"][0]["organization_id"] == org["id"] and first["items"][0]["title"].startswith(soon.code)
    assert alert(body, "AL-3")["items"][1]["organization_id"] is None
    assert alert(body, "AL-4")["items"][0]["organization_id"] == org["id"]
    assert alert(body, "AL-5")["tone"] == "success" and alert(body, "AL-6")["tone"] == "danger"
    assert alert(body, "AL-7")["items"][0]["at"] == ist_day(-1).isoformat()


@pytest.mark.asyncio
async def test_alerts_disappear_when_resolved(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager)
    await backdate_profile(db_session, bdm.id, 3)
    org = await org_of(client, bdm)
    soon = await appt_at(db_session, bdm.id, org, now() + timedelta(hours=2))
    trip = await insert_trip(db_session, bdm.id, 2, approval="submitted")
    task = await insert_task(db_session, bdm.id, due_on=ist_day(-2))
    row = await mou(db_session, org, bdm.id, "proposal_sent", waiting_days=7)
    late = await appt_at(db_session, bdm.id, org, now() - timedelta(hours=2))

    await login(client, manager)
    before = await read(client)
    assert [alert(before, k)["count"] for k in ("AL-1", "AL-2", "AL-3", "AL-4", "AL-6", "AL-7")] == [1, 1, 1, 1, 1, 1]

    await db_session.execute(update(BdmAppointment).where(BdmAppointment.id == soon.id).values(status="confirmed"))
    await db_session.execute(update(BdmTrip).where(BdmTrip.id == trip.id).values(approval_status="approved"))
    await db_session.execute(update(BdmTask).where(BdmTask.id == task.id).values(status="done", completed_at=now()))
    await db_session.execute(update(BdmMou).where(BdmMou.id == row.id).values(status="under_negotiation", status_changed_at=now()))
    await db_session.execute(update(BdmAppointment).where(BdmAppointment.id == late.id).values(status="cancelled"))
    await db_session.commit()
    await report(db_session, bdm.id, ist_day(-1))

    after = await read(client)
    assert all(a["count"] == 0 for a in after["alerts"])


@pytest.mark.asyncio
async def test_each_alert_shows_the_first_ten_and_the_full_count(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager)
    tasks = [await insert_task(db_session, bdm.id, due_on=ist_day(-20 + n)) for n in range(12)]
    await login(client, manager)
    overdue = alert(await read(client), "AL-3")
    assert overdue["count"] == 12
    assert [i["id"] for i in overdue["items"]] == [str(t.id) for t in tasks[:10]]  # oldest due first


# --- performance --------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_query_count_does_not_grow_with_the_team(client, db_session):
    async def statements_for_one_read() -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await read(client)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    manager = await make_manager(db_session)
    first = await make_bdm(db_session, manager)
    org = await org_of(client, first)
    await login(client, manager)
    small = await statements_for_one_read()
    for _ in range(3):
        bdm = await make_bdm(db_session, manager)
        await backdate_profile(db_session, bdm.id, 3)
        await appt_at(db_session, bdm.id, org, now() + timedelta(hours=1))
        await appt_at(db_session, bdm.id, org, now() - timedelta(hours=1))
        await insert_trip(db_session, bdm.id, 2, approval="submitted")
        await insert_task(db_session, bdm.id, due_on=ist_day(-2))
    assert await statements_for_one_read() == small
