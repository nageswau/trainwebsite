"""ccrm-003 (DEC-SCOPE-243): the counselor works the leads handed to them -- the CC8 stage moves (A1), the required next action (A2, A3),
follow-ups through the tel-011 service (A4), kept out of the telecaller's work (A5), the return clean-up (A6) and the admin owner check
(A7). The shared test database is never truncated: every assertion is about leads the test made."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Appointment, AuditLog, Enquiry, LeadFollowUp
from app.services.bdm_appointments import today_ist
from tests.tel004_helpers import make_user
from tests.tel016_helpers import book
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, setup

ADMIN = "/api/v1/admin/leads"
TEL_FOLLOW_UPS = "/api/v1/telecaller/follow-ups"


def fu_url(fu_id, action: str = "") -> str:
    return f"/api/v1/counselor/follow-ups/{fu_id}{'/' + action if action else ''}"


def soon(**delta) -> str:
    return (datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(hours=3))).isoformat()


def due(days: int = 2) -> str:
    return (today_ist(datetime.now(UTC)) + timedelta(days=days)).isoformat()


async def handed(client, db, division: str = "it", **over):
    manager, tel, counselor, row = await setup(db, division, **over)
    assert (await handover(client, tel, row, counselor)).status_code == 200
    await as_user(client, counselor)
    return manager, tel, counselor, row


async def move(client, row, to_stage: str, **body):
    return await client.post(c_url(row.id, "/stage"), json={"to_stage": to_stage, **body})


async def stored(db, row) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))


def field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


# --- A1 / A2: stage moves -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_moves_their_lead_with_a_next_action(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    response = await move(client, row, "counselling_completed", next_action="  Send the shortlist  ", next_action_due=due())
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "counselling_completed" and out["next_action"] == "Send the shortlist" and out["next_action_due"] == due()
    lead = await stored(db_session, row)
    assert lead.status == "counselling_completed" and lead.next_action == "Send the shortlist"
    detail = (await client.get(c_url(row.id))).json()
    assert detail["next_action"] == "Send the shortlist" and detail["next_action_due"] == due()
    assert detail["permissions"]["stage"] is True and detail["permissions"]["follow_up"] is True
    history = (await client.get(c_url(row.id, "/timeline"))).json()["items"]
    assert any(i["kind"] == "stage" and i["actor"]["id"] == str(counselor.id) for i in history)


@pytest.mark.asyncio
async def test_an_open_move_without_a_next_action_is_422_and_nothing_moves(client, db_session):
    _, _, _, row = await handed(client, db_session)
    assert field_error(await move(client, row, "qualified"), "next_action")
    assert field_error(await move(client, row, "qualified", next_action="Call back"), "next_action_due")
    assert (await stored(db_session, row)).status == "follow_up"


@pytest.mark.asyncio
async def test_a_stored_next_action_is_enough_for_the_next_move(client, db_session):
    _, _, _, row = await handed(client, db_session)
    assert (await move(client, row, "counselling_scheduled", next_action="Prepare documents", next_action_due=due())).status_code == 200
    assert (await move(client, row, "qualified")).status_code == 200
    assert (await stored(db_session, row)).next_action == "Prepare documents"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["interested", "wrong_number", "no_response", "application_enrollment", "converted", "new"])
async def test_stages_outside_the_cc8_list_are_422(client, db_session, stage):
    _, _, _, row = await handed(client, db_session)
    response = await move(client, row, stage, reason="x", next_action="Call", next_action_due=due())
    assert field_error(response, "to_stage")


@pytest.mark.asyncio
async def test_closing_needs_a_reason_and_cancels_follow_ups_and_appointments(client, db_session):
    _, tel, counselor, row = await setup(db_session)
    assert (await book(client, tel, row, counselor)).status_code == 201  # booked by the telecaller before the handover (D1)
    assert (await handover(client, tel, row, counselor)).status_code == 200
    await as_user(client, counselor)
    assert (await client.post(c_url(row.id, "/follow-ups"), json={"due_at": soon(), "reason": "fee_details"})).status_code == 201
    assert field_error(await move(client, row, "lost"), "reason")
    response = await move(client, row, "lost", reason="Chose another agency")
    assert response.status_code == 200, response.text
    assert (await stored(db_session, row)).status == "lost"
    statuses = (await db_session.scalars(select(LeadFollowUp.status).where(LeadFollowUp.lead_id == row.id))).all()
    assert statuses == ["cancelled"]
    appts = (await db_session.scalars(select(Appointment.status).where(Appointment.lead_id == row.id).execution_options(populate_existing=True))).all()
    assert appts == ["cancelled"]
    detail = (await client.get(c_url(row.id))).json()
    assert detail["permissions"]["stage"] is False and detail["permissions"]["follow_up"] is False


@pytest.mark.asyncio
async def test_a_closed_lead_is_not_reopened_by_the_counselor(client, db_session):
    _, _, _, row = await handed(client, db_session)
    assert (await move(client, row, "not_eligible", reason="No degree")).status_code == 200
    assert (await move(client, row, "follow_up", reason="Back", next_action="Call", next_action_due=due())).status_code == 403


@pytest.mark.asyncio
async def test_a_linked_lead_does_not_move_back_by_hand(client, db_session):
    _, _, _, row = await handed(client, db_session)
    row.status = "application_enrollment"
    await db_session.commit()
    assert field_error(await move(client, row, "qualified", next_action="Call", next_action_due=due()), "to_stage")


@pytest.mark.asyncio
async def test_scope_another_counselor_and_division_404_telecaller_403(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    other = await make_counselor(db_session)
    await as_user(client, other)
    assert (await move(client, row, "qualified", next_action="Call", next_action_due=due())).status_code == 404
    assert (await client.put(c_url(row.id, "/next-action"), json={"next_action": "x", "next_action_due": due()})).status_code == 404
    assert (await client.get(c_url(row.id, "/follow-ups"))).status_code == 404
    await as_user(client, tel)
    assert (await move(client, row, "qualified", next_action="Call", next_action_due=due())).status_code == 403
    counselor.division = "overseas"
    await db_session.commit()
    await as_user(client, counselor)
    assert (await move(client, row, "qualified", next_action="Call", next_action_due=due())).status_code == 404


# --- A3: the next action on its own ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_action_is_set_validated_and_audited_without_its_text(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    url = c_url(row.id, "/next-action")
    assert field_error(await client.put(url, json={"next_action": "   ", "next_action_due": due()}), "next_action")
    assert field_error(await client.put(url, json={"next_action": "x" * 201, "next_action_due": due()}), "next_action")
    assert field_error(await client.put(url, json={"next_action": "Call"}), "next_action_due")
    assert field_error(await client.put(url, json={"next_action": "Call", "next_action_due": due(-1)}), "next_action_due")
    response = await client.put(url, json={"next_action": "Call the parents", "next_action_due": due(0)})
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] == "Call the parents" and response.json()["next_action_due"] == due(0)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(row.id), AuditLog.action == "lead.next_action"))
    assert audit.user_id == counselor.id and "Call the parents" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_an_overdue_next_action_keeps_its_date_when_only_the_text_changes(client, db_session):
    _, _, _, row = await handed(client, db_session)
    past = date.today() - timedelta(days=3)
    row.next_action, row.next_action_due = "Old", past
    await db_session.commit()
    response = await client.put(c_url(row.id, "/next-action"), json={"next_action": "Newer", "next_action_due": past.isoformat()})
    assert response.status_code == 200, response.text
    detail = (await client.get(c_url(row.id))).json()
    assert detail["next_action_overdue"] is True


@pytest.mark.asyncio
async def test_next_action_on_a_closed_lead_is_409(client, db_session):
    _, _, _, row = await handed(client, db_session)
    assert (await move(client, row, "not_interested", reason="Busy")).status_code == 200
    assert (await client.put(c_url(row.id, "/next-action"), json={"next_action": "Call", "next_action_due": due()})).status_code == 409


# --- A4: follow-ups ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_creates_reschedules_completes_and_cancels_follow_ups(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    url = c_url(row.id, "/follow-ups")
    first = await client.post(url, json={"due_at": soon(), "reason": "waiting_documents", "next_action": "Collect transcripts"})
    assert first.status_code == 201, first.text
    fu = first.json()
    assert fu["can_change"] is True and fu["created_by"]["id"] == str(counselor.id)
    listed = (await client.get(url)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == fu["id"]
    patched = await client.patch(fu_url(fu["id"]), json={"due_at": soon(days=2)})
    assert patched.status_code == 200, patched.text
    assert (await client.post(fu_url(fu["id"], "complete"))).json()["status"] == "done"
    assert (await client.post(fu_url(fu["id"], "complete"))).status_code == 409
    second = (await client.post(url, json={"due_at": soon(), "reason": "fee_details"})).json()
    cancelled = await client.post(fu_url(second["id"], "cancel"), json={"reason": "Student travelling"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert field_error(await client.post(url, json={"due_at": soon(hours=-1), "reason": "fee_details"}), "due_at")

    await as_user(client, tel)  # D1: the telecaller reads them, never changes them
    tel_list = (await client.get(f"/api/v1/telecaller/leads/{row.id}/follow-ups")).json()
    assert tel_list["total"] == 2 and all(i["can_change"] is False for i in tel_list["items"])
    third = await db_session.scalar(select(LeadFollowUp.id).where(LeadFollowUp.lead_id == row.id, LeadFollowUp.status == "open"))
    assert third is None
    assert (await client.post(f"{TEL_FOLLOW_UPS}/{fu['id']}/complete")).status_code in (403, 409)


@pytest.mark.asyncio
async def test_another_counselor_gets_404_on_a_follow_up(client, db_session):
    _, _, _, row = await handed(client, db_session)
    fu = (await client.post(c_url(row.id, "/follow-ups"), json={"due_at": soon(), "reason": "fee_details"})).json()
    await as_user(client, await make_counselor(db_session))
    assert (await client.post(fu_url(fu["id"], "complete"))).status_code == 404
    assert (await client.patch(fu_url(fu["id"]), json={"notes": "x"})).status_code == 404
    assert (await client.post(c_url(row.id, "/follow-ups"), json={"due_at": soon(), "reason": "fee_details"})).status_code == 404


@pytest.mark.asyncio
async def test_move_to_follow_up_from_a_counselor_needs_a_next_action(client, db_session):
    _, _, _, row = await handed(client, db_session, status="qualified")
    url = c_url(row.id, "/follow-ups")
    assert field_error(await client.post(url, json={"due_at": soon(), "reason": "fee_details", "move_to_follow_up": True}), "next_action")
    assert (await db_session.scalar(select(LeadFollowUp.id).where(LeadFollowUp.lead_id == row.id))) is None


# --- A5: a counselor's follow-up is not the telecaller's work ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_telecaller_day_list_and_dashboard_leave_out_counselor_follow_ups(client, db_session):
    _, tel, _, row = await handed(client, db_session)
    assert (await client.post(c_url(row.id, "/follow-ups"), json={"due_at": soon(hours=1), "reason": "fee_details"})).status_code == 201
    await as_user(client, tel)
    day = (await client.get(TEL_FOLLOW_UPS, params={"view": "day"})).json()
    assert all(i["lead"]["id"] != str(row.id) for i in day["items"]) and day["counts"]["day"] == 0
    overdue = (await client.get(TEL_FOLLOW_UPS, params={"view": "overdue"})).json()
    assert overdue["counts"]["overdue"] == 0
    mine = (await client.get("/api/v1/telecaller/leads", params={"follow_up": "today"})).json()
    assert all(i["id"] != str(row.id) for i in mine["items"])


# --- A6: the return ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_return_cancels_counselor_follow_ups_and_clears_the_next_action(client, db_session):
    _, _, _, row = await handed(client, db_session)
    assert (await client.put(c_url(row.id, "/next-action"), json={"next_action": "Call", "next_action_due": due()})).status_code == 200
    assert (await client.post(c_url(row.id, "/follow-ups"), json={"due_at": soon(), "reason": "fee_details"})).status_code == 201
    assert (await client.post(c_url(row.id, "/return"), json={"reason": "Wants an IT course instead"})).status_code == 200
    lead = await stored(db_session, row)
    assert lead.owner_id is None and lead.next_action is None and lead.next_action_due is None
    fu = await db_session.scalar(select(LeadFollowUp).where(LeadFollowUp.lead_id == row.id).execution_options(populate_existing=True))
    assert fu.status == "cancelled" and fu.cancel_reason == "Returned to telecaller"


# --- A7: admin owner reassignment -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_owner_must_be_an_active_counselor_of_the_division(client, db_session):
    _, tel, counselor, row = await setup(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    other_division = await make_counselor(db_session, "overseas")
    inactive = await make_counselor(db_session, active=False)
    await as_user(client, admin)
    url = f"{ADMIN}/{row.id}"
    for owner in (admin.id, tel.id, other_division.id, inactive.id, "not-a-uuid"):
        assert field_error(await client.patch(url, json={"owner_id": str(owner)}), "owner_id"), owner
    assert (await stored(db_session, row)).owner_id is None
    assert (await client.patch(url, json={"owner_id": str(counselor.id)})).status_code == 200
    assert (await stored(db_session, row)).owner_id == counselor.id
    assert (await client.patch(url, json={"owner_id": None})).status_code == 200
    assert (await stored(db_session, row)).owner_id is None
