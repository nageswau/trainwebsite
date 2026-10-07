"""tel-010 -- call logging (spec §1-§4; DEC-SCOPE-096 CL1-CL4, D1-D10): log a call, its pipeline effect, the optional next follow-up,
the lead's call list, same-day edit/delete, the day counts and the follow-up card's last call. The shared test database is never
truncated, so every count narrows to users created by the test."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadCall, LeadFollowUp, LeadStageHistory
from app.services import lead_calls
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

LEADS = "/api/v1/telecaller/leads"
CALLS = "/api/v1/telecaller/calls"
REMARKS = "Spoke to the mother; secret-remark-7f3"


def calls_url(lead_id) -> str:
    return f"{LEADS}/{lead_id}/calls"


def call_url(call_id) -> str:
    return f"{CALLS}/{call_id}"


def ago(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def soon(**delta) -> str:
    return (datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(days=1))).isoformat()


async def lead(db, telecaller=None, **over) -> Enquiry:
    values = {"division": "it", "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210",
              "subject": "Python", "message": "Please call me", "source": "website", "status": "assigned",
              "telecaller_user_id": telecaller.id if telecaller else None} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def log(client, lead_row, outcome="no_answer", **over):
    return await client.post(calls_url(lead_row.id), json={"duration_seconds": 0, "call_type": "outgoing", "outcome": outcome} | over)


async def stored(db, lead_row, caller, occurred_at, outcome="no_answer") -> LeadCall:
    """Written straight to the database -- the only way to have a call from an earlier day."""
    row = LeadCall(lead_id=lead_row.id, caller_user_id=caller.id, occurred_at=occurred_at, duration_seconds=30, call_type="outgoing",
                   outcome=outcome, remarks="old")
    db.add(row)
    await db.commit()
    return row


async def stage_of(db, lead_row) -> str:
    return await db.scalar(select(Enquiry.status).where(Enquiry.id == lead_row.id).execution_options(populate_existing=True))


async def events(db, lead_row) -> list[tuple[str, str, str | None]]:
    rows = await db.execute(select(LeadStageHistory.event, LeadStageHistory.to_stage, LeadStageHistory.reason)
                            .where(LeadStageHistory.lead_id == lead_row.id).order_by(LeadStageHistory.position))
    return [tuple(r) for r in rows.all()]


def field_error(response, field: str) -> str:
    assert response.status_code == 422, response.text
    return next(e["msg"] for e in response.json()["detail"] if field in e["loc"])


# --- create + pipeline effects ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_not_connected_call_moves_the_lead_to_first_call_pending_and_records_every_field(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    when = (datetime.now(UTC) - timedelta(minutes=10)).replace(microsecond=0)
    response = await log(client, row, "busy", occurred_at=when.isoformat(), duration_seconds=0, call_type="incoming", remarks=REMARKS)
    assert response.status_code == 201, response.text
    body = response.json()
    call = body["call"]
    assert call["outcome"] == "busy" and call["outcome_label"] == "Busy" and call["connected"] is False
    assert call["call_type"] == "incoming" and call["duration_seconds"] == 0 and call["remarks"] == REMARKS
    assert datetime.fromisoformat(call["occurred_at"]) == when and call["caller"]["id"] == str(tel.id) and call["can_change"] is True
    assert body["lead"]["status"] == "first_call_pending" and body["lead"]["status_label"] == "First Call Pending"
    assert body["follow_up_id"] is None
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "lead_call", AuditLog.entity_id == call["id"]))).all()
    assert actions == ["lead_call.create"]


@pytest.mark.asyncio
async def test_no_answer_twice_then_interested_fires_each_first_call_event_once(client, db_session):
    """Backlog positive scenario + AC1: the first-call stages move once; Connected - Interested then moves on to Interested."""
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await log(client, row)).status_code == 201
    assert (await log(client, row)).status_code == 201
    response = await log(client, row, "interested", duration_seconds=240)
    assert response.json()["lead"]["status"] == "interested"
    assert [(e, s) for e, s, _ in await events(db_session, row)] == [
        ("call_unconnected", "first_call_pending"), ("call_connected", "contacted"), ("manual", "interested")]


@pytest.mark.asyncio
async def test_a_connected_call_never_moves_a_lead_backwards(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="follow_up")
    await as_user(client, tel)
    for outcome in ("interested", "need_information", "no_answer"):
        response = await log(client, row, outcome)
        assert response.status_code == 201 and response.json()["lead"]["status"] == "follow_up"
    assert await events(db_session, row) == []


@pytest.mark.asyncio
async def test_appointment_fixed_without_a_booking_leaves_the_lead_contacted(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="first_call_pending")
    await as_user(client, tel)
    response = await log(client, row, "appointment_fixed", duration_seconds=300)
    assert response.json()["lead"]["status"] == "contacted"


@pytest.mark.asyncio
@pytest.mark.parametrize(("outcome", "stage", "reason"), [
    ("not_interested", "not_interested", "Not Interested"), ("wrong_number", "wrong_number", "Wrong Number"),
    ("already_joined", "lost", "Already Joined Elsewhere"), ("not_eligible", "not_eligible", "Not Eligible"),
])
async def test_closing_outcomes_close_the_lead_with_the_outcome_as_reason(client, db_session, outcome, stage, reason):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="contacted")
    open_fu = LeadFollowUp(lead_id=row.id, due_at=datetime.now(UTC) + timedelta(days=1), reason="fee_details", created_by_user_id=tel.id)
    db_session.add(open_fu)
    await db_session.commit()
    await as_user(client, tel)
    response = await log(client, row, outcome)
    assert response.status_code == 201, response.text
    assert response.json()["lead"]["status"] == stage
    assert await events(db_session, row) == [("manual", stage, reason)]
    fu = await db_session.scalar(select(LeadFollowUp).where(LeadFollowUp.id == open_fu.id).execution_options(populate_existing=True))
    assert fu.status == "cancelled"  # tel-011 F4


@pytest.mark.asyncio
async def test_duplicate_lead_needs_remarks_and_changes_no_stage(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    field_error(await log(client, row, "duplicate_lead"), "remarks")
    assert (await log(client, row, "duplicate_lead", remarks="   ")).status_code == 422
    response = await log(client, row, "duplicate_lead", remarks="Same person as LD-000123")
    assert response.status_code == 201 and response.json()["lead"]["status"] == "assigned"
    assert await events(db_session, row) == []


# --- next follow-up --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["follow_up_required", "call_back_requested"])
async def test_follow_up_outcomes_require_a_next_follow_up(client, db_session, outcome):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    field_error(await log(client, row, outcome), "next_follow_up")
    assert await db_session.scalar(select(LeadCall.id).where(LeadCall.lead_id == row.id)) is None


@pytest.mark.asyncio
async def test_next_follow_up_is_created_with_the_call(client, db_session):
    """AC3. The follow-up's own optional move to Follow-up applies after the call's effect."""
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    due = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    response = await log(client, row, "call_back_requested", next_follow_up={
        "due_at": due.isoformat(), "reason": "fee_details", "next_action": "Call back at 6", "move_to_follow_up": True})
    assert response.status_code == 201, response.text
    body = response.json()
    fu = await db_session.scalar(select(LeadFollowUp).where(LeadFollowUp.id == uuid.UUID(body["follow_up_id"])))
    assert fu.lead_id == row.id and fu.due_at == due and fu.reason == "fee_details" and fu.next_action == "Call back at 6"
    assert body["lead"]["status"] == "follow_up"
    assert [e for e, _, _ in await events(db_session, row)] == ["call_connected", "manual"]


@pytest.mark.asyncio
async def test_an_invalid_next_follow_up_logs_nothing(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    response = await log(client, row, "interested", next_follow_up={"due_at": ago(hours=1), "reason": "fee_details"})
    assert response.status_code == 422
    assert await db_session.scalar(select(LeadCall.id).where(LeadCall.lead_id == row.id)) is None
    assert await stage_of(db_session, row) == "assigned"


@pytest.mark.asyncio
async def test_a_closing_outcome_takes_no_next_follow_up(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    field_error(await log(client, row, "not_interested", next_follow_up={"due_at": soon(), "reason": "fee_details"}), "next_follow_up")


# --- validation ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_time_bounds(client, db_session):
    """AC2 / D6: up to 5 minutes ahead is saved as now; further ahead or more than 7 IST days back is refused on the field."""
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    field_error(await log(client, row, occurred_at=soon(minutes=30)), "occurred_at")
    field_error(await log(client, row, occurred_at=ago(days=8)), "occurred_at")
    assert (await log(client, row, occurred_at=ago(days=6))).status_code == 201
    ahead = await log(client, row, occurred_at=soon(minutes=2))
    assert ahead.status_code == 201 and datetime.fromisoformat(ahead.json()["call"]["occurred_at"]) <= datetime.now(UTC)
    default = await log(client, row)
    assert abs(datetime.fromisoformat(default.json()["call"]["occurred_at"]) - datetime.now(UTC)) < timedelta(minutes=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"outcome": "converted"}, {"call_type": "callback"}, {"duration_seconds": -1}, {"duration_seconds": 14401}, {"caller_user_id": str(uuid.uuid4())},
    {"remarks": "x" * 2001}, {"remarks": "bad\x00text"},
])
async def test_invalid_bodies_are_422(client, db_session, over):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await log(client, row, **over)).status_code == 422


# --- who -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_the_leads_telecaller_logs_a_call(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, other)
    assert (await log(client, row)).status_code == 404
    await as_user(client, manager)
    assert (await log(client, row)).status_code == 403
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await log(client, row)).status_code == 403
    assert await db_session.scalar(select(LeadCall.id).where(LeadCall.lead_id == row.id)) is None


@pytest.mark.asyncio
async def test_closed_and_handed_over_leads_refuse_a_call(client, db_session):
    """CL2 closed -> 409; backlog negative scenario: handed over -> 403."""
    _, tel, _ = await team(db_session)
    closed = await lead(db_session, tel, status="not_interested")
    counselor = await make_user(db_session, "counselor", "it")
    handed = await lead(db_session, tel, owner_id=counselor.id)
    await as_user(client, tel)
    assert (await log(client, closed)).status_code == 409
    assert (await log(client, handed)).status_code == 403


@pytest.mark.asyncio
async def test_daily_cap(client, db_session, monkeypatch):
    monkeypatch.setattr(lead_calls, "DAILY_CAP", 2)
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await log(client, row)).status_code == 201
    assert (await log(client, row)).status_code == 201
    assert (await log(client, row)).status_code == 409


@pytest.mark.asyncio
async def test_remarks_are_never_logged(client, db_session, caplog):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    with caplog.at_level(logging.INFO):
        assert (await log(client, row, "need_information", remarks=REMARKS)).status_code == 201
    assert "secret-remark-7f3" not in caplog.text
    audit = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_type == "lead_call"))).all()
    assert all("secret-remark-7f3" not in str(m) for m in audit)


# --- the lead's calls ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lead_calls_newest_first_with_can_change(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    old = await stored(db_session, row, tel, datetime.now(UTC) - timedelta(days=3))
    await as_user(client, tel)
    new = (await log(client, row, "interested")).json()["call"]
    page = (await client.get(calls_url(row.id))).json()
    assert [c["id"] for c in page["items"]] == [new["id"], str(old.id)] and page["total"] == 2
    assert [c["can_change"] for c in page["items"]] == [True, False]  # CL4: only today's
    await as_user(client, manager)
    assert [c["can_change"] for c in (await client.get(calls_url(row.id))).json()["items"]] == [False, False]
    await as_user(client, other)
    assert (await client.get(calls_url(row.id))).status_code == 404


# --- edit / delete ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_changes_details_but_never_the_outcome(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    call = (await log(client, row, "need_information")).json()["call"]
    response = await client.patch(call_url(call["id"]), json={"duration_seconds": 95, "remarks": "Wants the fee sheet", "call_type": "incoming"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duration_seconds"] == 95 and body["remarks"] == "Wants the fee sheet" and body["call_type"] == "incoming"
    assert (await client.patch(call_url(call["id"]), json={"outcome": "busy"})).status_code == 422
    field_error(await client.patch(call_url(call["id"]), json={"occurred_at": ago(days=1)}), "occurred_at")  # must stay in today
    metas = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == call["id"], AuditLog.action == "lead_call.update"))).all()
    assert metas == [{"fields": ["call_type", "duration_seconds", "remarks"]}]


@pytest.mark.asyncio
async def test_a_duplicate_call_keeps_its_remarks(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    call = (await log(client, row, "duplicate_lead", remarks="Same as LD-1")).json()["call"]
    field_error(await client.patch(call_url(call["id"]), json={"remarks": None}), "remarks")


@pytest.mark.asyncio
async def test_earlier_days_calls_are_locked(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    old = await stored(db_session, row, tel, datetime.now(UTC) - timedelta(days=2))
    await as_user(client, tel)
    assert (await client.patch(call_url(old.id), json={"remarks": "late"})).status_code == 409
    assert (await client.delete(call_url(old.id))).status_code == 409


@pytest.mark.asyncio
async def test_only_the_caller_edits_and_deletes(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    call = (await log(client, row)).json()["call"]
    await as_user(client, manager)
    assert (await client.patch(call_url(call["id"]), json={"remarks": "x"})).status_code == 403
    assert (await client.delete(call_url(call["id"]))).status_code == 403
    await as_user(client, other)  # out of scope reads as missing
    assert (await client.delete(call_url(call["id"]))).status_code == 404
    row.telecaller_user_id = other.id  # reassigned: the new telecaller sees the call but did not make it
    await db_session.commit()
    assert (await client.delete(call_url(call["id"]))).status_code == 403
    await as_user(client, tel)
    assert (await client.delete(call_url(call["id"]))).status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_the_call_and_reverses_nothing(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    call = (await log(client, row, "interested")).json()["call"]
    response = await client.delete(call_url(call["id"]))
    assert response.status_code == 204
    assert await db_session.scalar(select(LeadCall.id).where(LeadCall.id == uuid.UUID(call["id"]))) is None
    assert await stage_of(db_session, row) == "interested"  # CL4
    assert (await client.delete(call_url(call["id"]))).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == call["id"]).order_by(AuditLog.created_at))).all()
    assert actions == ["lead_call.create", "lead_call.delete"]


@pytest.mark.asyncio
async def test_handed_over_calls_are_read_only(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    call = (await log(client, row)).json()["call"]
    row.owner_id = (await make_user(db_session, "counselor", "it")).id
    await db_session.commit()
    assert (await client.get(calls_url(row.id))).json()["items"][0]["can_change"] is False
    assert (await client.patch(call_url(call["id"]), json={"remarks": "x"})).status_code == 403


# --- day counts (AC4) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_day_counts_per_outcome_are_exact_and_scoped(client, db_session):
    manager, tel, other = await team(db_session)
    a, b = await lead(db_session, tel), await lead(db_session, other)
    await stored(db_session, a, tel, datetime.now(UTC) - timedelta(days=2), "interested")  # another day
    await as_user(client, tel)
    for outcome in ("no_answer", "no_answer", "busy", "need_information"):
        assert (await log(client, a, outcome)).status_code == 201
    assert (await log(client, a, "wrong_number")).status_code == 201
    await as_user(client, other)
    assert (await log(client, b, "interested")).status_code == 201

    await as_user(client, tel)
    mine = (await client.get(f"{CALLS}/day-counts")).json()
    assert mine["total"] == 5 and mine["connected"] == 1 and mine["not_connected"] == 4
    assert mine["by_outcome"]["no_answer"] == 2 and mine["by_outcome"]["wrong_number"] == 1 and mine["by_outcome"]["interested"] == 0
    assert set(mine["by_outcome"]) == set(lead_calls.OUTCOMES)
    await as_user(client, manager)
    team_counts = (await client.get(f"{CALLS}/day-counts")).json()
    assert team_counts["total"] == 6 and team_counts["by_outcome"]["interested"] == 1
    await as_user(client, await make_tl_manager(db_session))
    assert (await client.get(f"{CALLS}/day-counts")).json()["total"] == 0
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get(f"{CALLS}/day-counts")).status_code == 403


@pytest.mark.asyncio
async def test_day_counts_for_another_day(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    when = datetime.now(UTC) - timedelta(days=2)
    await stored(db_session, row, tel, when, "interested")
    await as_user(client, tel)
    from app.services.bdm_appointments import today_ist
    body = (await client.get(f"{CALLS}/day-counts", params={"day": today_ist(when).isoformat()})).json()
    assert body["total"] == 1 and body["connected"] == 1 and body["day"] == today_ist(when).isoformat()


# --- follow-up card (D10) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_follow_ups_show_the_last_call(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="contacted")
    quiet = await lead(db_session, tel, status="contacted")
    await as_user(client, tel)
    await log(client, row, "busy", occurred_at=ago(hours=2))
    await log(client, row, "need_information", occurred_at=ago(hours=1))
    for target in (row, quiet):
        assert (await client.post(f"{LEADS}/{target.id}/follow-ups", json={"due_at": soon(), "reason": "fee_details"})).status_code == 201
    items = (await client.get(f"{LEADS}/{row.id}/follow-ups")).json()["items"]
    assert items[0]["lead"]["last_call"]["outcome"] == "need_information"
    assert (await client.get(f"{LEADS}/{quiet.id}/follow-ups")).json()["items"][0]["lead"]["last_call"] is None
