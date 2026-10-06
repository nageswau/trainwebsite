"""bdm-025 -- POST /admin/bdms/{id}/handover for an inactive BDM (spec §5.3, L3) and reactivation (restores login only)."""

import pytest
from sqlalchemy import select

from app.models import BdmAppointment, BdmOrganization, BdmTask, Notification, User
from tests.bdm001_helpers import login, make_user
from tests.bdm025_helpers import BDMS, appt, as_super, audit_rows, deactivate, fresh, history, org, task, team


async def handover(client, bdm_id, target_id):
    return await client.post(f"{BDMS}/{bdm_id}/handover", json={"reassign_to": str(target_id)})


@pytest.mark.asyncio
async def test_leave_then_hand_over_later(client, db_session):
    _, a, b = await team(db_session)
    o = await org(db_session, a)
    x = await appt(db_session, a, o)
    t = await task(db_session, a)
    admin = await as_super(client, db_session)
    assert (await deactivate(client, a.id, {"mode": "leave"})).status_code == 200
    response = await handover(client, a.id, b.id)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "moved": {"organizations": 1, "appointments": 1, "tasks": 1}}
    assert (await fresh(db_session, BdmOrganization, o.id)).assigned_bdm_user_id == b.id
    assert (await fresh(db_session, BdmAppointment, x.id)).bdm_user_id == b.id
    assert (await fresh(db_session, BdmTask, t.id)).assignee_user_id == b.id
    [row] = await history(db_session, o.id)
    assert (row.reason, row.actor_user_id) == ("portfolio_handover", admin.id)
    [audit] = await audit_rows(db_session, "bdm.portfolio_handover", a.id)
    assert audit.metadata_json == {"reassign_to": str(b.id), "moved": {"organizations": 1, "appointments": 1, "tasks": 1}}
    assert (await db_session.scalars(select(Notification.title).where(Notification.user_id == b.id))).all() == ["Work handed over to you"]
    assert (await fresh(db_session, User, a.id)).active is False


@pytest.mark.asyncio
async def test_refusals(client, db_session):
    manager, a, b = await team(db_session)
    await org(db_session, a)
    await as_super(client, db_session)
    response = await handover(client, a.id, b.id)
    assert response.status_code == 409 and response.json()["detail"] == "Deactivate this BDM first"
    assert (await deactivate(client, a.id, {"mode": "leave"})).status_code == 200
    response = await handover(client, a.id, manager.id)
    assert response.status_code == 422 and response.json()["detail"] == "Choose an active BDM of the same module"
    assert (await client.post(f"{BDMS}/{a.id}/handover", json={})).status_code == 422
    assert (await handover(client, a.id, b.id)).status_code == 200
    response = await handover(client, a.id, b.id)
    assert response.status_code == 409 and response.json()["detail"] == "No open work to hand over"
    client.cookies.clear()
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await handover(client, a.id, b.id)).status_code == 403


@pytest.mark.asyncio
async def test_reactivation_restores_login_not_the_portfolio(client, db_session):
    _, a, b = await team(db_session)
    o = await org(db_session, a)
    await as_super(client, db_session)
    assert (await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})).status_code == 200
    assert (await client.patch(f"/api/v1/admin/users/{a.id}", json={"active": True})).status_code == 200
    assert (await fresh(db_session, User, a.id)).active is True
    assert (await fresh(db_session, BdmOrganization, o.id)).assigned_bdm_user_id == b.id
    client.cookies.clear()
    await login(client, a)
    assert (await client.get("/api/v1/bdm/me")).status_code == 200
