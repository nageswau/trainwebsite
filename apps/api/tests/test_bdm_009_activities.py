"""bdm-009 -- log, list my day, edit, delete (spec §5.3-§5.5; AC1, AC2, AC4, AC7, AC8)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmActivity
from app.services import bdm_activities as svc
from app.services.bdm_travel import india_today
from tests.bdm009_helpers import ACTIVITIES, activity_body, add_activity, bdm_with_org

CHANNELS = [("call", "outbound"), ("whatsapp", "inbound"), ("email", "outbound"), ("visit", None), ("meeting", None), ("other", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("channel,direction", CHANNELS)
async def test_each_channel_is_loggable_against_an_organization(client, db_session, channel, direction):
    _, bdm, org = await bdm_with_org(client, db_session)
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], channel=channel, direction=direction, note="Discussed intake"))
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["channel"], data["direction"], data["note"]) == (channel, direction, "Discussed intake")
    assert data["organization"]["id"] == org["id"]
    assert data["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    assert data["permissions"] == {"can_change": True}


@pytest.mark.asyncio
async def test_a_time_slightly_ahead_is_saved_as_now(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    ahead = datetime.now(UTC) + timedelta(minutes=2)
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=ahead.isoformat()))
    assert response.status_code == 201, response.text
    saved = datetime.fromisoformat(response.json()["occurred_at"].replace("Z", "+00:00"))
    assert saved < ahead  # clamped to the server's now (V9)


@pytest.mark.asyncio
async def test_the_daily_cap_refuses_the_next_log(client, db_session, monkeypatch):
    _, _, org = await bdm_with_org(client, db_session)
    monkeypatch.setattr(svc, "DAILY_CAP", 1)
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 201
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (409, svc.CAP_REACHED)


@pytest.mark.asyncio
async def test_future_and_too_old_occurred_at_are_422(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    future = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=future))
    assert (response.status_code, response.json()["detail"]) == (422, svc.FUTURE)
    old = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=old))
    assert (response.status_code, response.json()["detail"]) == (422, svc.TOO_OLD)
    six_days = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=six_days))).status_code == 201


@pytest.mark.asyncio
async def test_my_day_lists_newest_first_with_exact_counts_independent_of_the_page(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    start, _ = svc.day_range(india_today())
    base = max(datetime.now(UTC) - timedelta(minutes=30), start + timedelta(minutes=1))  # stay inside today's IST day
    for i, (channel, direction) in enumerate([("call", "outbound"), ("call", "outbound"), ("call", "inbound"), ("visit", None)]):
        body = activity_body(org["id"], channel=channel, direction=direction, occurred_at=(base + timedelta(minutes=i)).isoformat())
        assert (await client.post(ACTIVITIES, json=body)).status_code == 201
    data = (await client.get(ACTIVITIES, params={"limit": 2})).json()
    assert len(data["items"]) == 2 and data["total"] == 4
    assert data["items"][0]["channel"] == "visit"  # newest first
    assert data["counts"]["by_channel"]["call"] == 3
    assert data["counts"]["calls_made"] == 2
    assert data["counts"]["organizations_contacted"] == 1
    assert data["counts"]["day"] == str(india_today())


@pytest.mark.asyncio
async def test_my_day_of_a_future_date_is_422_and_a_past_date_shows_that_day(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    tomorrow = india_today() + timedelta(days=1)
    assert (await client.get(ACTIVITIES, params={"date": str(tomorrow)})).status_code == 422
    past = india_today() - timedelta(days=20)
    start, _ = svc.day_range(past)
    await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(hours=2))
    data = (await client.get(ACTIVITIES, params={"date": str(past)})).json()
    assert data["total"] == 1 and data["items"][0]["permissions"]["can_change"] is False


@pytest.mark.asyncio
async def test_patch_today_changes_fields_and_audits_names_only(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao"}, {"name": "Ms Iyer"}])
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="secret note"))).json()
    contact = org["contacts"][1]
    body = {"direction": "inbound", "contact_id": contact["id"], "note": "call back Tuesday"}
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["direction"], data["contact_name"], data["note"]) == ("inbound", "Ms Iyer", "call back Tuesday")
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in rows] == ["bdm_activity.created", "bdm_activity.updated"]
    assert sorted(rows[1].metadata_json["fields"]) == ["contact_id", "direction", "note"]
    flat = str([r.metadata_json for r in rows])
    for secret in ("secret note", "call back Tuesday", "Ms Iyer"):
        assert secret not in flat


@pytest.mark.asyncio
async def test_resending_the_same_contact_keeps_the_snapshot(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao"}])
    rao = org["contacts"][0]["id"]
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=rao))).json()
    renamed = await client.patch(f"/api/v1/bdm/organizations/{org['id']}/contacts/{rao}", json={"name": "Dr K Rao"})  # bdm-002 route
    assert renamed.status_code == 200, renamed.text
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"contact_id": rao, "note": "follow-up"})
    assert response.status_code == 200
    assert response.json()["contact_name"] == "Dr Rao"  # the name at save, not the renamed one
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "bdm_activity.updated"))
    assert row.metadata_json["fields"] == ["note"]


@pytest.mark.asyncio
async def test_abuse_cases_server_owned_fields_and_markup(client, db_session):
    """AC13: mass assignment is refused; markup is stored and returned as plain text (React renders it as text)."""
    _, bdm, org = await bdm_with_org(client, db_session)
    for field, value in (("bdm_user_id", str(uuid.uuid4())), ("contact_name", "Forged"), ("id", str(uuid.uuid4()))):
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"], **{field: value}))).status_code == 422
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="<script>alert(1)</script>"))).json()
    assert created["note"] == "<script>alert(1)</script>"
    assert created["bdm"]["id"] == str(bdm.id)
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"organization_id": str(uuid.uuid4())})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_channel_change_needs_direction_cleared(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"channel": "visit"})
    assert (response.status_code, response.json()["detail"]) == (422, "Direction applies only to calls, WhatsApp and email")
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"channel": "visit", "direction": None})
    assert response.status_code == 200 and response.json()["direction"] is None


@pytest.mark.asyncio
async def test_patch_cannot_move_off_today_and_past_activities_are_locked(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    yesterday = (datetime.now(UTC) - timedelta(days=1, hours=1)).isoformat()
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"occurred_at": yesterday})
    assert (response.status_code, response.json()["detail"]) == (422, svc.MOVE_TODAY)
    start, _ = svc.day_range(india_today() - timedelta(days=1))
    old = await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(hours=1))
    for request in (client.patch(f"{ACTIVITIES}/{old.id}", json={"note": "late"}), client.delete(f"{ACTIVITIES}/{old.id}")):
        response = await request
        assert (response.status_code, response.json()["detail"]) == (409, svc.NOT_TODAY)


@pytest.mark.asyncio
async def test_empty_patch_changes_nothing_and_writes_no_audit(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={})).status_code == 200
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]))).all()
    assert actions == ["bdm_activity.created"]


@pytest.mark.asyncio
async def test_delete_today_removes_the_row_and_audits(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="private"))).json()
    response = await client.delete(f"{ACTIVITIES}/{created['id']}")
    assert response.status_code == 204
    assert await db_session.get(BdmActivity, uuid.UUID(created["id"]), populate_existing=True) is None
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "bdm_activity.deleted"))
    assert row.metadata_json == {"organization_id": org["id"], "channel": "call"}
    assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_contact_must_belong_to_the_organization_and_survives_contact_delete(client, db_session):
    _, _, other = await bdm_with_org(client, db_session)
    foreign = other["contacts"][0]["id"]
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao", "role": "principal"}, {"name": "Ms Iyer"}])
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=foreign))
    assert (response.status_code, response.json()["detail"]) == (422, svc.CONTACT_INVALID)
    iyer = org["contacts"][1]["id"]
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=iyer))).json()
    assert created["contact_name"] == "Ms Iyer"
    assert (await client.delete(f"/api/v1/bdm/organizations/{org['id']}/contacts/{iyer}")).status_code == 200  # bdm-002 route
    listed = (await client.get(ACTIVITIES)).json()["items"]
    mine = next(i for i in listed if i["id"] == created["id"])
    assert (mine["contact_id"], mine["contact_name"], mine["contact_removed"]) == (None, "Ms Iyer", True)
