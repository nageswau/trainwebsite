"""bdm-006 -- create, read, list (AC1, AC8 retry; spec §5.3, §5.5). PATCH tests follow (Task 5)."""

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update as sa_update

from app.models import BdmAppointment
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, audits, bdm_with_org, create_appt, future

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.asyncio
async def test_create_captures_every_section_2_field(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    contact = org["contacts"][0]
    a = await create_appt(
        client, org, appointment_type="placement_discussion", duration_minutes=90, location="Main block", purpose="Placement tie-up",
        remarks="Bring brochure", expected_leads=12, expected_revenue=25000.5,
    )
    assert re.fullmatch(r"APT-\d{6,}", a["code"])
    assert a["bdm"]["id"] == str(bdm.id) and a["organization"] == {"id": org["id"], "code": org["code"], "name": org["name"], "archived": False}
    assert (a["contact_id"], a["contact_name"], a["contact_designation"]) == (contact["id"], "Dr Rao", "Principal")
    assert a["status"] == "scheduled" and a["outcome"] is None and a["next_follow_up_on"] is None
    assert (a["appointment_type"], a["duration_minutes"], a["location"], a["purpose"], a["remarks"]) == ("placement_discussion", 90, "Main block", "Placement tie-up", "Bring brochure")
    assert a["expected_leads"] == 12 and a["expected_revenue"] == "25000.50"
    assert [(e["from_status"], e["to_status"]) for e in a["events"]] == [(None, "scheduled")]
    assert a["permissions"] == {"can_edit": True, "can_confirm": True, "can_reschedule": True, "can_cancel": True, "can_no_show": False, "can_complete": False}
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create"]
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["code"] == a["code"]


@pytest.mark.asyncio
async def test_codes_increase(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    first, second = await create_appt(client, org, starts_at=future(24)), await create_appt(client, org, starts_at=future(30))
    assert int(second["code"][4:]) > int(first["code"][4:])


@pytest.mark.asyncio
async def test_a_retried_create_meets_the_overlap_warning_naming_the_first(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    payload = appt_payload(org)
    first = (await client.post(APPTS, json=payload)).json()["appointment"]
    retry = await client.post(APPTS, json=payload)
    assert retry.status_code == 409
    detail = retry.json()["detail"]
    assert detail["code"] == "possible_overlap" and detail["total"] == 1 and detail["matches"][0]["code"] == first["code"]
    saved = await client.post(APPTS, json={**payload, "confirm_overlap": True})
    assert saved.status_code == 201
    assert sorted(await audits(db_session, saved.json()["appointment"]["id"])) == ["bdm_appointment.create", "bdm_appointment.overlap_override"]


@pytest.mark.asyncio
async def test_adjacent_appointments_do_not_overlap(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    start = datetime.fromisoformat(future(72))
    await create_appt(client, org, starts_at=start.isoformat(), duration_minutes=60)
    await create_appt(client, org, starts_at=(start + timedelta(minutes=60)).isoformat())  # starts as the first ends


@pytest.mark.asyncio
async def test_create_rejections_in_rule_order(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    other = await create_org(client)
    cases = [
        ({"starts_at": future(-1)}, 422, "Choose a time in the future"),
        ({"appointment_type": "agent_visit"}, 422, "This appointment type is not available for College BDMs"),
        ({"contact_id": other["contacts"][0]["id"]}, 422, "Choose a contact of this organization"),
    ]
    for over, status, message in cases:
        response = await client.post(APPTS, json=appt_payload(org, **over))
        assert (response.status_code, response.json()["detail"]) == (status, message), over


@pytest.mark.asyncio
async def test_list_filters_ordering_and_ist_day_edges(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    second_org = await create_org(client)
    day = (datetime.now(IST) + timedelta(days=10)).date()
    late = await create_appt(client, org, starts_at=datetime.combine(day, time(23, 30), IST).isoformat(), duration_minutes=30)
    early = await create_appt(client, second_org, contact_id=second_org["contacts"][0]["id"], starts_at=datetime.combine(day + timedelta(days=1), time(0, 30), IST).isoformat(), appointment_type="workshop")

    async def codes(**params) -> list[str]:
        response = await client.get(APPTS, params=params)
        assert response.status_code == 200, response.text
        return [i["code"] for i in response.json()["items"]]

    assert await codes(date_from=day.isoformat(), date_to=day.isoformat()) == [late["code"]]
    assert await codes(date_from=(day + timedelta(days=1)).isoformat()) == [early["code"]]
    assert await codes(date_from=day.isoformat()) == [late["code"], early["code"]]  # ordered by start
    assert await codes(date_from=day.isoformat(), appointment_type="workshop") == [early["code"]]
    assert await codes(date_from=day.isoformat(), organization_id=org["id"]) == [late["code"]]
    assert await codes(q=early["code"]) == [early["code"]]
    assert await codes(q=second_org["name"][-6:]) == [early["code"]]
    assert await codes(date_from=day.isoformat(), status=["scheduled", "confirmed"]) == [late["code"], early["code"]]
    assert await codes(date_from=day.isoformat(), status="cancelled") == []
    page = (await client.get(APPTS, params={"date_from": day.isoformat(), "limit": 1, "offset": 1})).json()
    assert (page["total"], page["limit"], page["offset"], [i["code"] for i in page["items"]]) == (2, 1, 1, [early["code"]])
    row = page["items"][0]
    assert set(row) == {"id", "code", "starts_at", "duration_minutes", "appointment_type", "status", "organization", "contact_name", "bdm"}


@pytest.mark.asyncio
async def test_list_parameter_validation(client, db_session):
    await bdm_with_org(client, db_session)
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "lost"}, {"date_from": "2030-02-02", "date_to": "2030-02-01"}, {"bdm_user_id": "00000000-0000-0000-0000-000000000000"}, {"q": "x" * 201}):
        assert (await client.get(APPTS, params=params)).status_code == 422, params


@pytest.mark.asyncio
async def test_unknown_id_is_404(client, db_session):
    await bdm_with_org(client, db_session)
    response = await client.get(f"{APPTS}/00000000-0000-0000-0000-000000000000")
    assert (response.status_code, response.json()["detail"]) == (404, "Appointment not found")


@pytest.mark.asyncio
async def test_school_and_agent_bdms_get_their_own_lists(client, db_session):
    manager = await make_manager(db_session)
    for bdm_type, module_type, foreign in (("school", "parent_orientation", "hod_meeting"), ("agent", "commission_discussion", "parent_orientation")):
        await login(client, await make_bdm(db_session, manager, bdm_type))
        org = await create_org(client)
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type=module_type))).status_code == 201
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type=foreign, starts_at=future(96)))).status_code == 422
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type="seminar_workshop", starts_at=future(120)))).status_code == 201


