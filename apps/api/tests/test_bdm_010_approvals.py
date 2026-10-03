"""bdm-010 -- decisions, fallback approver, queue and the manager's view (spec §5.2 decide; AC2–AC4, AC7; Review Focus 1–4)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmProfile, Notification
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm010_helpers import APPROVALS, TEAM_TRIPS, TRIPS, act, bdm_pair, make_trip, sign_in


async def _submitted(client, db, **over):
    manager, bdm = await bdm_pair(client, db)
    trip = await make_trip(client, **over)
    assert (await act(client, trip["id"], "submit")).status_code == 200
    return manager, bdm, trip


def _decide(client, trip_id, verb, **kwargs):
    return client.post(f"{TEAM_TRIPS}/{trip_id}/{verb}", **kwargs)


@pytest.mark.asyncio
async def test_manager_approves_audited_and_bdm_notified(client, db_session):
    manager, bdm, trip = await _submitted(client, db_session)
    await sign_in(client, manager)
    queue = (await client.get(APPROVALS)).json()
    assert [t["id"] for t in queue["items"]] == [trip["id"]]
    detail = (await client.get(f"{TEAM_TRIPS}/{trip['id']}")).json()
    assert detail["can_decide"] and not detail["can_edit"]
    approved = (await _decide(client, trip["id"], "approve")).json()
    assert approved["approval_status"] == "approved" and approved["decided_by"]["id"] == str(manager.id)
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == trip["id"], AuditLog.action == "bdm.trip_approve"))
    assert row.outcome == "approved" and row.user_id == manager.id
    note = await db_session.scalar(select(Notification).where(Notification.user_id == bdm.id))
    assert note.action_url == f"/bdm/travel/{trip['id']}" and "approved" in note.title.lower()
    assert (await client.get(APPROVALS)).json()["total"] == 0


@pytest.mark.asyncio
async def test_reject_needs_a_reason_and_records_it(client, db_session):
    manager, _, trip = await _submitted(client, db_session)
    await sign_in(client, manager)
    assert (await _decide(client, trip["id"], "reject", json={"reason": ""})).status_code == 422
    rejected = (await _decide(client, trip["id"], "reject", json={"reason": "Combine with next week's trip"})).json()
    assert (rejected["approval_status"], rejected["rejection_reason"]) == ("rejected", "Combine with next week's trip")
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == trip["id"], AuditLog.action == "bdm.trip_reject"))
    assert row.outcome == "rejected" and row.metadata_json["reason"] == "Combine with next week's trip"


@pytest.mark.asyncio
async def test_resubmit_after_reject_clears_the_decision(client, db_session):
    manager, bdm, trip = await _submitted(client, db_session)
    await sign_in(client, manager)
    await _decide(client, trip["id"], "reject", json={"reason": "Too costly"})
    await sign_in(client, bdm)
    edited = await client.patch(f"{TRIPS}/{trip['id']}", json={"estimated_cost": "1500"})
    assert edited.status_code == 200
    again = (await act(client, trip["id"], "submit")).json()
    assert (again["approval_status"], again["rejection_reason"], again["decided_by"], again["decided_at"]) == ("submitted", None, None, None)


@pytest.mark.asyncio
async def test_another_teams_manager_gets_404_and_a_bdm_gets_403(client, db_session):
    _, bdm, trip = await _submitted(client, db_session)
    assert (await _decide(client, trip["id"], "approve")).status_code == 403  # the BDM (role bdm) on a manager route
    await sign_in(client, await make_manager(db_session))
    assert (await _decide(client, trip["id"], "approve")).status_code == 404
    assert (await client.get(f"{TEAM_TRIPS}/{trip['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_super_admin_decides_only_when_the_manager_is_inactive(client, db_session):
    manager, _, trip = await _submitted(client, db_session)
    admin = await make_user(db_session, "super_admin", "global")
    await sign_in(client, admin)
    refused = await _decide(client, trip["id"], "approve")
    assert (refused.status_code, refused.json()["detail"]) == (403, "The reporting manager is active and decides this trip")
    assert trip["id"] not in [t["id"] for t in (await client.get(APPROVALS, params={"limit": 100})).json()["items"]]
    manager.active = False
    await db_session.commit()
    assert trip["id"] in [t["id"] for t in (await client.get(APPROVALS, params={"limit": 100})).json()["items"]]
    assert (await _decide(client, trip["id"], "approve")).json()["approval_status"] == "approved"


@pytest.mark.asyncio
async def test_reassigned_bdm_moves_pending_trip_to_new_manager(client, db_session):
    old, bdm, trip = await _submitted(client, db_session)
    new = await make_manager(db_session)
    profile = await db_session.scalar(select(BdmProfile).where(BdmProfile.user_id == bdm.id))
    profile.reporting_manager_user_id = new.id
    await db_session.commit()
    await sign_in(client, old)
    assert (await _decide(client, trip["id"], "approve")).status_code == 404
    await sign_in(client, new)
    assert (await _decide(client, trip["id"], "approve")).status_code == 200


@pytest.mark.asyncio
async def test_cancelled_while_submitted_leaves_the_queue_and_cannot_be_decided(client, db_session):
    manager, _, trip = await _submitted(client, db_session)
    assert (await act(client, trip["id"], "cancel")).json()["travel_status"] == "cancelled"
    await sign_in(client, manager)
    assert (await client.get(APPROVALS)).json()["total"] == 0
    assert (await _decide(client, trip["id"], "approve")).status_code == 409


@pytest.mark.asyncio
async def test_approved_trip_fields_locked_but_remarks_editable_after_completion(client, db_session):
    today = india_today()
    manager, bdm, trip = await _submitted(client, db_session, travel_date=str(today), return_date=str(today))
    await sign_in(client, manager)
    await _decide(client, trip["id"], "approve")
    await sign_in(client, bdm)
    locked = await client.patch(f"{TRIPS}/{trip['id']}", json={"travel_date": str(today + timedelta(days=1))})
    assert (locked.status_code, locked.json()["detail"]) == (422, "An approved trip's details can't be changed")
    assert (await act(client, trip["id"], "complete")).json()["travel_status"] == "completed"
    remarks = await client.patch(f"{TRIPS}/{trip['id']}", json={"remarks": "Two MoUs signed"})
    assert remarks.status_code == 200 and remarks.json()["remarks"] == "Two MoUs signed"
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == trip["id"], AuditLog.action == "bdm.trip_update"))
    assert row.metadata_json["after"] == {"remarks": "Two MoUs signed"}


@pytest.mark.asyncio
async def test_start_waits_for_the_travel_date(client, db_session):
    manager, bdm, trip = await _submitted(client, db_session)  # travel date is 7 days ahead
    await sign_in(client, manager)
    await _decide(client, trip["id"], "approve")
    await sign_in(client, bdm)
    early = await act(client, trip["id"], "start")
    assert early.status_code == 409 and "can be started from that day" in early.json()["detail"]


@pytest.mark.asyncio
async def test_team_list_scope_and_filter(client, db_session):
    manager, bdm, trip = await _submitted(client, db_session)
    await sign_in(client, manager)
    page = (await client.get(TEAM_TRIPS, params={"bdm_user_id": str(bdm.id)})).json()
    assert [t["id"] for t in page["items"]] == [trip["id"]] and page["items"][0]["bdm"]["full_name"] == bdm.full_name
    other = await make_manager(db_session)
    await sign_in(client, other)
    assert (await client.get(TEAM_TRIPS, params={"bdm_user_id": str(bdm.id)})).json()["total"] == 0
