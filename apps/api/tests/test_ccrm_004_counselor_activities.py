"""ccrm-004 (DEC-SCOPE-259): the counselor logs activity on the leads handed to them -- calls (LG1), WhatsApp and email (LG2), meetings
(LG3) and appointment outcome notes (LG4), all in the lead timeline; telecaller work never counts it (LG5). The shared test database is
never truncated: every assertion is about rows the test made."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Appointment, AuditLog, Enquiry, LeadCall, LeadFollowUp, LeadMeeting, LeadMessage
from tests.tel016_helpers import action_url, book
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, setup
from tests.test_tel_013_messages import template
from tests.test_tel_014_email import smtp_on  # noqa: F401 -- fixture

REMARKS = "Parent wants Canada secret-remarks-91"
NOTES = "Discussed shortlist secret-meeting-notes-37"
OUTCOME = "Student picked UK secret-outcome-55"


async def handed(client, db, division: str = "overseas", **over):
    manager, tel, counselor, row = await setup(db, division, **over)
    assert (await handover(client, tel, row, counselor)).status_code == 200
    await as_user(client, counselor)
    return manager, tel, counselor, row


def call_body(**over) -> dict:
    return {"duration_seconds": 125, "call_type": "outgoing", "outcome": "need_information", "remarks": REMARKS} | over


def meeting_body(**over) -> dict:
    return {"occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(), "mode": "In person", "notes": NOTES} | over


async def stored(db, row) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))


async def close(db, row, stage: str = "lost") -> None:
    lead = await stored(db, row)
    lead.status = stage
    await db.commit()


async def timeline(client, row) -> list[dict]:
    response = await client.get(c_url(row.id, "/timeline"))
    assert response.status_code == 200, response.text
    return response.json()["items"]


def field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


# --- LG1: calls ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_logs_a_call_with_no_stage_effect_and_it_shows_in_the_timeline(client, db_session, caplog):
    _, _, counselor, row = await handed(client, db_session)
    with caplog.at_level(logging.INFO):
        response = await client.post(c_url(row.id, "/calls"), json=call_body(outcome="not_interested"))
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["call"]["caller"]["id"] == str(counselor.id) and out["call"]["can_change"] is True and out["follow_up_id"] is None
    assert out["lead"]["status"] == "follow_up"  # LG1: a counselor's call never moves the stage (no closing outcome)
    assert (await stored(db_session, row)).status == "follow_up"
    listed = (await client.get(c_url(row.id, "/calls"))).json()
    assert [c["id"] for c in listed["items"]] == [out["call"]["id"]]
    assert any(i["kind"] == "call" and i["actor"]["id"] == str(counselor.id) for i in await timeline(client, row))
    assert REMARKS not in caplog.text  # LG8


@pytest.mark.asyncio
async def test_a_follow_up_outcome_needs_and_creates_the_counselors_follow_up(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    assert field_error(await client.post(c_url(row.id, "/calls"), json=call_body(outcome="call_back_requested")), "next_follow_up")
    due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = await client.post(c_url(row.id, "/calls"), json=call_body(outcome="call_back_requested", next_follow_up={"due_at": due, "reason": "counselor_call"}))
    assert response.status_code == 201, response.text
    fu = await db_session.get(LeadFollowUp, uuid.UUID(response.json()["follow_up_id"]))
    assert fu.created_by_user_id == counselor.id and fu.status == "open"


@pytest.mark.asyncio
async def test_counselor_edits_and_deletes_their_own_call_the_same_day(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    call_id = (await client.post(c_url(row.id, "/calls"), json=call_body())).json()["call"]["id"]
    edited = await client.patch(f"/api/v1/counselor/calls/{call_id}", json={"duration_seconds": 300})
    assert edited.status_code == 200 and edited.json()["duration_seconds"] == 300
    await as_user(client, tel)  # the telecaller reads the handed-over lead's calls, read only
    seen = (await client.get(f"/api/v1/telecaller/leads/{row.id}/calls")).json()["items"]
    assert [c["can_change"] for c in seen] == [False]
    assert (await client.delete(f"/api/v1/telecaller/calls/{call_id}")).status_code == 403
    await as_user(client, counselor)
    assert (await client.delete(f"/api/v1/counselor/calls/{call_id}")).status_code == 204
    assert await db_session.get(LeadCall, uuid.UUID(call_id)) is None


@pytest.mark.asyncio
async def test_call_scope_role_and_closed_lead(client, db_session):
    _, tel, _, row = await handed(client, db_session)
    other = await make_counselor(db_session, "overseas")
    await as_user(client, other)
    assert (await client.post(c_url(row.id, "/calls"), json=call_body())).status_code == 404
    assert (await client.get(c_url(row.id, "/calls"))).status_code == 404
    await as_user(client, tel)
    assert (await client.post(c_url(row.id, "/calls"), json=call_body())).status_code == 403
    _, _, _, closed = await handed(client, db_session)
    await close(db_session, closed)
    assert (await client.post(c_url(closed.id, "/calls"), json=call_body())).status_code == 409


# --- LG2: WhatsApp and email ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_records_a_whatsapp_send_and_deletes_it_the_same_day(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    tpl = await template(db_session)
    templates = await client.get("/api/v1/telecaller/templates?channel=whatsapp&active=true&limit=100")
    assert templates.status_code == 200  # LG2: the counselor reads the active library
    rendered = await client.get(c_url(row.id, f"/render?template_id={tpl.id}"))
    assert rendered.status_code == 200, rendered.text
    response = await client.post(c_url(row.id, "/messages"), json={"channel": "whatsapp", "template_id": str(tpl.id), "body": "Hello there"})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["sender"]["id"] == str(counselor.id) and item["can_delete"] is True
    assert [m["id"] for m in (await client.get(c_url(row.id, "/messages"))).json()["items"]] == [item["id"]]
    assert any(i["kind"] == "message" for i in await timeline(client, row))
    assert (await client.delete(f"/api/v1/counselor/messages/{item['id']}")).status_code == 204
    assert await db_session.get(LeadMessage, uuid.UUID(item["id"])) is None


@pytest.mark.asyncio
async def test_counselor_emails_their_lead(client, db_session, smtp_on, lead_emails_enqueued):  # noqa: F811
    _, _, counselor, row = await handed(client, db_session)
    response = await client.post(c_url(row.id, "/messages"), json={"channel": "email", "subject": "Shortlist", "body": "Please see the list"})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["delivery_status"] == "queued" and item["can_delete"] is False and item["sender"]["id"] == str(counselor.id)
    assert lead_emails_enqueued == [(item["id"], 0)]


@pytest.mark.asyncio
async def test_message_scope_role_and_closed_lead(client, db_session):
    _, tel, _, row = await handed(client, db_session)
    body = {"channel": "whatsapp", "body": "Hi"}
    other = await make_counselor(db_session, "overseas")
    await as_user(client, other)
    assert (await client.post(c_url(row.id, "/messages"), json=body)).status_code == 404
    await as_user(client, tel)
    assert (await client.post(c_url(row.id, "/messages"), json=body)).status_code == 403
    assert (await client.post(f"/api/v1/telecaller/leads/{row.id}/messages", json=body)).status_code == 403  # handed over
    _, _, _, closed = await handed(client, db_session)
    await close(db_session, closed)
    assert (await client.post(c_url(closed.id, "/messages"), json=body)).status_code == 409


# --- LG3: meetings ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_records_a_meeting_and_it_shows_in_the_timeline(client, db_session, caplog):
    _, _, counselor, row = await handed(client, db_session)
    with caplog.at_level(logging.INFO):
        response = await client.post(c_url(row.id, "/meetings"), json=meeting_body())
    assert response.status_code == 201, response.text
    item = response.json()
    assert (item["mode"], item["notes"], item["author"]["id"]) == ("In person", NOTES, str(counselor.id))
    assert [m["id"] for m in (await client.get(c_url(row.id, "/meetings"))).json()["items"]] == [item["id"]]
    entry = next(i for i in await timeline(client, row) if i["kind"] == "meeting")
    assert entry["from_value"] == "In person" and entry["reason"] == NOTES and entry["actor"]["id"] == str(counselor.id)
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "lead_meeting.create", AuditLog.entity_id == str(row.id)))).all()
    assert len(audit) == 1 and NOTES not in str(audit[0].metadata_json)
    assert NOTES not in caplog.text


@pytest.mark.asyncio
async def test_meeting_validation_scope_and_closed_lead(client, db_session):
    _, tel, _, row = await handed(client, db_session)
    assert field_error(await client.post(c_url(row.id, "/meetings"), json=meeting_body(mode="Carrier pigeon")), "mode")
    assert field_error(await client.post(c_url(row.id, "/meetings"), json=meeting_body(notes="  ")), "notes")
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    assert field_error(await client.post(c_url(row.id, "/meetings"), json=meeting_body(occurred_at=future)), "occurred_at")
    old = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    assert field_error(await client.post(c_url(row.id, "/meetings"), json=meeting_body(occurred_at=old)), "occurred_at")
    other = await make_counselor(db_session, "overseas")
    await as_user(client, other)
    assert (await client.post(c_url(row.id, "/meetings"), json=meeting_body())).status_code == 404
    await as_user(client, tel)
    assert (await client.get(c_url(row.id, "/meetings"))).status_code == 403
    _, _, _, closed = await handed(client, db_session)
    await close(db_session, closed)
    assert (await client.post(c_url(closed.id, "/meetings"), json=meeting_body())).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(LeadMeeting).where(LeadMeeting.lead_id.in_([row.id, closed.id]))) == 0


# --- LG4: appointment outcome notes ---------------------------------------------------------------------------------------------------
async def started_appointment(client, db, tel, row, counselor) -> Appointment:
    lead = await stored(db, row)
    owner = lead.owner_id
    lead.owner_id = None  # book as the telecaller before the handover rule applies
    await db.commit()
    response = await book(client, tel, row, counselor)
    assert response.status_code == 201, response.text
    appt = await db.get(Appointment, uuid.UUID(response.json()["id"]))
    appt.scheduled_at = datetime.now(UTC) - timedelta(minutes=30)
    lead = await stored(db, row)
    lead.owner_id = owner
    await db.commit()
    await as_user(client, counselor)
    return appt


@pytest.mark.asyncio
async def test_completing_an_appointment_keeps_its_outcome_notes(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    appt = await started_appointment(client, db_session, tel, row, counselor)
    assert field_error(await client.post(action_url(appt.id, "complete"), json={"outcome_notes": "x" * 2001}), "outcome_notes")
    response = await client.post(action_url(appt.id, "complete"), json={"outcome_notes": f"  {OUTCOME}  "})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed" and response.json()["outcome_notes"] == OUTCOME
    stored_appt = await db_session.scalar(select(Appointment).where(Appointment.id == appt.id).execution_options(populate_existing=True))
    assert stored_appt.outcome_notes == OUTCOME
    entry = next(i for i in await timeline(client, row) if i["kind"] == "appointment" and i["to_value"] == "completed")
    assert entry["reason"] == OUTCOME


@pytest.mark.asyncio
async def test_completing_without_a_body_still_works(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    appt = await started_appointment(client, db_session, tel, row, counselor)
    response = await client.post(action_url(appt.id, "complete"))
    assert response.status_code == 200, response.text
    assert response.json()["outcome_notes"] is None


# --- LG7: the detail --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_detail_offers_activity_and_the_whatsapp_number(client, db_session):
    _, _, _, row = await handed(client, db_session)
    detail = (await client.get(c_url(row.id))).json()
    assert detail["permissions"]["activity"] is True and detail["whatsapp_to"] == "919876543210"
    await close(db_session, row)
    assert (await client.get(c_url(row.id))).json()["permissions"]["activity"] is False