@pytest.mark.asyncio
async def test_patch_changes_only_sent_fields_and_audits_their_names(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, location="Gate 1")
    response = await client.patch(f"{APPTS}/{a['id']}", json={"location": "Gate 2", "purpose": "Demo"})
    assert response.status_code == 200, response.text
    b = response.json()["appointment"]
    assert (b["location"], b["purpose"], b["starts_at"], b["status"]) == ("Gate 2", "Demo", a["starts_at"], "scheduled")
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create", "bdm_appointment.update"]
    assert len(b["events"]) == 1  # an edit is not a transition


@pytest.mark.asyncio
async def test_noop_patch_writes_nothing(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, location="Gate 1")
    for body in ({}, {"location": "Gate 1", "duration_minutes": 60}):
        b = (await client.patch(f"{APPTS}/{a['id']}", json=body)).json()["appointment"]
        assert b["updated_at"] == a["updated_at"]
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create"]


@pytest.mark.asyncio
async def test_patch_contact_recopies_the_snapshot_and_refuses_another_orgs_contact(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    org = (await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "Ms Iyer", "designation": "TPO", "phone": "+91 99999 00000"})).json()["organization"]
    iyer = next(c for c in org["contacts"] if c["name"] == "Ms Iyer")
    a = await create_appt(client, org)
    b = (await client.patch(f"{APPTS}/{a['id']}", json={"contact_id": iyer["id"]})).json()["appointment"]
    assert (b["contact_id"], b["contact_name"], b["contact_designation"], b["contact_phone"]) == (iyer["id"], "Ms Iyer", "TPO", "+91 99999 00000")
    other = await create_org(client)
    response = await client.patch(f"{APPTS}/{a['id']}", json={"contact_id": other["contacts"][0]["id"]})
    assert (response.status_code, response.json()["detail"]) == (422, "Choose a contact of this organization")


@pytest.mark.asyncio
async def test_patch_rules(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(50))
    b = await create_appt(client, org, starts_at=future(51.5))
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"appointment_type": "agent_visit"})).status_code == 422
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"starts_at": future(80)})).status_code == 422  # unknown field
    clash = await client.patch(f"{APPTS}/{a['id']}", json={"duration_minutes": 120})  # now runs into b
    assert clash.status_code == 409 and clash.json()["detail"]["matches"][0]["code"] == b["code"]
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"duration_minutes": 120, "confirm_overlap": True})).status_code == 200
    await db_session.execute(sa_update(BdmAppointment).where(BdmAppointment.id == a["id"]).values(status="cancelled"))
    await db_session.commit()
    closed = await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "late"})
    assert (closed.status_code, closed.json()["detail"]) == (409, "Appointment is already cancelled")


@pytest.mark.asyncio
async def test_deleting_the_booked_contact_keeps_the_snapshot(client, db_session):
    """AC10 / A5 (Review Focus 3): bdm-002's delete route is unchanged and still succeeds."""
    _, _, org = await bdm_with_org(client, db_session)
    org = (await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "Ms Iyer"})).json()["organization"]
    rao = next(c for c in org["contacts"] if c["name"] == "Dr Rao")
    a = await create_appt(client, org, contact_id=rao["id"])
    assert (await client.delete(f"{ORGS}/{org['id']}/contacts/{rao['id']}")).status_code == 200
    b = (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]
    assert (b["contact_id"], b["contact_name"], b["contact_designation"]) == (None, "Dr Rao", "Principal")
