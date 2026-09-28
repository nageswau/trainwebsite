import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, UserRoleAssignment
from tests.agn001_helpers import login, mk_active_org, mk_user, org_of, register_agent

ORG_ACTION = "/api/v1/overseas-admin/agent-orgs/{oid}/{action}"


async def _admin(client, db):
    admin = await mk_user(db, role="overseas_admin")
    await login(client, admin.email)
    return admin


async def _audits(db, org_id, action):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == action))


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "action", "end"), [
    ("pending", "approve", "active"), ("rejected", "approve", "active"), ("pending", "reject", "rejected"),
    ("active", "suspend", "suspended"), ("suspended", "reinstate", "active"),
])
async def test_valid_transitions_change_status_and_audit(client, db_session, start, action, end):  # AC03
    ctx = await mk_active_org(db_session, name="Trans Agency")
    ctx["org"].status = start
    await db_session.commit()
    admin = await _admin(client, db_session)
    response = await client.post(ORG_ACTION.format(oid=ctx["org"].id, action=action))
    assert response.status_code == 200 and response.json() == {"id": str(ctx["org"].id), "status": end}
    org = await org_of(db_session, ctx["master"].id)
    assert org.status == end and org.status_changed_by_user_id == admin.id and org.status_changed_at is not None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(org.id), AuditLog.action == f"agent_org.{action}"))
    assert log.entity_type == "agent_org" and log.outcome == end and log.metadata_json == {"from": start} and log.user_id == admin.id


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "action"), [
    ("active", "approve"), ("suspended", "approve"), ("active", "reject"), ("rejected", "reject"), ("suspended", "reject"),
    ("pending", "suspend"), ("suspended", "suspend"), ("rejected", "suspend"),
    ("pending", "reinstate"), ("active", "reinstate"), ("rejected", "reinstate"),
])
async def test_invalid_transitions_are_409_with_no_change_and_no_audit(client, db_session, start, action):  # AC03
    ctx = await mk_active_org(db_session, name="Bad Trans")
    ctx["org"].status = start
    await db_session.commit()
    await _admin(client, db_session)
    response = await client.post(ORG_ACTION.format(oid=ctx["org"].id, action=action))
    assert response.status_code == 409 and response.json()["detail"] == f"Cannot {action} an organisation that is {start}"
    assert (await org_of(db_session, ctx["master"].id)).status == start
    assert await _audits(db_session, ctx["org"].id, f"agent_org.{action}") == 0


@pytest.mark.asyncio
async def test_unknown_org_is_404_and_non_admin_is_403(client, db_session):
    await _admin(client, db_session)
    assert (await client.post(ORG_ACTION.format(oid=uuid.uuid4(), action="approve"))).status_code == 404
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    ctx = await mk_active_org(db_session, name="Forbid")
    assert (await client.post(ORG_ACTION.format(oid=ctx["org"].id, action="suspend"))).status_code == 403
    assert (await client.get("/api/v1/overseas-admin/agent-orgs")).status_code == 403


@pytest.mark.asyncio
async def test_approve_and_reject_write_through_to_master_assignments(client, db_session):  # E11
    body = await register_agent(client, agency_name="Write Through")
    org = await org_of(db_session, body["user"]["id"])
    await _admin(client, db_session)
    await client.post(ORG_ACTION.format(oid=org.id, action="approve"))
    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uuid.UUID(body["user"]["id"])).execution_options(populate_existing=True))
    assert assignment.approval_status == "approved"
    await client.post(ORG_ACTION.format(oid=org.id, action="suspend"))
    await db_session.refresh(assignment)
    assert assignment.approval_status == "approved"  # suspend does not touch assignments


@pytest.mark.asyncio
async def test_list_groups_masters_and_filters_by_status(client, db_session):
    ctx = await mk_active_org(db_session, name="Listed Agency")
    await _admin(client, db_session)
    page = (await client.get("/api/v1/overseas-admin/agent-orgs?status=active")).json()
    assert set(page) == {"items", "total", "limit", "offset"} and page["limit"] == 25 and page["offset"] == 0
    row = page["items"][0]  # newest first: the org just created
    assert row["id"] == str(ctx["org"].id)
    assert row["name"] == "Listed Agency" and row["prefix"] == ctx["org"].prefix and row["status"] == "active"
    assert row["masters"] == [{"id": str(ctx["member"].id), "code": ctx["member"].code, "full_name": ctx["master"].full_name, "email": ctx["master"].email, "status": "active"}]
    assert all(r["status"] == "active" for r in page["items"])
    assert (await client.get("/api/v1/overseas-admin/agent-orgs?status=approved")).status_code == 422


@pytest.mark.asyncio
async def test_the_list_is_paginated_newest_first(client, db_session):  # review: unbounded list
    made = [await mk_active_org(db_session, name=f"Page Agency {i}") for i in range(3)]
    for ctx in made:
        ctx["org"].status = "suspended"
    await db_session.commit()
    await _admin(client, db_session)
    first = (await client.get("/api/v1/overseas-admin/agent-orgs?status=suspended&limit=2&offset=0")).json()
    second = (await client.get("/api/v1/overseas-admin/agent-orgs?status=suspended&limit=2&offset=2")).json()
    assert first["total"] == second["total"] >= 3 and len(first["items"]) == 2 and first["limit"] == 2 and second["offset"] == 2
    assert [r["id"] for r in first["items"]] == [str(made[2]["org"].id), str(made[1]["org"].id)]
    assert str(made[0]["org"].id) == second["items"][0]["id"]
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
async def test_out_of_range_paging_is_422(client, db_session, query):
    await _admin(client, db_session)
    assert (await client.get(f"/api/v1/overseas-admin/agent-orgs?{query}")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "end", "audit"), [("approve", "active", "agent.approve"), ("reject", "rejected", "agent.reject")])
async def test_old_routes_keep_their_audit_and_set_the_org(client, db_session, action, end, audit):  # E4
    body = await register_agent(client, agency_name="Old Route")
    await _admin(client, db_session)
    response = await client.post(f"/api/v1/overseas-admin/agents/{body['user']['id']}/{action}")
    assert response.status_code == 200 and response.json()["approval_status"] == ("approved" if action == "approve" else "rejected")
    assert (await org_of(db_session, body["user"]["id"])).status == end
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == audit, AuditLog.entity_type == "user_role_assignment").order_by(AuditLog.created_at.desc())) is not None


@pytest.mark.asyncio
async def test_old_reject_still_works_on_an_active_org(client, db_session):  # E4 any-state
    ctx = await mk_active_org(db_session, name="Any State")
    await _admin(client, db_session)
    assert (await client.post(f"/api/v1/overseas-admin/agents/{ctx['master'].id}/reject")).status_code == 200
    assert (await org_of(db_session, ctx["master"].id)).status == "rejected"
