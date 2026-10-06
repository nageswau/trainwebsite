"""bdm-025 -- POST /admin/bdms/{id}/deactivate and GET /admin/bdms/{id}/portfolio (spec §5.1, §5.2, §5.4; AC1, AC2, AC5)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, BdmAppointment, BdmOrganization, BdmTask, BdmTrip, Notification, User
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm008_helpers import bdm_logs
from tests.bdm025_helpers import (
    BDMS,
    appt,
    as_super,
    audit_rows,
    deactivate,
    fresh,
    history,
    org,
    task,
    team,
    trip,
)


async def _portfolio(db, a):
    """A's live work (moves) and history (stays)."""
    orgs = [await org(db, a) for _ in range(3)]
    live = {
        "orgs": orgs,
        "appts": [await appt(db, a, orgs[0], hours=24), await appt(db, a, orgs[1], hours=72, status="confirmed")],
        "tasks": [await task(db, a, organization=orgs[0]), await task(db, a)],
    }
    archived = await org(db, a, archived=True)
    stays = {
        "org": archived,
        "appts": [
            await appt(db, a, orgs[0], hours=-48, status="completed"),
            await appt(db, a, orgs[0], hours=30, status="cancelled"),
            await appt(db, a, orgs[0], hours=-2, status="scheduled"),  # past, outcome pending: stays with A
        ],
        "tasks": [await task(db, a, status="done"), await task(db, a, status="cancelled")],
        "trip": await trip(db, a, approval="approved", travel="in_progress"),
    }
    return live, stays


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"reassign_to": None}, {"mode": "reassign"}, {"mode": "leave", "reassign_to": str(uuid.uuid4())}])
async def test_deactivate_without_a_choice_is_422(client, db_session, body):
    _, a, _ = await team(db_session)
    await as_super(client, db_session)
    response = await deactivate(client, a.id, body)
    assert response.status_code == 422
    assert (await fresh(db_session, User, a.id)).active is True


@pytest.mark.asyncio
async def test_reassign_moves_every_open_item_and_notifies(client, db_session):
    _, a, b = await team(db_session)
    live, _ = await _portfolio(db_session, a)
    admin = await as_super(client, db_session)
    counts = (await client.get(f"{BDMS}/{a.id}/portfolio")).json()
    assert counts == {"organizations": 3, "appointments": 2, "tasks": 2, "trips": 0}

    response = await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "active": False, "mode": "reassign",
                               "moved": {"organizations": 3, "appointments": 2, "tasks": 2}, "trips_cancelled": 0}
    assert (await fresh(db_session, User, a.id)).active is False
    for o in live["orgs"]:
        assert (await fresh(db_session, BdmOrganization, o.id)).assigned_bdm_user_id == b.id
        [row] = await history(db_session, o.id)
        assert (row.entity_type, row.from_user_id, row.to_user_id, row.actor_user_id, row.reason) == ("organization", a.id, b.id, admin.id, "bdm_deactivated")
    for x in live["appts"]:
        assert (await fresh(db_session, BdmAppointment, x.id)).bdm_user_id == b.id
        assert [r.entity_type for r in await history(db_session, x.id)] == ["appointment"]
    for t in live["tasks"]:
        assert (await fresh(db_session, BdmTask, t.id)).assignee_user_id == b.id
    [audit] = await audit_rows(db_session, "bdm.deactivate", a.id)
    assert audit.user_id == admin.id and audit.metadata_json == {
        "mode": "reassign", "reassign_to": str(b.id), "moved": {"organizations": 3, "appointments": 2, "tasks": 2}, "trips_cancelled": 0}
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == b.id))).all()
    assert note.title == "Work handed over to you" and note.action_url == "/bdm/organizations"
    assert "3 organizations, 2 appointments and 2 follow-ups/tasks" in note.body and a.full_name in note.body
    client.cookies.clear()
    response = await client.post("/api/v1/auth/login", json={"email": a.email, "password": "Sup3r-Secret-Pass!", "division": a.division})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_history_stays_with_the_original_bdm(client, db_session):
    _, a, b = await team(db_session)
    _, stays = await _portfolio(db_session, a)
    await as_super(client, db_session)
    assert (await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})).status_code == 200
    assert (await fresh(db_session, BdmOrganization, stays["org"].id)).assigned_bdm_user_id == a.id
    for x in stays["appts"]:
        assert (await fresh(db_session, BdmAppointment, x.id)).bdm_user_id == a.id
    for t in stays["tasks"]:
        assert (await fresh(db_session, BdmTask, t.id)).assignee_user_id == a.id
    in_progress = await fresh(db_session, BdmTrip, stays["trip"].id)
    assert (in_progress.bdm_user_id, in_progress.travel_status) == (a.id, "in_progress")
    for row_id in [stays["org"].id, *(x.id for x in stays["appts"]), *(t.id for t in stays["tasks"])]:
        assert await history(db_session, row_id) == []


@pytest.mark.asyncio
async def test_not_started_trips_are_cancelled(client, db_session):
    manager, a, b = await team(db_session)
    trips = [await trip(db_session, a), await trip(db_session, a, approval="submitted"), await trip(db_session, a, approval="approved"),
             await trip(db_session, a, approval="rejected")]
    done = await trip(db_session, a, approval="approved", travel="completed")
    await as_super(client, db_session)
    assert (await client.get(f"{BDMS}/{a.id}/portfolio")).json()["trips"] == 4
    response = await deactivate(client, a.id, {"mode": "leave"})
    assert response.status_code == 200 and response.json()["trips_cancelled"] == 4
    for t in trips:
        row = await fresh(db_session, BdmTrip, t.id)
        assert row.travel_status == "cancelled" and row.cancelled_at is not None and row.bdm_user_id == a.id
        [audit] = await audit_rows(db_session, "bdm.trip_cancel", t.id)
        assert audit.metadata_json["reason"] == "BDM deactivated"
    assert (await fresh(db_session, BdmTrip, done.id)).travel_status == "completed"
    client.cookies.clear()
    await login(client, manager)
    queue = (await client.get("/api/v1/bdm/manager/approvals")).json()
    assert str(trips[1].id) not in {r["id"] for r in queue["items"]}


