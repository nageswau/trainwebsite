"""tel-016 -- after the booking (spec §3; DEC-SCOPE-095 AP2, AP3, AP9, AP10, AP12, AP13): the counselor's list, the shared action routes,
the legacy overseas PATCH guard and the IT counselor's Appointments section. The shared test database is never truncated."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import Appointment, AuditLog, Enquiry, LeadStageHistory
from tests.tel016_helpers import COUNSELOR_LIST, action_url, as_user, at, book, make_counselor, setup


async def booked(client, db, division: str = "it", **kwargs):
    manager, tel, counselor, lead = await setup(db, division)
    out = (await book(client, tel, lead, counselor, **kwargs)).json()
    return manager, tel, counselor, lead, out


async def started(db, appt_id) -> None:
    """Move an appointment's start into the past (a booking itself must be in the future)."""
    await db.execute(update(Appointment).where(Appointment.id == uuid.UUID(appt_id)).values(scheduled_at=datetime.fromisoformat(at(days=-1))))
    await db.commit()


async def stage(db, lead) -> str:
    return await db.scalar(select(Enquiry.status).where(Enquiry.id == lead.id).execution_options(populate_existing=True))


# --- AP2: the counselor's actions; AC2 completion ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_counselor_confirms_then_completes_and_the_stage_moves(client, db_session):
    _, _, counselor, lead, out = await booked(client, db_session)
    await as_user(client, counselor)
    response = await client.post(action_url(out["id"], "confirm"))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    assert (await client.post(action_url(out["id"], "complete"))).status_code == 422  # AP9: not started yet
    await started(db_session, out["id"])
    response = await client.post(action_url(out["id"], "complete"))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed" and response.json()["lead"]["status"] == "counselling_completed"
    assert await stage(db_session, lead) == "counselling_completed"
    assert [(e["from_status"], e["to_status"]) for e in response.json()["events"]] == [(None, "scheduled"), ("scheduled", "confirmed"),
                                                                                       ("confirmed", "completed")]
    # AP2: a finished appointment is 409 for every action
    for action, payload in (("confirm", None), ("no-show", None), ("cancel", {"reason": "x"}), ("reschedule", {"scheduled_at": at(days=2)})):
        assert (await client.post(action_url(out["id"], action), json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_a_no_show_returns_the_lead_to_follow_up(client, db_session):
    _, _, counselor, lead, out = await booked(client, db_session)
    await as_user(client, counselor)
    assert (await client.post(action_url(out["id"], "no-show"))).status_code == 422  # AP9
    await started(db_session, out["id"])
    response = await client.post(action_url(out["id"], "no-show"))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "no_show" and await stage(db_session, lead) == "follow_up"
    events = (await db_session.scalars(select(LeadStageHistory.event).where(LeadStageHistory.lead_id == lead.id).order_by(LeadStageHistory.position))).all()
    assert events == ["appointment_booked", "appointment_released"]


@pytest.mark.asyncio
async def test_the_telecaller_cancels_with_a_reason_and_the_lead_returns_to_follow_up(client, db_session):
    _, tel, _, lead, out = await booked(client, db_session)
    await as_user(client, tel)
    assert (await client.post(action_url(out["id"], "cancel"), json={})).status_code == 422
    assert (await client.post(action_url(out["id"], "cancel"), json={"reason": "  "})).status_code == 422
    response = await client.post(action_url(out["id"], "cancel"), json={"reason": "Lead travelling"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled" and response.json()["events"][-1]["reason"] == "Lead travelling"
    assert await stage(db_session, lead) == "follow_up"


@pytest.mark.asyncio
async def test_reschedule_keeps_history_and_does_not_move_the_stage(client, db_session):
    _, tel, counselor, lead, out = await booked(client, db_session)
    await as_user(client, counselor)
    new_time = at(days=2)
    response = await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": new_time, "reason": "Counselor on leave"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "rescheduled" and datetime.fromisoformat(body["scheduled_at"]) == datetime.fromisoformat(new_time)
    last = body["events"][-1]
    assert last["to_status"] == "rescheduled" and datetime.fromisoformat(last["old_scheduled_at"]) == datetime.fromisoformat(out["scheduled_at"])
    assert datetime.fromisoformat(last["new_scheduled_at"]) == datetime.fromisoformat(new_time) and last["reason"] == "Counselor on leave"
    assert await stage(db_session, lead) == "counselling_scheduled"
    await as_user(client, tel)  # the telecaller may reschedule too; past -> 422
    past = (datetime.fromisoformat(at(days=-1))).isoformat()
    assert (await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": past})).status_code == 422
    assert (await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": at(days=3)})).status_code == 200


@pytest.mark.asyncio
async def test_a_reschedule_onto_another_booking_is_409_but_onto_its_own_slot_is_fine(client, db_session):
    _, _, counselor, _, out = await booked(client, db_session)
    _, tel2, _, lead2 = await setup(db_session)
    other_time = at(days=4)
    assert (await book(client, tel2, lead2, counselor, when=other_time)).status_code == 201
    await as_user(client, counselor)
    clash = (datetime.fromisoformat(other_time) + timedelta(minutes=15)).isoformat()
    response = await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": clash})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "counselor_busy"
    shifted = (datetime.fromisoformat(out["scheduled_at"]) + timedelta(minutes=30)).isoformat()
    assert (await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": shifted})).status_code == 200


# --- AP2 scope and role ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_and_role_refusals(client, db_session):
    manager, tel, _, _, out = await booked(client, db_session)
    other_counselor = await make_counselor(db_session, "it")
    await as_user(client, other_counselor)
    assert (await client.post(action_url(out["id"], "confirm"))).status_code == 404  # another counselor's: out of scope
    await as_user(client, tel)
    assert (await client.post(action_url(out["id"], "confirm"))).status_code == 403  # the telecaller never confirms
    await started(db_session, out["id"])
    assert (await client.post(action_url(out["id"], "complete"))).status_code == 403
    assert (await client.post(action_url(out["id"], "no-show"))).status_code == 403
    await as_user(client, manager)
    assert (await client.post(action_url(out["id"], "cancel"), json={"reason": "x"})).status_code == 404
    _, other_tel, _, _ = await setup(db_session)
    await as_user(client, other_tel)
    assert (await client.post(action_url(out["id"], "cancel"), json={"reason": "x"})).status_code == 404
    assert (await client.post(action_url(uuid.uuid4(), "confirm"))).status_code == 404


@pytest.mark.asyncio
async def test_a_telecaller_cannot_act_once_the_lead_is_handed_over(client, db_session):
    _, tel, counselor, lead, out = await booked(client, db_session)
    await db_session.execute(update(Enquiry).where(Enquiry.id == lead.id).values(owner_id=counselor.id))
    await db_session.commit()
    await as_user(client, tel)
    assert (await client.post(action_url(out["id"], "cancel"), json={"reason": "x"})).status_code == 403


# --- AP13: the counselor's list --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_counselor_lists_only_their_own_lead_appointments_with_contact_details(client, db_session):
    _, _, counselor, lead, out = await booked(client, db_session, "overseas")
    _, _, _, _, someone_elses = await booked(client, db_session, "overseas")
    await as_user(client, counselor)
    response = await client.get(COUNSELOR_LIST)
    assert response.status_code == 200, response.text
    page = response.json()
    assert [a["id"] for a in page["items"]] == [out["id"]] and page["total"] == 1
    row = page["items"][0]
    assert row["lead"] == {"id": str(lead.id), "lead_code": lead.lead_code, "name": lead.name, "phone": "9876543210", "email": lead.email,
                           "status": "counselling_scheduled", "status_label": "Counselling Scheduled"}
    assert row["permissions"]["can_confirm"] is True and row["permissions"]["can_complete"] is False
    assert someone_elses["id"] not in {a["id"] for a in page["items"]}
    assert (await client.get(f"{COUNSELOR_LIST}?status=completed")).json()["total"] == 0
    assert (await client.get(f"{COUNSELOR_LIST}?status=bogus")).status_code == 422


@pytest.mark.asyncio
async def test_only_counselors_read_the_counselor_list(client, db_session):
    _, tel, _, _ = await setup(db_session)
    await as_user(client, tel)
    assert (await client.get(COUNSELOR_LIST)).status_code == 403


# --- AP15: closing a lead cancels its open appointment (owner answer 2026-10-07, as tel-011 F4 does for follow-ups) -----------------
@pytest.mark.asyncio
async def test_closing_a_lead_cancels_its_open_appointment(client, db_session):
    _, tel, counselor, lead, out = await booked(client, db_session)
    await as_user(client, tel)
    response = await client.post(f"/api/v1/telecaller/leads/{lead.id}/stage", json={"to_stage": "not_interested", "reason": "Joined elsewhere"})
    assert response.status_code == 200, response.text
    assert await stage(db_session, lead) == "not_interested"  # the close stands -- no release back to Follow-up
    items = (await client.get(f"/api/v1/telecaller/leads/{lead.id}/appointments")).json()["items"]
    assert items[0]["status"] == "cancelled"
    last = items[0]["events"][-1]
    assert (last["from_status"], last["to_status"], last["reason"], last["actor_name"]) == ("scheduled", "cancelled", "Lead closed", tel.full_name)
    assert items[0]["permissions"]["can_cancel"] is False
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == out["id"], AuditLog.action == "lead_appointment.cancel"))
    assert audit is not None and audit.metadata_json["reason"] == "lead_closed"
    await as_user(client, counselor)  # the counselor's slot is free again
    assert (await client.get(f"{COUNSELOR_LIST}?status=cancelled")).json()["items"][0]["id"] == out["id"]


@pytest.mark.asyncio
async def test_closing_a_lead_leaves_finished_appointments_alone(client, db_session):
    _, tel, counselor, lead, out = await booked(client, db_session)
    await as_user(client, counselor)
    await started(db_session, out["id"])
    assert (await client.post(action_url(out["id"], "complete"))).status_code == 200
    await as_user(client, tel)
    assert (await client.post(f"/api/v1/telecaller/leads/{lead.id}/stage", json={"to_stage": "lost", "reason": "No budget"})).status_code == 200
    items = (await client.get(f"/api/v1/telecaller/leads/{lead.id}/appointments")).json()["items"]
    assert items[0]["status"] == "completed" and len(items[0]["events"]) == 2


# --- AP12: the legacy overseas PATCH cannot touch a lead appointment ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_legacy_overseas_patch_is_404_for_a_lead_appointment(client, db_session):
    _, _, counselor, lead, out = await booked(client, db_session, "overseas")
    await as_user(client, counselor)
    response = await client.patch(f"/api/v1/workflows/overseas/appointments/{out['id']}", json={"status": "completed"})
    assert response.status_code == 404, response.text
    assert await stage(db_session, lead) == "counselling_scheduled"


# --- AP14: the IT counselor's Appointments section --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_it_counselor_has_an_appointments_section(client, db_session):
    counselor = await make_counselor(db_session, "it")
    await as_user(client, counselor)
    response = await client.get("/api/v1/portal/it/counselor/appointments")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Appointments" and response.json()["rows"] == []
