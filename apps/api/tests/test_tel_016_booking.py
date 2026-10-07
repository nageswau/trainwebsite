"""tel-016 -- a telecaller books a counselling appointment for a lead (spec §3; DEC-SCOPE-095 AP1-AP14): options, the lead's list and
POST /telecaller/leads/{id}/appointments. The shared test database is never truncated."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Appointment, AppointmentEvent, AuditLog, LeadStageHistory
from tests.tel016_helpers import OPTIONS, as_user, at, body, book, book_url, make_counselor, setup, student_appointment


# --- AC1 / AC2: a lead without a student account is booked; the stage moves ----------------------------------------------------------
@pytest.mark.asyncio
async def test_booking_a_lead_without_a_student_account_succeeds_and_moves_the_stage(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    response = await book(client, tel, lead, counselor, remarks="Bring marksheets", location="Room 2")
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["code"].startswith("CAP-") and len(out["code"]) == 10
    assert out["status"] == "scheduled" and out["duration_minutes"] == 60 and out["mode"] == "Online"
    assert out["appointment_type"] == "it_course_counselling" and out["type_label"] == "IT course counselling"
    assert out["counselor"]["id"] == str(counselor.id) and out["booked_by"]["id"] == str(tel.id)
    assert out["lead"]["id"] == str(lead.id) and out["lead"]["status"] == "counselling_scheduled"
    assert out["lead"]["status_label"] == "Counselling Scheduled"
    assert out["purpose"] == "Course fit" and out["remarks"] == "Bring marksheets" and out["location"] == "Room 2"
    assert [(e["from_status"], e["to_status"]) for e in out["events"]] == [(None, "scheduled")]
    assert out["permissions"] == {"can_confirm": False, "can_complete": False, "can_no_show": False, "can_cancel": True, "can_reschedule": True}
    appt = await db_session.scalar(select(Appointment).where(Appointment.id == uuid.UUID(out["id"])))
    assert appt.student_id is None and appt.lead_id == lead.id and appt.division == "it" and appt.staff_id == counselor.id
    history = (await db_session.scalars(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id))).all()
    assert [(h.from_stage, h.to_stage, h.event) for h in history] == [("follow_up", "counselling_scheduled", "appointment_booked")]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == out["id"], AuditLog.action == "lead_appointment.create"))
    assert audit is not None and "Bring" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_a_lead_past_follow_up_is_booked_but_its_stage_does_not_move(client, db_session):
    _, tel, counselor, lead = await setup(db_session, status="counselling_completed")
    response = await book(client, tel, lead, counselor)
    assert response.status_code == 201, response.text
    assert response.json()["lead"]["status"] == "counselling_completed"


@pytest.mark.asyncio
async def test_the_lead_list_shows_its_appointments_newest_first(client, db_session):
    manager, tel, counselor, lead = await setup(db_session)
    first = (await book(client, tel, lead, counselor)).json()
    await client.post(f"/api/v1/lead-appointments/{first['id']}/cancel", json={"reason": "Clash"})
    second = (await book(client, tel, lead, counselor, when=at(days=2))).json()
    response = await client.get(book_url(lead.id))
    assert response.status_code == 200, response.text
    assert [a["id"] for a in response.json()["items"]] == [second["id"], first["id"]]
    await as_user(client, manager)  # a manager reads, never acts
    items = (await client.get(book_url(lead.id))).json()["items"]
    assert items[0]["permissions"] == {"can_confirm": False, "can_complete": False, "can_no_show": False, "can_cancel": False, "can_reschedule": False}


# --- AP4: options by division --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_options_list_the_division_types_and_its_active_counselors_only(client, db_session):
    _, tel, counselor, lead = await setup(db_session, "overseas")
    inactive = await make_counselor(db_session, "overseas", active=False)
    other_division = await make_counselor(db_session, "it")
    await as_user(client, tel)
    response = await client.get(OPTIONS.format(lead.id))
    assert response.status_code == 200, response.text
    out = response.json()
    assert [t["key"] for t in out["types"]] == ["career_counselling", "overseas_counselling", "university_counselling"]
    ids = {c["id"] for c in out["counselors"]}
    assert str(counselor.id) in ids and str(inactive.id) not in ids and str(other_division.id) not in ids
    assert out["modes"] == ["Online", "Phone", "In person"] and out["duration_minutes"] == 60


# --- AC3 / AC4 / AP4 / AP7 / AP8: 422s -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"scheduled_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()},  # AC3: past
    {"scheduled_at": (datetime.now(UTC) + timedelta(days=367)).isoformat()},  # AP8: beyond the horizon
    {"appointment_type": "university_counselling"},  # not an IT type
    {"appointment_type": "nonsense"},
    {"mode": "Carrier pigeon"},
    {"meeting_link": "javascript:alert(1)"},
    {"purpose": "x" * 501},
    {"remarks": "bad\x00text"},
])
async def test_invalid_bookings_are_422(client, db_session, override):
    _, tel, counselor, lead = await setup(db_session)
    await as_user(client, tel)
    response = await client.post(book_url(lead.id), json=body(counselor) | override)
    assert response.status_code == 422, response.text
    assert await db_session.scalar(select(Appointment.id).where(Appointment.lead_id == lead.id)) is None


@pytest.mark.asyncio
async def test_an_it_lead_with_an_overseas_counselor_is_422(client, db_session):
    _, tel, _, lead = await setup(db_session)
    overseas = await make_counselor(db_session, "overseas")
    response = await book(client, tel, lead, overseas, appointment_type="it_course_counselling")
    assert response.status_code == 422, response.text
    assert "counselor" in response.text.lower()


@pytest.mark.asyncio
async def test_an_inactive_counselor_or_a_non_counselor_is_422(client, db_session):
    manager, tel, _, lead = await setup(db_session)
    inactive = await make_counselor(db_session, "it", active=False)
    assert (await book(client, tel, lead, inactive)).status_code == 422
    response = await client.post(book_url(lead.id), json=body(manager) | {"appointment_type": "career_counselling"})
    assert response.status_code == 422


# --- AP1: the counselor clash ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_clash_with_the_counselors_open_lead_appointment_is_409(client, db_session):
    manager, tel, counselor, lead = await setup(db_session)
    when = at()
    assert (await book(client, tel, lead, counselor, when=when)).status_code == 201
    _, tel2, _, lead2 = await setup(db_session)
    half_hour = (datetime.fromisoformat(when) + timedelta(minutes=30)).isoformat()
    response = await book(client, tel2, lead2, counselor, when=half_hour)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "counselor_busy" and len(detail["matches"]) == 1


@pytest.mark.asyncio
async def test_a_clash_with_a_student_appointment_is_409_and_back_to_back_is_fine(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    when = at()
    await student_appointment(db_session, counselor, when)
    assert (await book(client, tel, lead, counselor, when=when)).status_code == 409
    after = (datetime.fromisoformat(when) + timedelta(minutes=60)).isoformat()
    assert (await book(client, tel, lead, counselor, when=after)).status_code == 201


@pytest.mark.asyncio
async def test_a_cancelled_appointment_no_longer_blocks_the_slot(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    when = at()
    first = (await book(client, tel, lead, counselor, when=when)).json()
    assert (await client.post(f"/api/v1/lead-appointments/{first['id']}/cancel", json={"reason": "Lead asked"})).status_code == 200
    assert (await book(client, tel, lead, counselor, when=when)).status_code == 201


# --- AP5 / AP11 / scope ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_second_open_appointment_on_one_lead_is_409(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    assert (await book(client, tel, lead, counselor)).status_code == 201
    response = await book(client, tel, lead, counselor, when=at(days=3))
    assert response.status_code == 409 and "open" in response.text


@pytest.mark.asyncio
async def test_a_handed_over_lead_is_403_and_a_closed_lead_is_409(client, db_session):
    _, tel, counselor, lead = await setup(db_session, owner_id=None)
    lead.owner_id = counselor.id
    await db_session.commit()
    assert (await book(client, tel, lead, counselor)).status_code == 403
    _, tel2, counselor2, closed = await setup(db_session, status="not_interested")
    assert (await book(client, tel2, closed, counselor2)).status_code == 409


@pytest.mark.asyncio
async def test_a_manager_cannot_book_and_another_telecallers_lead_is_404(client, db_session):
    manager, tel, counselor, lead = await setup(db_session)
    await as_user(client, manager)
    assert (await client.post(book_url(lead.id), json=body(counselor))).status_code == 403
    _, other, _, _ = await setup(db_session)
    assert (await book(client, other, lead, counselor)).status_code == 404
    await as_user(client, counselor)  # a counselor is not a telecaller-route role
    assert (await client.get(book_url(lead.id))).status_code == 403


@pytest.mark.asyncio
async def test_booking_writes_one_creation_event(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    out = (await book(client, tel, lead, counselor)).json()
    events = (await db_session.scalars(select(AppointmentEvent).where(AppointmentEvent.appointment_id == uuid.UUID(out["id"])))).all()
    assert [(e.from_status, e.to_status, e.actor_user_id) for e in events] == [(None, "scheduled", tel.id)]
