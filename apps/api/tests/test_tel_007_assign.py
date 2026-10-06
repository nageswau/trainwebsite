"""tel-007 -- the unassigned queue, the team's assigned leads and manual (re)assignment (spec §5; AC5, D3, D4, DI4, T23)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadStageHistory
from tests.tel007_helpers import ASSIGN, ASSIGNED, UNASSIGNED, lead, login, make_telecaller, make_tl_manager, make_user


async def _team(client, db, *, team="it"):
    manager = await make_tl_manager(db)
    a, b = await make_telecaller(db, manager, team=team), await make_telecaller(db, manager, team=team)
    await login(client, manager)
    return manager, a, b


async def _find(client, url, row, **params):
    response = await client.get(url, params={"q": row.name, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _fresh(db, row):
    return await db.get(Enquiry, row.id, populate_existing=True)


# --- the queue and the team's leads (DI4, T23) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_queue_holds_the_unassigned_leads_of_my_reports_teams(client, db_session):
    _, a, _ = await _team(client, db_session)
    mine, other_team, taken = await lead(db_session, city_name="Pune"), await lead(db_session, division="overseas"), await lead(db_session, telecaller=a)
    [item] = await _find(client, UNASSIGNED, mine)
    assert (item["id"], item["lead_code"], item["division"], item["city"], item["status"], item["status_label"], item["telecaller"]) == (
        str(mine.id), mine.lead_code, "it", "Pune", "new", "New Lead", None)
    assert await _find(client, UNASSIGNED, other_team) == []  # no report on the Overseas team
    assert await _find(client, UNASSIGNED, taken) == []
    assert (await client.get(UNASSIGNED, params={"q": mine.lead_code})).json()["total"] == 1


@pytest.mark.asyncio
async def test_a_manager_without_reports_has_an_empty_queue_and_super_admin_sees_both_teams(client, db_session):
    row = await lead(db_session, division="overseas")
    await login(client, await make_tl_manager(db_session))
    assert await _find(client, UNASSIGNED, row) == []
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert [i["id"] for i in await _find(client, UNASSIGNED, row)] == [str(row.id)]
    assert await _find(client, UNASSIGNED, row, team="it") == []


@pytest.mark.asyncio
async def test_the_assigned_tab_lists_my_reports_leads_only(client, db_session):
    _, a, b = await _team(client, db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    mine, theirs = await lead(db_session, telecaller=a), await lead(db_session, telecaller=stranger)
    [item] = await _find(client, ASSIGNED, mine)
    assert item["telecaller"] == {"id": str(a.id), "full_name": a.full_name, "active": True}
    assert await _find(client, ASSIGNED, theirs) == []
    assert await _find(client, ASSIGNED, mine, telecaller_user_id=str(b.id)) == []
    assert (await client.get(ASSIGNED, params={"telecaller_user_id": str(stranger.id)})).status_code == 404


@pytest.mark.asyncio
async def test_lists_refuse_other_roles(client, db_session):
    assert (await client.get(UNASSIGNED)).status_code == 401
    manager = await make_tl_manager(db_session)
    for user in (await make_telecaller(db_session, manager), await make_user(db_session, "it_admin", "it")):
        await login(client, user)
        for url in (UNASSIGNED, ASSIGNED):
            assert (await client.get(url)).status_code == 403
        assert (await client.post(ASSIGN, json={"lead_ids": [str(uuid.uuid4())], "telecaller_user_id": str(user.id)})).status_code == 403


# --- manual assignment (D3, D4) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manager_assigns_queue_leads_to_a_report(client, db_session):
    manager, a, _ = await _team(client, db_session)
    rows = [await lead(db_session), await lead(db_session)]
    body = {"lead_ids": [str(r.id) for r in rows], "telecaller_user_id": str(a.id)}
    response = await client.post(ASSIGN, json=body)
    assert (response.status_code, response.json()) == (200, {"assigned": 2, "unchanged": 0})
    for row in rows:
        fresh = await _fresh(db_session, row)
        assert (fresh.telecaller_user_id, fresh.status) == (a.id, "assigned")
        history = (await db_session.execute(select(LeadStageHistory.event, LeadStageHistory.actor_user_id).where(LeadStageHistory.lead_id == row.id))).all()
        assert history == [("assigned", manager.id)]
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead.assign", AuditLog.entity_id == str(row.id)))
        assert audit.user_id == manager.id and audit.metadata_json == {"from": None, "to": str(a.id), "method": "manual"}
    assert (await client.post(ASSIGN, json=body)).json() == {"assigned": 0, "unchanged": 2}  # a repeat changes nothing


@pytest.mark.asyncio
async def test_a_reassignment_keeps_the_stage(client, db_session):
    _, a, b = await _team(client, db_session)
    row = await lead(db_session, telecaller=a, status="contacted")
    response = await client.post(ASSIGN, json={"lead_ids": [str(row.id)], "telecaller_user_id": str(b.id)})
    assert response.json() == {"assigned": 1, "unchanged": 0}
    fresh = await _fresh(db_session, row)
    assert (fresh.telecaller_user_id, fresh.status) == (b.id, "contacted")
    assert (await db_session.scalar(select(AuditLog.metadata_json).where(AuditLog.action == "lead.assign", AuditLog.entity_id == str(row.id))))["from"] == str(a.id)


@pytest.mark.asyncio
async def test_assigning_outside_my_reports_is_403(client, db_session):
    """AC5."""
    _, a, _ = await _team(client, db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    row = await lead(db_session, telecaller=a)
    response = await client.post(ASSIGN, json={"lead_ids": [str(row.id)], "telecaller_user_id": str(stranger.id)})
    assert (response.status_code, response.json()["detail"]) == (403, "You can only assign leads to your direct reports")
    assert (await _fresh(db_session, row)).telecaller_user_id == a.id


@pytest.mark.asyncio
async def test_the_target_must_be_active_and_on_the_leads_team(client, db_session):
    manager, a, b = await _team(client, db_session)
    overseas = await make_telecaller(db_session, manager, team="overseas")
    b.active = False
    await db_session.commit()
    row = await lead(db_session)
    for target, detail in ((overseas, f"{overseas.full_name} is on the Overseas team"), (b, "This telecaller is inactive")):
        response = await client.post(ASSIGN, json={"lead_ids": [str(row.id)], "telecaller_user_id": str(target.id)})
        assert (response.status_code, response.json()["detail"]) == (422, detail)
    mixed = [str(row.id), str((await lead(db_session, division="overseas")).id)]
    response = await client.post(ASSIGN, json={"lead_ids": mixed, "telecaller_user_id": str(a.id)})
    assert (response.status_code, response.json()["detail"]) == (422, "Choose leads from one team")


@pytest.mark.asyncio
async def test_a_lead_out_of_scope_fails_the_whole_request(client, db_session):
    _, a, _ = await _team(client, db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    mine, theirs = await lead(db_session), await lead(db_session, telecaller=stranger)
    response = await client.post(ASSIGN, json={"lead_ids": [str(mine.id), str(theirs.id)], "telecaller_user_id": str(a.id)})
    assert (response.status_code, response.json()["detail"]) == (404, "Lead not found")
    assert (await _fresh(db_session, mine)).telecaller_user_id is None  # all or nothing
    assert (await client.post(ASSIGN, json={"lead_ids": [str(uuid.uuid4())], "telecaller_user_id": str(a.id)})).status_code == 404


@pytest.mark.asyncio
async def test_the_body_is_validated(client, db_session):
    _, a, _ = await _team(client, db_session)
    same = str(uuid.uuid4())
    for ids in ([], [same, same], [str(uuid.uuid4()) for _ in range(101)]):
        assert (await client.post(ASSIGN, json={"lead_ids": ids, "telecaller_user_id": str(a.id)})).status_code == 422
    assert (await client.post(ASSIGN, json={"lead_ids": [same], "telecaller_user_id": str(a.id), "method": "round_robin"})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_assigns_any_lead_to_any_telecaller(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    row = await lead(db_session, division="overseas")
    await login(client, await make_user(db_session, "super_admin", "global"))
    response = await client.post(ASSIGN, json={"lead_ids": [str(row.id)], "telecaller_user_id": str(tel.id)})
    assert response.json() == {"assigned": 1, "unchanged": 0}
