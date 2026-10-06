"""bdm-011 -- linking appointments to trips (spec §2 L2/L4, §4; AC1, negative scenarios, edge cases)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import login
from tests.bdm006_helpers import appt_payload, audits, create_appt
from tests.bdm010_helpers import act, make_trip, sign_in
from tests.bdm011_helpers import APPTS, TRIPS, bdm_trip, linked, on_day


def _out_of_range(day, trip) -> str:
    fmt = lambda d: d.strftime("%d %b %Y")  # noqa: E731
    travel, ret = (india_today() + timedelta(days=n) for n in (7, 8))
    return f"This appointment is on {fmt(india_today() + timedelta(days=day))}, outside {trip['code']} ({fmt(travel)} – {fmt(ret)})"


@pytest.mark.asyncio
async def test_create_links_a_trip_covering_the_appointment_date(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    a = await linked(client, org, trip, day=8, hour=21)  # the return date, late evening IST (next day in UTC is still in range)
    assert a["trip"] == {
        "id": trip["id"], "code": trip["code"], "from_place": "Hyderabad", "to_place": "Vijayawada", "travel_date": trip["travel_date"],
        "return_date": trip["return_date"], "approval_status": "draft", "travel_status": "planned",
    }


@pytest.mark.asyncio
async def test_an_unlinked_appointment_has_no_trip(client, db_session):
    _, _, org, _ = await bdm_trip(client, db_session)
    assert (await create_appt(client, org))["trip"] is None


@pytest.mark.asyncio
async def test_create_outside_the_trip_dates_is_422(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    response = await client.post(APPTS, json=appt_payload(org, starts_at=on_day(9), trip_id=trip["id"]))
    assert (response.status_code, response.json()["detail"]) == (422, _out_of_range(9, trip))


@pytest.mark.asyncio
async def test_patch_links_and_unlinks_with_an_audit(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    a = await create_appt(client, org, starts_at=on_day(7))
    response = await client.patch(f"{APPTS}/{a['id']}", json={"trip_id": trip["id"]})
    assert response.status_code == 200 and response.json()["appointment"]["trip"]["id"] == trip["id"]
    response = await client.patch(f"{APPTS}/{a['id']}", json={"trip_id": None})
    assert response.status_code == 200 and response.json()["appointment"]["trip"] is None
    assert sorted(await audits(db_session, a["id"])) == ["bdm_appointment.create", "bdm_appointment.update", "bdm_appointment.update"]


@pytest.mark.asyncio
async def test_ac1_patch_link_outside_the_trip_dates_is_422_and_changes_nothing(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    a = await create_appt(client, org, starts_at=on_day(6))
    response = await client.patch(f"{APPTS}/{a['id']}", json={"trip_id": trip["id"]})
    assert (response.status_code, response.json()["detail"]) == (422, _out_of_range(6, trip))
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["trip"] is None


@pytest.mark.asyncio
async def test_another_bdms_trip_is_404(client, db_session):
    _, _, _, theirs = await bdm_trip(client, db_session)
    _, _, org, _ = await bdm_trip(client, db_session)  # now signed in as a second BDM
    response = await client.post(APPTS, json=appt_payload(org, starts_at=on_day(7), trip_id=theirs["id"]))
    assert (response.status_code, response.json()["detail"]) == (404, "Trip not found")


@pytest.mark.asyncio
async def test_another_bdms_appointment_is_404(client, db_session):
    _, _, org, _ = await bdm_trip(client, db_session)
    theirs = await create_appt(client, org, starts_at=on_day(7))
    _, _, _, mine = await bdm_trip(client, db_session)
    response = await client.patch(f"{APPTS}/{theirs['id']}", json={"trip_id": mine["id"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_manager_cannot_link(client, db_session):
    manager, _, org, trip = await bdm_trip(client, db_session)
    a = await create_appt(client, org, starts_at=on_day(7))
    await sign_in(client, manager)
    response = await client.patch(f"{APPTS}/{a['id']}", json={"trip_id": trip["id"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_l4_a_cancelled_trip_keeps_its_links_takes_no_new_ones_and_can_be_unlinked(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    kept = await linked(client, org, trip)
    assert (await act(client, trip["id"], "cancel")).status_code == 200
    assert (await client.get(f"{APPTS}/{kept['id']}")).json()["appointment"]["trip"]["travel_status"] == "cancelled"
    other = await create_appt(client, org, starts_at=on_day(7, 15))
    response = await client.patch(f"{APPTS}/{other['id']}", json={"trip_id": trip["id"]})
    assert (response.status_code, response.json()["detail"]) == (409, "This trip is cancelled and can't take appointments")
    response = await client.patch(f"{APPTS}/{kept['id']}", json={"trip_id": None})
    assert response.status_code == 200 and response.json()["appointment"]["trip"] is None


@pytest.mark.asyncio
async def test_a_reschedule_outside_the_trip_unlinks_with_an_audit(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    a = await linked(client, org, trip)
    inside = await client.post(f"{APPTS}/{a['id']}/reschedule", json={"starts_at": on_day(8, 11)})
    assert inside.status_code == 200 and inside.json()["appointment"]["trip"]["id"] == trip["id"]
    outside = await client.post(f"{APPTS}/{a['id']}/reschedule", json={"starts_at": on_day(12)})
    assert outside.status_code == 200 and outside.json()["appointment"]["trip"] is None
    assert "bdm_appointment.trip_unlinked" in await audits(db_session, a["id"])


@pytest.mark.asyncio
async def test_a_trip_date_edit_that_would_strand_a_linked_appointment_is_422(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    await linked(client, org, trip, day=8)
    today = india_today()
    response = await client.patch(f"{TRIPS}/{trip['id']}", json={"return_date": str(today + timedelta(days=7))})
    assert (response.status_code, response.json()["detail"]) == (
        422, "1 linked appointment falls outside the new dates — unlink or reschedule it first")
    response = await client.patch(f"{TRIPS}/{trip['id']}", json={"return_date": str(today + timedelta(days=9))})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_trip_date_edit_unlinks_closed_appointments_left_outside_and_audits_them(client, db_session):
    _, _, org, trip = await bdm_trip(client, db_session)
    a = await linked(client, org, trip, day=8)
    assert (await client.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "Principal away"})).status_code == 200
    response = await client.patch(f"{TRIPS}/{trip['id']}", json={"return_date": str(india_today() + timedelta(days=7))})
    assert response.status_code == 200
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["trip"] is None
    rows = await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == trip["id"], AuditLog.action == "bdm.trip_update"))
    assert [r.get("unlinked_appointments") for r in rows] == [[a["code"]]]


@pytest.mark.asyncio
async def test_linkable_lists_only_my_open_trips_that_have_not_ended(client, db_session):
    """The appointment form's trip choices (the page filters them by the chosen date)."""
    today = india_today()
    _, bdm, _, soon = await bdm_trip(client, db_session)
    later = await make_trip(client, travel_date=str(today + timedelta(days=20)), return_date=str(today + timedelta(days=21)))
    await make_trip(client, travel_date=str(today - timedelta(days=3)), return_date=str(today - timedelta(days=1)))  # ended
    today_only = await make_trip(client, travel_date=str(today), return_date=str(today))
    cancelled = await make_trip(client)
    await act(client, cancelled["id"], "cancel")
    await bdm_trip(client, db_session)  # another BDM's trip
    client.cookies.clear()
    await login(client, bdm)
    page = (await client.get(TRIPS, params={"linkable": "true"})).json()
    assert {t["id"] for t in page["items"]} == {soon["id"], later["id"], today_only["id"]}
