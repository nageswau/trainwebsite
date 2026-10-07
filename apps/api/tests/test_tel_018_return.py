"""tel-018 -- the counselor returns a lead (spec §3.2; T19; DEC-SCOPE-098 HO4; AC2)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Appointment, AuditLog, Enquiry, LeadStageHistory
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, make_student, setup


async def _returned(client, db, *, status="follow_up"):
    manager, tel, counselor, lead = await setup(db, status=status)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return manager, tel, counselor, lead


@pytest.mark.asyncio
async def test_a_return_reopens_the_lead_for_the_telecaller(client, db_session):
    """AC2: the lead goes back to Follow-up, the counselor is cleared and the telecaller can write again."""
    _, tel, counselor, lead = await _returned(client, db_session, status="counselling_completed")
    response = await client.post(c_url(lead.id, "/return"), json={"reason": "  Needs a fee discussion first  "})
    assert response.status_code == 200, response.text
    row = await db_session.scalar(select(Enquiry).where(Enquiry.id == lead.id).execution_options(populate_existing=True))
    assert (row.status, row.owner_id) == ("follow_up", None)
    history = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id, LeadStageHistory.event == "returned"))
    assert (history.from_stage, history.reason, history.actor_user_id) == ("counselling_completed", "Needs a fee discussion first", counselor.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(lead.id), AuditLog.action == "lead.return"))
    assert audit.metadata_json == {"counselor_id": str(counselor.id)}  # never the reason text
    assert (await client.get(c_url(lead.id))).status_code == 404  # out of the counselor's scope now
    await as_user(client, tel)
    detail = (await client.get(f"/api/v1/telecaller/leads/{lead.id}")).json()
    assert (detail["read_only"], detail["counselor"]) == (False, None)
    assert (await client.patch(f"/api/v1/telecaller/leads/{lead.id}", json={"priority": "hot"})).status_code == 200
    rows = (await client.get(f"/api/v1/telecaller/leads/{lead.id}/timeline")).json()["items"]
    returned = next(r for r in rows if r["kind"] == "stage" and r["event"] == "returned")  # QA-03: the client names the return
    assert returned["reason"] == "Needs a fee discussion first"
    assert next(r for r in rows if r["kind"] == "priority")["event"] is None


@pytest.mark.asyncio
async def test_a_return_from_follow_up_is_still_in_the_history(client, db_session):
    _, _, _, lead = await _returned(client, db_session, status="follow_up")
    assert (await client.post(c_url(lead.id, "/return"), json={"reason": "Wrong course"})).status_code == 200
    history = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id, LeadStageHistory.event == "returned"))
    assert (history.from_stage, history.to_stage, history.reason) == ("follow_up", "follow_up", "Wrong course")


@pytest.mark.asyncio
async def test_a_return_needs_a_reason(client, db_session):
    _, _, _, lead = await _returned(client, db_session)
    for body in ({}, {"reason": "   "}, {"reason": "x" * 501}):
        assert (await client.post(c_url(lead.id, "/return"), json=body)).status_code == 422


@pytest.mark.asyncio
async def test_a_return_cancels_the_open_counselling_appointment(client, db_session):
    _, tel, counselor, lead = await _returned(client, db_session, status="counselling_scheduled")
    appt = Appointment(division="it", lead_id=lead.id, staff_id=counselor.id, scheduled_at=datetime.now(UTC) + timedelta(days=2),
                       appointment_type="it_course_counselling", mode="Online", status="scheduled", appointment_code="APT-T18-" + str(lead.id)[:8],
                       duration_minutes=60, booked_by_user_id=tel.id)
    db_session.add(appt)
    await db_session.commit()
    assert (await client.post(c_url(lead.id, "/return"), json={"reason": "Not ready"})).status_code == 200
    stored = await db_session.scalar(select(Appointment).where(Appointment.id == appt.id).execution_options(populate_existing=True))
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_a_linked_lead_cannot_be_returned(client, db_session):
    _, _, counselor, lead = await _returned(client, db_session, status="counselling_completed")
    student = await make_student(db_session)
    assert (await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(student.id)})).status_code == 200
    response = await client.post(c_url(lead.id, "/return"), json={"reason": "Oops"})
    assert (response.status_code, response.json()["detail"]) == (409, "Unlink the student before returning the lead")


@pytest.mark.asyncio
async def test_only_the_assigned_counselor_returns(client, db_session):
    manager, tel, _, lead = await _returned(client, db_session)
    await as_user(client, await make_counselor(db_session, "it"))
    assert (await client.post(c_url(lead.id, "/return"), json={"reason": "x"})).status_code == 404
    for actor in (tel, manager):
        await as_user(client, actor)
        assert (await client.post(c_url(lead.id, "/return"), json={"reason": "x"})).status_code == 403
