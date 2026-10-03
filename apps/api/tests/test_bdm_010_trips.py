"""bdm-010 -- BDM trip routes (spec §5.3; AC1, AC2, AC6, AC7, AC8)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, NotificationDelivery, User
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import make_user
from tests.bdm010_helpers import TRIPS, act, bdm_pair, make_trip, sign_in, trip_body


async def _audit(db, trip_id: str) -> list[str]:
    rows = await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == trip_id).order_by(AuditLog.created_at))
    return list(rows)


@pytest.mark.asyncio
async def test_create_returns_the_full_trip_with_a_trv_code(client, db_session):
    _, bdm = await bdm_pair(client, db_session)
    trip = await make_trip(client, mode="flight", accommodation_required=True, remarks="Hotel near campus")
    assert trip["code"].startswith("TRV-") and len(trip["code"]) == 10
    assert (trip["approval_status"], trip["travel_status"], trip["currency"]) == ("draft", "planned", "INR")
    assert (trip["estimated_cost"], trip["actual_cost"], trip["mode"]) == ("2500.00", "0.00", "flight")
    assert trip["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    assert trip["can_edit"] and trip["can_submit"] and not trip["can_add_expense"] and trip["expenses"] == []
    assert await _audit(db_session, trip["id"]) == ["bdm.trip_create"]


@pytest.mark.asyncio
async def test_codes_increase(client, db_session):
    await bdm_pair(client, db_session)
    first, second = await make_trip(client), await make_trip(client)
    assert int(second["code"][4:]) > int(first["code"][4:])


@pytest.mark.asyncio
async def test_create_applies_the_date_guards(client, db_session):
    await bdm_pair(client, db_session)
    today = india_today()
    bad = await client.post(TRIPS, json=trip_body(travel_date=str(today - timedelta(days=31)), return_date=str(today)))
    assert (bad.status_code, bad.json()["detail"]) == (422, "Travel date can be at most 30 days in the past")
    long = await client.post(TRIPS, json=trip_body(travel_date=str(today), return_date=str(today + timedelta(days=31))))
    assert long.json()["detail"] == "A trip can last at most 31 days"


@pytest.mark.asyncio
async def test_list_is_mine_only_newest_first_and_filterable(client, db_session):
    manager, _ = await bdm_pair(client, db_session)
    today = india_today()
    early = await make_trip(client, travel_date=str(today + timedelta(days=2)), return_date=str(today + timedelta(days=2)))
    late = await make_trip(client, travel_date=str(today + timedelta(days=9)), return_date=str(today + timedelta(days=9)))
    await act(client, early["id"], "submit")
    page = (await client.get(TRIPS)).json()
    assert [t["id"] for t in page["items"]] == [late["id"], early["id"]] and page["total"] == 2
    submitted = (await client.get(TRIPS, params={"approval_status": "submitted"})).json()
    assert [t["id"] for t in submitted["items"]] == [early["id"]]
    assert (await client.get(TRIPS, params={"approval_status": "nope"})).status_code == 422
    await bdm_pair(client, db_session, manager=manager)  # another BDM of the same manager
    assert (await client.get(TRIPS)).json()["total"] == 0


@pytest.mark.asyncio
async def test_submit_notifies_the_active_manager_in_app_only(client, db_session):
    manager, _ = await bdm_pair(client, db_session)
    trip = await make_trip(client)
    response = await act(client, trip["id"], "submit")
    assert response.status_code == 200 and response.json()["approval_status"] == "submitted"
    note = (await db_session.scalars(select(Notification).where(Notification.user_id == manager.id))).one()
    assert trip["code"] in note.title + note.body and note.action_url == "/bdm/manager/approvals"
    assert (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id))).all() == []


@pytest.mark.asyncio
async def test_submit_with_an_inactive_manager_notifies_every_active_super_admin(client, db_session):
    manager, bdm = await bdm_pair(client, db_session)
    trip = await make_trip(client)
    manager.active = False
    await db_session.commit()
    await act(client, trip["id"], "submit")
    admins = (await db_session.scalars(select(User.id).where(User.role == "super_admin", User.active.is_(True)))).all()
    notified = (await db_session.scalars(
        select(Notification.user_id).where(Notification.action_url == "/admin/bdm-travel-approvals", Notification.body.contains(trip["code"]))
    )).all()
    assert set(notified) == set(admins) and manager.id not in notified


@pytest.mark.asyncio
async def test_withdraw_then_edit_then_resubmit(client, db_session):
    await bdm_pair(client, db_session)
    trip = await make_trip(client)
    await act(client, trip["id"], "submit")
    locked = await client.patch(f"{TRIPS}/{trip['id']}", json={"to_place": "Guntur"})
    assert (locked.status_code, locked.json()["detail"]) == (409, "Withdraw the trip to edit it")
    assert (await act(client, trip["id"], "withdraw")).json()["approval_status"] == "draft"
    edited = await client.patch(f"{TRIPS}/{trip['id']}", json={"to_place": "Guntur"})
    assert edited.status_code == 200 and edited.json()["to_place"] == "Guntur"
    assert (await act(client, trip["id"], "submit")).json()["approval_status"] == "submitted"
    assert await _audit(db_session, trip["id"]) == ["bdm.trip_create", "bdm.trip_submit", "bdm.trip_withdraw", "bdm.trip_update", "bdm.trip_submit"]


@pytest.mark.asyncio
async def test_disallowed_transition_is_409_and_changes_nothing(client, db_session):
    await bdm_pair(client, db_session)
    trip = await make_trip(client)
    response = await act(client, trip["id"], "start")
    assert (response.status_code, response.json()["detail"]) == (409, "This trip is draft and can't be started")
    assert (await client.get(f"{TRIPS}/{trip['id']}")).json()["travel_status"] == "planned"


@pytest.mark.asyncio
async def test_patch_rules(client, db_session):
    await bdm_pair(client, db_session)
    trip = await make_trip(client)
    assert (await client.patch(f"{TRIPS}/{trip['id']}", json={})).json()["detail"] == "Nothing to change"
    bad = await client.patch(f"{TRIPS}/{trip['id']}", json={"return_date": str(india_today())})
    assert bad.json()["detail"] == "Return date must be on or after the travel date"
    assert (await client.patch(f"{TRIPS}/{trip['id']}", json={"approval_status": "approved"})).status_code == 422
    later = str(india_today() + timedelta(days=10))
    moved = await client.patch(f"{TRIPS}/{trip['id']}", json={"travel_date": later, "return_date": later, "estimated_cost": "99.5"})
    assert moved.status_code == 200 and (moved.json()["travel_date"], moved.json()["estimated_cost"]) == (later, "99.50")
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == trip["id"], AuditLog.action == "bdm.trip_update"))
    assert row.metadata_json["after"]["travel_date"] == later and row.metadata_json["after"]["estimated_cost"] == "99.5"


@pytest.mark.asyncio
async def test_cancel_a_draft(client, db_session):
    await bdm_pair(client, db_session)
    trip = await make_trip(client)
    cancelled = (await act(client, trip["id"], "cancel")).json()
    assert (cancelled["travel_status"], cancelled["cancelled_at"] is not None, cancelled["can_edit"]) == ("cancelled", True, False)
    again = await act(client, trip["id"], "cancel")
    assert (again.status_code, again.json()["detail"]) == (409, "This trip is cancelled and can't be cancelled")


@pytest.mark.asyncio
async def test_a_non_bdm_is_refused(client, db_session):
    await sign_in(client, await make_user(db_session, "bdm_manager", "global"))
    assert (await client.get(TRIPS)).status_code == 403
    assert (await client.post(TRIPS, json=trip_body())).status_code == 403


@pytest.mark.asyncio
async def test_unknown_trip_is_404(client, db_session):
    await bdm_pair(client, db_session)
    response = await client.get(f"{TRIPS}/{uuid.uuid4()}")
    assert (response.status_code, response.json()["detail"]) == (404, "Trip not found")