@pytest.mark.asyncio
async def test_leave_keeps_items_with_the_inactive_bdm(client, db_session):
    _, a, b = await team(db_session)
    live, _ = await _portfolio(db_session, a)
    await as_super(client, db_session)
    response = await deactivate(client, a.id, {"mode": "leave"})
    assert response.status_code == 200
    assert response.json()["moved"] == {"organizations": 0, "appointments": 0, "tasks": 0}
    assert (await fresh(db_session, User, a.id)).active is False
    assert (await fresh(db_session, BdmOrganization, live["orgs"][0].id)).assigned_bdm_user_id == a.id
    assert await history(db_session, live["orgs"][0].id) == []
    assert (await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == b.id))) == 0
    [audit] = await audit_rows(db_session, "bdm.deactivate", a.id)
    assert audit.metadata_json["mode"] == "leave" and audit.metadata_json["reassign_to"] is None
    assert (await client.get(f"{BDMS}/{a.id}/portfolio")).json() == {"organizations": 3, "appointments": 2, "tasks": 2, "trips": 0}


@pytest.mark.asyncio
async def test_invalid_targets_are_one_422(client, db_session):
    manager, a, _ = await team(db_session)
    o = await org(db_session, a)
    other_type = await make_bdm(db_session, manager, "school")
    inactive = await make_bdm(db_session, manager, active=False)
    for target in (other_type.id, inactive.id, a.id, manager.id, uuid.uuid4()):
        await as_super(client, db_session)
        response = await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(target)})
        assert response.status_code == 422 and response.json()["detail"] == "Choose an active BDM of the same module"
    assert (await fresh(db_session, User, a.id)).active is True
    assert (await fresh(db_session, BdmOrganization, o.id)).assigned_bdm_user_id == a.id
    assert await audit_rows(db_session, "bdm.deactivate", a.id) == []


@pytest.mark.asyncio
async def test_scope(client, db_session):
    _, a, b = await team(db_session)
    body = {"mode": "reassign", "reassign_to": str(b.id)}
    client.cookies.clear()
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await deactivate(client, a.id, body)).status_code == 403
    assert (await client.get(f"{BDMS}/{a.id}/portfolio")).status_code == 403
    client.cookies.clear()
    await login(client, await make_manager(db_session))
    assert (await deactivate(client, a.id, body)).status_code == 403
    client.cookies.clear()
    await login(client, a)
    assert (await deactivate(client, a.id, body)).status_code == 403
    client.cookies.clear()
    await login(client, await make_user(db_session, "it_admin", "it"))
    not_a_bdm = await make_user(db_session, "it_student", "it")
    assert (await deactivate(client, not_a_bdm.id, body)).status_code == 404
    assert (await deactivate(client, uuid.uuid4(), body)).status_code == 404
    assert (await fresh(db_session, User, a.id)).active is True
    assert (await deactivate(client, a.id, body)).status_code == 200


@pytest.mark.asyncio
async def test_already_inactive_is_409(client, db_session):
    _, a, b = await team(db_session)
    await as_super(client, db_session)
    assert (await deactivate(client, a.id, {"mode": "leave"})).status_code == 200
    response = await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})
    assert response.status_code == 409 and response.json()["detail"] == "This BDM is already inactive"
    assert len(await audit_rows(db_session, "bdm.deactivate", a.id)) == 1


@pytest.mark.asyncio
async def test_logs_carry_ids_only(client, db_session, caplog, monkeypatch):
    _, a, b = await team(db_session)
    await org(db_session, a)
    await as_super(client, db_session)
    bdm_logs(caplog, monkeypatch)
    assert (await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})).status_code == 200
    records = [r for r in caplog.records if r.getMessage() == "bdm_deactivated"]
    assert len(records) == 1
    fields = records[0].extra_fields
    assert fields["bdm_id"] == str(a.id) and fields["target_id"] == str(b.id) and fields["organizations"] == 1
    assert a.email not in str(fields) and a.full_name not in str(fields)


@pytest.mark.asyncio
async def test_single_reassign_writes_history(client, db_session):
    """§5.8: bdm-002's manager reassign of one organization is recorded in the same history table."""
    manager, a, b = await team(db_session)
    o = await org(db_session, a)
    client.cookies.clear()
    await login(client, manager)
    response = await client.post(f"/api/v1/bdm/organizations/{o.id}/assign", json={"bdm_user_id": str(b.id)})
    assert response.status_code == 200, response.text
    [row] = await history(db_session, o.id)
    assert (row.entity_type, row.from_user_id, row.to_user_id, row.actor_user_id, row.reason) == ("organization", a.id, b.id, manager.id, "organization_reassigned")


@pytest.mark.asyncio
async def test_no_audit_or_write_when_unauthenticated(client, db_session):
    _, a, b = await team(db_session)
    client.cookies.clear()
    assert (await deactivate(client, a.id, {"mode": "leave"})).status_code == 401
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(a.id))) == 0
