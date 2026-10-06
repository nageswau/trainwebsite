"""bdm-011 -- the trip's itinerary and productivity metrics (spec §4; AC2, AC4, L1, L3)."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import update

from app.models import Enquiry
from app.services.bdm_travel import india_today
from tests.bdm006_helpers import APPTS, create_appt, move_to_past
from tests.bdm007_helpers import REPORT
from tests.bdm010_helpers import TEAM_TRIPS, TRIPS, act, sign_in
from tests.bdm011_helpers import IST, bdm_trip, linked
from tests.bdm017_helpers import add_lead


async def _complete(client, db, appt: dict) -> None:
    await move_to_past(db, appt["id"])
    assert (await client.post(f"{APPTS}/{appt['id']}/complete", json=REPORT)).status_code == 200


async def _trip(client, trip_id: str) -> dict:
    return (await client.get(f"{TRIPS}/{trip_id}")).json()


@pytest.mark.asyncio
async def test_ac4_the_itinerary_lists_linked_appointments_in_time_order(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    late = await linked(client, org, trip, hour=16, appointment_type="principal_meeting")
    early = await linked(client, org, trip, hour=10, appointment_type="course_promotion")
    noon = await linked(client, org, trip, hour=13, appointment_type="mou_discussion")
    await client.post(f"{APPTS}/{early['id']}/confirm")
    await client.post(f"{APPTS}/{noon['id']}/confirm")
    await create_appt(client, org, starts_at=datetime.combine(india_today() + timedelta(days=7), time(18), IST).isoformat())  # not linked
    itinerary = (await _trip(client, trip["id"]))["itinerary"]
    assert [(i["code"], i["appointment_type"], i["status"]) for i in itinerary] == [
        (early["code"], "course_promotion", "confirmed"), (noon["code"], "mou_discussion", "confirmed"), (late["code"], "principal_meeting", "scheduled")]
    assert itinerary[0]["organization"] == {"id": org["id"], "name": org["name"]}
    assert set(itinerary[0]) == {"id", "code", "starts_at", "duration_minutes", "appointment_type", "status", "organization", "expected_leads", "expected_revenue"}


@pytest.mark.asyncio
async def test_a_trip_without_links_has_an_empty_itinerary_and_null_derived_figures(client, db_session):
    _, _, _, trip = await bdm_trip(client, db_session)
    out = await _trip(client, trip["id"])
    assert out["itinerary"] == []
    assert out["metrics"] == {
        "meetings_planned": 0, "meetings_completed": 0, "estimated_cost": "2500.00", "actual_cost": "0.00", "cost_per_completed_meeting": None,
        "expected_leads": None, "expected_revenue": None, "actual_leads": 0, "actual_revenue": None,
    }


@pytest.mark.asyncio
async def test_ac2_counts_and_costs_are_exact(client, db_session):
    manager, bdm, org, trip = await bdm_trip(client, db_session)
    a = await linked(client, org, trip, hour=9, expected_leads=10, expected_revenue="1000")
    b = await linked(client, org, trip, hour=11, expected_leads=5)
    c = await linked(client, org, trip, hour=13, expected_revenue="500.50")
    d = await linked(client, org, trip, hour=15, expected_leads=100, expected_revenue="9999")
    await client.post(f"{APPTS}/{d['id']}/cancel", json={"reason": "Closed for exams"})  # L3: not planned, not summed
    await act(client, trip["id"], "submit")
    await sign_in(client, manager)
    assert (await client.post(f"{TEAM_TRIPS}/{trip['id']}/approve")).status_code == 200
    await sign_in(client, bdm)
    for amount in ("1200.25", "1800.25"):
        await client.post(f"{TRIPS}/{trip['id']}/expenses", json={"category": "travel", "amount": amount, "expense_date": str(india_today())})
    await _complete(client, db_session, a)
    await _complete(client, db_session, b)
    await move_to_past(db_session, c["id"])
    await client.post(f"{APPTS}/{c['id']}/no-show", json={"reason": "Not there"})  # L3: planned, not completed
    metrics = (await _trip(client, trip["id"]))["metrics"]
    assert metrics == {
        "meetings_planned": 3, "meetings_completed": 2, "estimated_cost": "2500.00", "actual_cost": "3000.50",
        "cost_per_completed_meeting": "1500.25", "expected_leads": 15, "expected_revenue": "1500.50", "actual_leads": 0, "actual_revenue": None,
    }
    assert len((await _trip(client, trip["id"]))["itinerary"]) == 4  # the cancelled one is still listed


@pytest.mark.asyncio
async def test_the_manager_sees_the_same_itinerary_and_metrics(client, db_session):
    manager, _, org, trip = await bdm_trip(client, db_session)
    await linked(client, org, trip, expected_leads=3)
    mine = await _trip(client, trip["id"])
    await sign_in(client, manager)
    theirs = (await client.get(f"{TEAM_TRIPS}/{trip['id']}")).json()
    assert (theirs["itinerary"], theirs["metrics"]) == (mine["itinerary"], mine["metrics"])


async def _lead(client, db, org_id: str, created: datetime) -> None:
    lead = await add_lead(client, org_id)
    await db.execute(update(Enquiry).where(Enquiry.id == uuid.UUID(lead["id"])).values(created_at=created))
    await db.commit()


@pytest.mark.asyncio
async def test_l1_actual_leads_are_my_leads_of_organizations_met_within_the_trip_window(client, db_session):
    from tests.bdm002_helpers import create_org

    _, _, met, trip = await bdm_trip(client, db_session)
    not_met = await create_org(client)
    await _complete(client, db_session, await linked(client, met, trip))
    first, last = india_today() + timedelta(days=7), india_today() + timedelta(days=8)
    at = lambda day, hour=12: datetime.combine(day, time(hour), IST)  # noqa: E731
    await _lead(client, db_session, met["id"], at(first, 0))  # counted: the trip's first minute
    await _lead(client, db_session, met["id"], at(last + timedelta(days=7), 23))  # counted: last day of the 7-day grace
    await _lead(client, db_session, met["id"], at(first - timedelta(days=1), 23))  # before the trip
    await _lead(client, db_session, met["id"], at(last + timedelta(days=8), 0))  # after the grace
    await _lead(client, db_session, not_met["id"], at(first))  # an organization this trip didn't meet
    assert (await _trip(client, trip["id"]))["metrics"]["actual_leads"] == 2
