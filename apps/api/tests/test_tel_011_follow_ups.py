"""tel-011 -- follow-ups on a lead (spec §3; DEC-SCOPE-093 F1-F10): create, the lead's list, reschedule/edit, complete, cancel, the
day / overdue lists, the close cancel (F4) and My Leads' `follow_up` filter (F9). The shared test database is never truncated, so every
list assertion narrows to telecallers created by the test."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadFollowUp
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import IST
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user, stage_url

LEADS = "/api/v1/telecaller/leads"
FOLLOW_UPS = "/api/v1/telecaller/follow-ups"


def lead_url(lead_id) -> str:
    return f"{LEADS}/{lead_id}/follow-ups"


def fu_url(fu_id, action: str = "") -> str:
    return f"{FOLLOW_UPS}/{fu_id}{'/' + action if action else ''}"


def soon(**delta) -> str:
    return (datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(days=1))).isoformat()


async def lead(db, telecaller=None, **over) -> Enquiry:
    values = {"division": "it", "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210",
              "subject": "Python", "message": "Please call me", "source": "website", "status": "contacted",
              "telecaller_user_id": telecaller.id if telecaller else None} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def stored(db, lead_row, creator, due_at, **over) -> LeadFollowUp:
    """A row written straight to the database -- the only way to have one already due (the API refuses a past time)."""
    row = LeadFollowUp(lead_id=lead_row.id, due_at=due_at, reason="fee_details", created_by_user_id=creator.id, **over)
    db.add(row)
    await db.commit()
    return row


async def create(client, lead_row, **over):
    return await client.post(lead_url(lead_row.id), json={"due_at": soon(), "reason": "discuss_with_parents"} | over)


async def audit_actions(db, fu_id) -> list[str]:
    stmt = select(AuditLog.action).where(AuditLog.entity_type == "lead_follow_up", AuditLog.entity_id == str(fu_id)).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


# --- create ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_creates_a_follow_up_with_the_section_7_fields(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, priority="hot")
    await as_user(client, tel)
    due = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    response = await create(client, row, due_at=due.isoformat(), notes="Call after 4", next_action="Call today at 4:00 PM")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reason"] == "discuss_with_parents" and body["notes"] == "Call after 4" and body["next_action"] == "Call today at 4:00 PM"
    assert body["status"] == "open" and body["overdue"] is False and body["can_change"] is True
    assert datetime.fromisoformat(body["due_at"]) == due
    assert body["lead"]["id"] == str(row.id) and body["lead"]["priority"] == "hot" and body["lead"]["status"] == "contacted"
    assert body["created_by"]["id"] == str(tel.id)
    assert await audit_actions(db_session, body["id"]) == ["lead_follow_up.create"]
    await db_session.refresh(row)
    assert row.status == "contacted"  # F5: no stage move unless asked


@pytest.mark.asyncio
async def test_create_moves_the_stage_only_when_asked(client, db_session):
    _, tel, _ = await team(db_session)
    row, already = await lead(db_session, tel), await lead(db_session, tel, status="follow_up")
    await as_user(client, tel)
    response = await create(client, row, move_to_follow_up=True)
    assert response.status_code == 201, response.text
    assert response.json()["lead"]["status"] == "follow_up" and response.json()["lead"]["status_label"] == "Follow-up"
    assert (await create(client, already, move_to_follow_up=True)).status_code == 201  # already there: no move, no 422


@pytest.mark.asyncio
async def test_stage_move_past_the_counselor_is_refused_and_nothing_is_created(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="application_enrollment")
    await as_user(client, tel)
    response = await create(client, row, move_to_follow_up=True)
    assert response.status_code == 422, response.text
    assert await db_session.scalar(select(LeadFollowUp.id).where(LeadFollowUp.lead_id == row.id)) is None
    assert (await create(client, row)).status_code == 201  # without the move it is allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("due, message", [({"minutes": -1}, "future"), ({"days": 367}, "12 months")])
async def test_due_time_must_be_future_and_within_a_year(client, db_session, due, message):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    response = await create(client, row, due_at=soon(**due))
    assert response.status_code == 422 and message in response.text  # AC3


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [{"reason": "other"}, {"due_at": "2027-01-01T10:00:00"}, {"notes": "x" * 2001}, {"next_action": "x" * 201},
                                  {"status": "done"}])
async def test_invalid_bodies_are_422(client, db_session, over):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await create(client, row, **over)).status_code == 422


@pytest.mark.asyncio
async def test_scope_and_role_rules_on_create(client, db_session):
    manager, tel, other = await team(db_session)
    mine, theirs = await lead(db_session, tel), await lead(db_session, other)
    await as_user(client, tel)
    assert (await create(client, theirs)).status_code == 404  # another telecaller's lead reads as missing
    assert (await create(client, Enquiry(id=uuid.uuid4()))).status_code == 404
    await as_user(client, manager)
    response = await create(client, mine)
    assert response.status_code == 403 and "telecaller" in response.text  # F2: managers read only
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await create(client, mine)).status_code == 403
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await create(client, mine)).status_code == 403
    client.cookies.clear()
    assert (await create(client, mine)).status_code == 401


@pytest.mark.asyncio
async def test_closed_and_handed_over_leads_refuse_new_follow_ups(client, db_session):
    _, tel, _ = await team(db_session)
    closed = await lead(db_session, tel, status="not_interested")
    counselor = await make_user(db_session, "counselor", "it")
    handed = await lead(db_session, tel, owner_id=counselor.id)
    await as_user(client, tel)
    response = await create(client, closed)
    assert response.status_code == 409 and "closed" in response.text  # F4
    assert (await create(client, handed)).status_code == 403  # tel-008 D1


@pytest.mark.asyncio
async def test_at_most_twenty_open_follow_ups_per_lead(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    future = datetime.now(UTC) + timedelta(days=2)
    for _ in range(20):
        db_session.add(LeadFollowUp(lead_id=row.id, due_at=future, reason="fee_details", created_by_user_id=tel.id))
    await db_session.commit()
    await as_user(client, tel)
    response = await create(client, row)
    assert response.status_code == 409 and "20" in response.text  # F10


# --- the lead's list ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lead_list_shows_open_first_by_due_then_closed_newest_first(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    now = datetime.now(UTC)
    late = await stored(db_session, row, tel, now + timedelta(days=3))
    early = await stored(db_session, row, tel, now + timedelta(days=1))
    done = await stored(db_session, row, tel, now - timedelta(days=2), status="done", completed_at=now - timedelta(days=1), completed_by_user_id=tel.id)
    gone = await stored(db_session, row, tel, now - timedelta(days=3), status="cancelled", cancelled_at=now, cancel_reason="No longer needed")
    await as_user(client, tel)
    body = (await client.get(lead_url(row.id))).json()
    assert [i["id"] for i in body["items"]] == [str(early.id), str(late.id), str(gone.id), str(done.id)]
    assert body["total"] == 4 and body["items"][0]["can_change"] is True and body["items"][2]["can_change"] is False
    await as_user(client, manager)  # F2: the manager reads, never changes
    items = (await client.get(lead_url(row.id))).json()["items"]
    assert len(items) == 4 and not any(i["can_change"] for i in items)
    await as_user(client, other)
    assert (await client.get(lead_url(row.id))).status_code == 404


# --- reschedule / edit, complete, cancel ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_writes_only_changes_and_audits_field_names(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    fu = (await create(client, row, notes="first")).json()
    new_due = (datetime.now(UTC) + timedelta(days=5)).replace(microsecond=0)
    response = await client.patch(fu_url(fu["id"]), json={"due_at": new_due.isoformat(), "reason": "fee_details", "notes": "first"})
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["due_at"]) == new_due and response.json()["reason"] == "fee_details"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == fu["id"], AuditLog.action == "lead_follow_up.update"))
    assert audit.metadata_json == {"fields": ["due_at", "reason"]}
    assert (await client.patch(fu_url(fu["id"]), json={"notes": "first"})).status_code == 200  # unchanged: no audit row
    assert (await audit_actions(db_session, fu["id"])).count("lead_follow_up.update") == 1


@pytest.mark.asyncio
async def test_reschedule_rules(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    past = await stored(db_session, row, tel, datetime.now(UTC) - timedelta(hours=1))
    await as_user(client, tel)
    response = await client.patch(fu_url(past.id), json={"due_at": soon(minutes=-5)})
    assert response.status_code == 422 and "future" in response.text
    assert (await client.patch(fu_url(past.id), json={"notes": "still overdue"})).status_code == 200  # an overdue one can be edited
    assert (await client.patch(fu_url(past.id), json={"due_at": None})).status_code == 422
    assert (await client.patch(fu_url(past.id), json={"lead_id": str(row.id)})).status_code == 422


@pytest.mark.asyncio
async def test_complete_and_cancel_close_it_once(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    one, two = (await create(client, row)).json(), (await create(client, row)).json()
    done = await client.post(fu_url(one["id"], "complete"))
    assert done.status_code == 200 and done.json()["status"] == "done" and done.json()["completed_by"]["id"] == str(tel.id)
    assert done.json()["can_change"] is False
    again = await client.post(fu_url(one["id"], "complete"))
    assert again.status_code == 409 and "already done" in again.text
    assert (await client.patch(fu_url(one["id"]), json={"notes": "x"})).status_code == 409
    assert (await client.post(fu_url(two["id"], "cancel"), json={})).status_code == 422  # reason required
    cancelled = await client.post(fu_url(two["id"], "cancel"), json={"reason": "Student already joined"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled" and cancelled.json()["cancel_reason"] == "Student already joined"
    assert (await client.post(fu_url(two["id"], "complete"))).status_code == 409
    assert await audit_actions(db_session, one["id"]) == ["lead_follow_up.create", "lead_follow_up.complete"]
    assert await audit_actions(db_session, two["id"]) == ["lead_follow_up.create", "lead_follow_up.cancel"]


@pytest.mark.asyncio
async def test_someone_elses_follow_up_is_404_and_a_manager_403(client, db_session):
    manager, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    fu = (await create(client, row)).json()
    await as_user(client, other)
    for response in (await client.post(fu_url(fu["id"], "complete")), await client.patch(fu_url(fu["id"]), json={"notes": "x"}),
                     await client.post(fu_url(fu["id"], "cancel"), json={"reason": "x"})):
        assert response.status_code == 404
    assert (await client.post(fu_url(uuid.uuid4(), "complete"))).status_code == 404
    await as_user(client, manager)
    assert (await client.post(fu_url(fu["id"], "complete"))).status_code == 403


@pytest.mark.asyncio
async def test_follow_ups_move_with_a_reassigned_lead(client, db_session):
    _, tel, other = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    fu = (await create(client, row)).json()
    row.telecaller_user_id = other.id  # what tel-007's assign writes
    await db_session.commit()
    assert (await client.post(fu_url(fu["id"], "complete"))).status_code == 404  # F3: the old telecaller lost it
    await as_user(client, other)
    response = await client.post(fu_url(fu["id"], "complete"))
    assert response.status_code == 200 and response.json()["completed_by"]["id"] == str(other.id)
    assert response.json()["created_by"]["id"] == str(tel.id)


@pytest.mark.asyncio
async def test_handed_over_lead_follow_ups_are_read_only_for_the_telecaller(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    fu = await stored(db_session, row, tel, datetime.now(UTC) + timedelta(days=1))
    row.owner_id = (await make_user(db_session, "counselor", "it")).id
    await db_session.commit()
    await as_user(client, tel)
    items = (await client.get(lead_url(row.id))).json()["items"]
    assert items[0]["can_change"] is False
    assert (await client.post(fu_url(fu.id, "complete"))).status_code == 403


# --- the day / overdue lists ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_day_list_is_exactly_the_open_follow_ups_of_that_ist_day_ordered_by_time(client, db_session):
    _, tel, other = await team(db_session)
    row, row2 = await lead(db_session, tel, priority="hot"), await lead(db_session, tel)
    day = datetime.now(IST).date() + timedelta(days=2)
    start, end = day_range(day)
    last = await stored(db_session, row, tel, end - timedelta(seconds=1), next_action="Call at night")
    first = await stored(db_session, row2, tel, start)
    middle = await stored(db_session, row, tel, start + timedelta(hours=16))
    await stored(db_session, row, tel, end)  # the next day
    await stored(db_session, row, tel, start - timedelta(seconds=1))  # the day before
    await stored(db_session, row, tel, start + timedelta(hours=1), status="done", completed_at=start, completed_by_user_id=tel.id)
    await stored(db_session, await lead(db_session, other), other, start + timedelta(hours=2))  # another telecaller's
    await as_user(client, tel)
    response = await client.get(FOLLOW_UPS, params={"day": day.isoformat()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["id"] for i in body["items"]] == [str(first.id), str(middle.id), str(last.id)]  # AC1
    assert body["day"] == day.isoformat() and body["counts"]["day"] == 3 and body["total"] == 3
    card = body["items"][2]
    assert card["lead"]["name"] == row.name and card["lead"]["priority"] == "hot" and card["next_action"] == "Call at night"
    assert card["overdue"] is False and "product" in card["lead"]


@pytest.mark.asyncio
async def test_today_marks_overdue_and_the_overdue_view_lists_every_past_due_one(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    now = datetime.now(UTC)
    past = await stored(db_session, row, tel, now - timedelta(minutes=2))
    older = await stored(db_session, row, tel, now - timedelta(days=3))
    await stored(db_session, row, tel, now + timedelta(days=1))
    await as_user(client, tel)
    today = (await client.get(FOLLOW_UPS)).json()  # default: today (IST)
    assert today["day"] == datetime.now(IST).date().isoformat()
    marked = {i["id"]: i["overdue"] for i in today["items"]}
    if str(past.id) in marked:  # 2 minutes ago is today unless the test runs in the first 2 minutes after IST midnight
        assert marked[str(past.id)] is True  # AC2
    overdue = (await client.get(FOLLOW_UPS, params={"view": "overdue"})).json()
    assert [i["id"] for i in overdue["items"]] == [str(older.id), str(past.id)] and all(i["overdue"] for i in overdue["items"])
    assert overdue["counts"]["overdue"] == 2 == today["counts"]["overdue"]
    await as_user(client, manager)  # F2: the manager reads its reports' lists
    managed = (await client.get(FOLLOW_UPS, params={"view": "overdue"})).json()
    assert {str(past.id), str(older.id)} <= {i["id"] for i in managed["items"]}
    assert all(not i["can_change"] for i in managed["items"]) and managed["items"][0]["lead"]["telecaller"] is not None


@pytest.mark.asyncio
async def test_list_role_and_parameter_rules(client, db_session):
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get(FOLLOW_UPS)).status_code == 403
    _, tel, _ = await team(db_session)
    await as_user(client, tel)
    assert (await client.get(FOLLOW_UPS, params={"view": "soon"})).status_code == 422
    assert (await client.get(FOLLOW_UPS, params={"day": "06-10-2026"})).status_code == 422
    assert (await client.get(FOLLOW_UPS, params={"limit": 101})).status_code == 422


# --- F4: closing cancels; F9: My Leads filter -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_closing_a_lead_cancels_its_open_follow_ups_only(client, db_session):
    _, tel, _ = await team(db_session)
    row, other_lead = await lead(db_session, tel), await lead(db_session, tel)
    now = datetime.now(UTC)
    open_one = await stored(db_session, row, tel, now + timedelta(days=1))
    done = await stored(db_session, row, tel, now - timedelta(days=1), status="done", completed_at=now, completed_by_user_id=tel.id)
    untouched = await stored(db_session, other_lead, tel, now + timedelta(days=1))
    await as_user(client, tel)
    response = await client.post(stage_url(row.id), json={"to_stage": "not_interested", "reason": "Joined elsewhere"})
    assert response.status_code == 200, response.text
    for fu in (open_one, done, untouched):
        await db_session.refresh(fu)
    assert (open_one.status, open_one.cancel_reason) == ("cancelled", "Lead closed") and open_one.cancelled_at is not None
    assert done.status == "done" and untouched.status == "open"


@pytest.mark.asyncio
async def test_my_leads_follow_up_filter(client, db_session):
    _, tel, _ = await team(db_session)
    due_today, overdue, later, none = [await lead(db_session, tel) for _ in range(4)]
    now = datetime.now(UTC)
    _, end = day_range(datetime.now(IST).date())
    await stored(db_session, due_today, tel, end - timedelta(seconds=1))
    await stored(db_session, overdue, tel, now - timedelta(days=2))
    await stored(db_session, later, tel, end + timedelta(days=1))
    await stored(db_session, none, tel, end - timedelta(seconds=2), status="cancelled", cancelled_at=now, cancel_reason="x")
    await as_user(client, tel)

    async def ids(value: str) -> set[str]:
        response = await client.get(LEADS, params={"follow_up": value})
        assert response.status_code == 200, response.text
        return {i["id"] for i in response.json()["items"]}

    assert await ids("today") == {str(due_today.id)}
    assert await ids("overdue") == {str(overdue.id)}
    assert (await client.get(LEADS, params={"follow_up": "soon"})).status_code == 422
