"""bdm-014 (DEC-SCOPE-097) -- GET /bdm/my-day: the §15 common section and each type's "Today's overview" tiles (Appendix B.2).

Every row here is "today" by the IST clock, so each test uses fresh BDMs and only counts its own BDM's records (own scope)."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import event, func, update

from app.core.database import engine
from app.models import BdmActivity, BdmAppointment, BdmMou, BdmOrganization, BdmTrip
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm008_helpers import insert_task, ist_day
from tests.bdm017_helpers import add_lead

MY_DAY = "/api/v1/bdm/my-day"
AGENT_TILES = ["T-A1", "T-A2", "T-A3", "T-A4", "T-A5", "T-A6", "T-A7", "T-A8"]
SCHOOL_TILES = ["T-S1", "T-S2", "T-S3", "T-S4", "T-S5", "T-S6", "T-S7", "T-S8"]
COLLEGE_TILES = ["T-K1", "T-K2", "T-K3", "T-K4", "T-K5", "T-K6", "T-K7", "T-K8"]


async def signed_in_bdm(client, db, bdm_type: str = "college"):
    bdm = await make_bdm(db, await make_manager(db), bdm_type)
    await login(client, bdm)
    return bdm


async def insert_appt(db, bdm_id, org: dict, *, day_offset: int = 0, at: time = time(10, 0), appointment_type="college_meeting",
                      status="scheduled", trip_id=None) -> BdmAppointment:
    appt = BdmAppointment(
        code=f"APT-T{uuid.uuid4().hex[:10]}", bdm_user_id=bdm_id, organization_id=org["id"], contact_name="Dr Rao",
        starts_at=datetime.combine(ist_day(day_offset), at, IST), appointment_type=appointment_type, status=status,
        outcome="interested" if status == "completed" else None, trip_id=trip_id,
    )
    db.add(appt)
    await db.commit()
    return appt


async def insert_trip(db, bdm_id, start: int, end: int | None = None, *, to_place="Vijayawada", approval="approved",
                      travel_status="planned") -> BdmTrip:
    trip = BdmTrip(
        code=f"TRV-T{uuid.uuid4().hex[:10]}", bdm_user_id=bdm_id, travel_date=ist_day(start), return_date=ist_day(start if end is None else end),
        from_place="Hyderabad", to_place=to_place, purpose="College visits", mode="train", estimated_cost=1000,
        approval_status=approval, travel_status=travel_status,
    )
    db.add(trip)
    await db.commit()
    return trip


async def insert_mou(db, org: dict, bdm_id, status: str) -> None:
    db.add(BdmMou(organization_id=org["id"], created_by_user_id=bdm_id, status=status))
    await db.commit()


async def archive(db, org: dict) -> None:
    await db.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(archived_at=func.now()))
    await db.commit()


async def my_day(client) -> dict:
    response = await client.get(MY_DAY)
    assert response.status_code == 200, response.text
    return response.json()


def tile_values(body: dict) -> dict:
    return {t["key"]: t["value"] for t in body["tiles"]}


# --- access -------------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_a_bdm_with_a_profile_reads_my_day(client, db_session):
    manager = await make_manager(db_session)
    await login(client, manager)
    r = await client.get(MY_DAY)
    assert (r.status_code, r.json()["detail"]) == (403, "BDM role required")

    client.cookies.clear()
    await login(client, await make_user(db_session, "bdm", "it"))  # no profile row
    r = await client.get(MY_DAY)
    assert (r.status_code, r.json()["detail"]) == (403, "BDM profile not set up — contact your administrator")

    client.cookies.clear()
    assert (await client.get(MY_DAY)).status_code == 401


# --- empty and shape ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("bdm_type", "keys", "untracked"), [
    ("agent", AGENT_TILES, {"T-A6"}), ("school", SCHOOL_TILES, set()), ("college", COLLEGE_TILES, {"T-K7"}),
])
async def test_a_new_bdm_sees_its_types_exact_tiles_with_zeroes_and_untracked_labels(client, db_session, bdm_type, keys, untracked):
    await signed_in_bdm(client, db_session, bdm_type)
    body = await my_day(client)
    assert body["today"] == ist_day().isoformat() and body["bdm_type"] == bdm_type
    assert body["appointments"] == {"count": 0, "truncated": False, "items": []}
    assert body["trips"] == {"total": 0, "items": []}
    assert body["follow_ups"] == {"total": 0, "groups": []}
    assert [t["key"] for t in body["tiles"]] == keys
    for tile in body["tiles"]:
        assert tile["label"]
        if tile["key"] in untracked:
            assert (tile["tracked"], tile["value"]) == (False, None) and tile["note"]
        else:
            assert (tile["tracked"], tile["value"], tile["note"]) == (True, 0, None)


# --- §15 common section (AC1) -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_section_15_example_renders_from_real_data(client, db_session):
    bdm = await signed_in_bdm(client, db_session, "college")
    other = await make_bdm(db_session, await make_manager(db_session), "college")
    abc, xyz, pqr = [await create_org(client, name=f"{n} College {uuid.uuid4().hex[:6]}") for n in ("ABC", "XYZ", "PQR")]
    agent_org = await create_org(client, org_type="agent")

    late = await insert_appt(db_session, bdm.id, pqr, at=time(16, 0))
    first = await insert_appt(db_session, bdm.id, abc, at=time(10, 0))
    mid = await insert_appt(db_session, bdm.id, xyz, at=time(13, 0), status="confirmed")
    await insert_appt(db_session, bdm.id, abc, at=time(11, 0), status="cancelled")
    await insert_appt(db_session, bdm.id, abc, day_offset=1)
    await insert_appt(db_session, bdm.id, abc, day_offset=-1, at=time(23, 59))
    await insert_appt(db_session, other.id, abc)

    hyd_vja = await insert_trip(db_session, bdm.id, 5, 7)
    hyd_blr = await insert_trip(db_session, bdm.id, 9, 10, to_place="Bangalore", approval="draft")
    for _ in range(3):
        await insert_appt(db_session, bdm.id, abc, day_offset=5, trip_id=hyd_vja.id)
    await insert_appt(db_session, bdm.id, abc, day_offset=6, trip_id=hyd_vja.id, status="cancelled")
    for _ in range(5):
        await insert_appt(db_session, bdm.id, xyz, day_offset=9, trip_id=hyd_blr.id)
    await insert_trip(db_session, bdm.id, 0, 2)  # starts today: not upcoming
    await insert_trip(db_session, bdm.id, 3, travel_status="cancelled")
    await insert_trip(db_session, bdm.id, 4, approval="rejected")
    await insert_trip(db_session, other.id, 3)

    for offset in (0, 0, -1, -10):
        await insert_task(db_session, bdm.id, due_on=ist_day(offset), org_id=abc["id"])
    for offset in (0, -2):
        await insert_task(db_session, bdm.id, due_on=ist_day(offset), org_id=agent_org["id"])
    await insert_task(db_session, bdm.id, due_on=ist_day(-1), org_id=xyz["id"], source="mou")
    await insert_task(db_session, bdm.id, due_on=ist_day(1), org_id=abc["id"])  # upcoming
    await insert_task(db_session, bdm.id, org_id=abc["id"], status="done")
    await insert_task(db_session, bdm.id, org_id=abc["id"], status="cancelled")
    await insert_task(db_session, bdm.id, org_id=abc["id"], kind="task")
    await insert_task(db_session, other.id, org_id=abc["id"])

    body = await my_day(client)
    appts = body["appointments"]
    assert appts["count"] == 3 and appts["truncated"] is False
    assert [a["id"] for a in appts["items"]] == [str(first.id), str(mid.id), str(late.id)]
    assert [a["organization"]["name"] for a in appts["items"]] == [abc["name"], xyz["name"], pqr["name"]]
    assert appts["items"][1]["status"] == "confirmed" and appts["items"][0]["organization"]["org_type"] == "college"
    assert datetime.fromisoformat(appts["items"][0]["starts_at"]).astimezone(IST).time() == time(10, 0)

    trips = body["trips"]
    assert trips["total"] == 2
    assert [(t["id"], t["to_place"], t["appointment_count"]) for t in trips["items"]] == [
        (str(hyd_vja.id), "Vijayawada", 3), (str(hyd_blr.id), "Bangalore", 5)]
    assert trips["items"][0]["from_place"] == "Hyderabad" and trips["items"][1]["approval_status"] == "draft"

    assert body["follow_ups"] == {"total": 7, "groups": [{"key": "college", "count": 4}, {"key": "agent", "count": 2}, {"key": "mou", "count": 1}]}
    assert tile_values(body)["T-K1"] == 3


@pytest.mark.asyncio
async def test_follow_ups_without_an_organization_are_their_own_group(client, db_session):
    bdm = await signed_in_bdm(client, db_session)
    await insert_task(db_session, bdm.id)
    assert (await my_day(client))["follow_ups"] == {"total": 1, "groups": [{"key": "none", "count": 1}]}


@pytest.mark.asyncio
async def test_lists_are_bounded_but_counts_are_exact(client, db_session, monkeypatch):
    from app.api import bdm_my_day

    monkeypatch.setattr(bdm_my_day, "APPOINTMENT_LIMIT", 2)
    bdm = await signed_in_bdm(client, db_session)
    org = await create_org(client)
    for hour in (9, 10, 11):
        await insert_appt(db_session, bdm.id, org, at=time(hour, 0))
    for start in range(1, 8):
        await insert_trip(db_session, bdm.id, start)
    body = await my_day(client)
    assert (body["appointments"]["count"], len(body["appointments"]["items"]), body["appointments"]["truncated"]) == (3, 2, True)
    assert body["trips"]["total"] == 7 and [t["travel_date"] for t in body["trips"]["items"]] == [ist_day(n).isoformat() for n in range(1, 6)]


# --- type tiles (AC2) ---------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_tiles(client, db_session):
    bdm = await signed_in_bdm(client, db_session, "agent")
    agent, agent_two, archived, college = [await create_org(client, org_type=t) for t in ("agent", "agent", "agent", "college")]
    await insert_appt(db_session, bdm.id, agent, appointment_type="agent_meeting")
    await insert_appt(db_session, bdm.id, agent, appointment_type="agent_visit", at=time(12, 0))
    await insert_appt(db_session, bdm.id, agent, appointment_type="product_training", at=time(15, 0))
    await insert_appt(db_session, bdm.id, agent, appointment_type="agent_meeting", status="cancelled")
    await insert_appt(db_session, bdm.id, agent, appointment_type="agent_meeting", day_offset=1)
    # T-A3: two distinct agent organizations (two follow-ups on one); not the college one, not tomorrow's
    await insert_task(db_session, bdm.id, org_id=agent["id"])
    await insert_task(db_session, bdm.id, due_on=ist_day(-3), org_id=agent["id"])
    await insert_task(db_session, bdm.id, org_id=agent_two["id"])
    await insert_task(db_session, bdm.id, org_id=college["id"])
    await insert_task(db_session, bdm.id, due_on=ist_day(1), org_id=archived["id"])
    # T-A7: open tasks on agent organizations due <= today
    await insert_task(db_session, bdm.id, org_id=agent["id"], kind="task")
    await insert_task(db_session, bdm.id, due_on=ist_day(-1), org_id=agent_two["id"], kind="task")
    await insert_task(db_session, bdm.id, due_on=ist_day(2), org_id=agent["id"], kind="task")
    await insert_task(db_session, bdm.id, org_id=college["id"], kind="task")
    await insert_task(db_session, bdm.id, org_id=agent["id"], kind="task", status="done")
    # T-A5: current MoU pending on non-archived agent organizations
    await insert_mou(db_session, agent, bdm.id, "proposal_sent")
    await insert_mou(db_session, agent_two, bdm.id, "draft_shared")
    await insert_mou(db_session, archived, bdm.id, "under_negotiation")
    await insert_mou(db_session, college, bdm.id, "proposal_sent")
    await archive(db_session, archived)
    # T-A8: trips covering today or tomorrow
    await insert_trip(db_session, bdm.id, -2, 0)
    await insert_trip(db_session, bdm.id, 1, 3)
    await insert_trip(db_session, bdm.id, 2, 3)
    await insert_trip(db_session, bdm.id, -5, -1)
    await insert_trip(db_session, bdm.id, 0, travel_status="cancelled")

    # T-A4: three agent organizations created today (the archived one too), not the college one
    assert tile_values(await my_day(client)) == {
        "T-A1": 3, "T-A2": 2, "T-A3": 2, "T-A4": 3, "T-A5": 2, "T-A6": None, "T-A7": 2, "T-A8": 2,
    }


@pytest.mark.asyncio
async def test_school_tiles(client, db_session):
    bdm = await signed_in_bdm(client, db_session, "school")
    school, school_two, archived, college = [await create_org(client, org_type=t) for t in ("school", "school", "school", "college")]
    for kind in ("principal_meeting", "management_meeting", "seminar", "workshop", "seminar_workshop", "parent_orientation",
                 "teacher_orientation", "career_guidance_presentation", "psychometric_presentation", "profile_building_presentation"):
        await insert_appt(db_session, bdm.id, school, appointment_type=kind)
    await insert_appt(db_session, bdm.id, college, appointment_type="principal_meeting")
    await insert_appt(db_session, bdm.id, school, appointment_type="principal_meeting", status="cancelled")
    await insert_appt(db_session, bdm.id, school, appointment_type="seminar", day_offset=-1)
    for offset in (0, -4):
        await insert_task(db_session, bdm.id, due_on=ist_day(offset), org_id=school["id"])
    await insert_task(db_session, bdm.id, due_on=ist_day(1), org_id=school["id"])
    await insert_task(db_session, bdm.id, org_id=school["id"], kind="task")
    now = datetime.now(IST)
    for channel, at in (("visit", now), ("visit", now), ("call", now), ("visit", now - timedelta(days=2))):
        db_session.add(BdmActivity(bdm_user_id=bdm.id, organization_id=school["id"], channel=channel, occurred_at=at,
                                   direction="outbound" if channel == "call" else None))
    await db_session.commit()
    await insert_mou(db_session, school, bdm.id, "proposal_sent")
    await insert_mou(db_session, school_two, bdm.id, "discussion_started")
    await insert_mou(db_session, archived, bdm.id, "proposal_sent")
    await insert_mou(db_session, college, bdm.id, "under_negotiation")
    await archive(db_session, archived)

    assert tile_values(await my_day(client)) == {
        "T-S1": 10, "T-S2": 2, "T-S3": 1, "T-S4": 2, "T-S5": 2, "T-S6": 1, "T-S7": 2, "T-S8": 8,
    }


@pytest.mark.asyncio
async def test_school_mous_signed_or_prospect_are_not_pending(client, db_session):
    bdm = await signed_in_bdm(client, db_session, "school")
    for status in ("prospect", "signed", "rejected"):
        org = await create_org(client, org_type="school")
        db_session.add(BdmMou(organization_id=org["id"], created_by_user_id=bdm.id, status=status,
                              signed_on=ist_day() if status == "signed" else None))
    await db_session.commit()
    values = tile_values(await my_day(client))
    assert (values["T-S6"], values["T-S7"]) == (0, 0)


@pytest.mark.asyncio
async def test_college_tiles(client, db_session):
    bdm = await signed_in_bdm(client, db_session, "college")
    college, university = await create_org(client), await create_org(client, org_type="university")
    for kind in ("placement_cell_meeting", "principal_meeting", "hod_meeting", "course_promotion", "student_seminar", "workshop",
                 "seminar_workshop", "internship_discussion", "faculty_meeting"):
        await insert_appt(db_session, bdm.id, college, appointment_type=kind)
    await insert_appt(db_session, bdm.id, university, appointment_type="hod_meeting")
    await insert_appt(db_session, bdm.id, college, appointment_type="course_promotion", status="cancelled")
    await insert_appt(db_session, bdm.id, college, appointment_type="course_promotion", status="completed", at=time(8, 0))
    await add_lead(client, college["id"])
    await add_lead(client, university["id"])

    assert tile_values(await my_day(client)) == {
        "T-K1": 10, "T-K2": 1, "T-K3": 3, "T-K4": 2, "T-K5": 3, "T-K6": 1, "T-K7": None, "T-K8": 2,
    }


# --- performance (AC4) --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bdm_type", ["agent", "school", "college"])
async def test_the_query_count_does_not_grow_with_the_data(client, db_session, bdm_type):
    async def statements_for_one_read() -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await my_day(client)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    bdm = await signed_in_bdm(client, db_session, bdm_type)
    small = await statements_for_one_read()
    orgs = [await create_org(client, org_type=t) for t in ("agent", "school", "college")]
    for i, org in enumerate(orgs * 3):
        await insert_appt(db_session, bdm.id, org, at=time(9 + i, 0))
        await insert_task(db_session, bdm.id, org_id=org["id"])
    for org in orgs:
        await insert_mou(db_session, org, bdm.id, "proposal_sent")
    for start in range(1, 6):
        trip = await insert_trip(db_session, bdm.id, start)
        await insert_appt(db_session, bdm.id, orgs[0], day_offset=start, trip_id=trip.id)
    assert await statements_for_one_read() == small
