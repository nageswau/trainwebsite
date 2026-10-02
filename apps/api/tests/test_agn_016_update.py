"""AGN-016 AC03, AC05, AC06, AC07 -- editing, completing and cancelling a task; closed and archived refusals; reassignment."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentTask, AuditLog
from app.services import agent_tasks as service
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import RECORDS, mk_record
from tests.agn008_helpers import agency_world, mk_application
from tests.agn016_helpers import TASKS, due, mk_task


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["task"] = await mk_task(db_session, record=w["record"], author=w["master"], title="Call", notes="Old notes")
    return w


async def _audits(db, task, action) -> list[AuditLog]:
    rows = (await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(task.agent_student_id)))).all()
    return [r for r in rows if r.metadata_json.get("task_id") == str(task.id)]


async def _patch(email, task, body):
    async with client_for(email) as c:
        return await c.patch(f"{TASKS}/{task.id}", json=body)


@pytest.mark.asyncio
async def test_assigned_staff_edits_fields_and_the_audit_names_fields_only(db_session, world):
    new_due = due(days=5)
    response = await _patch(world["staff"]["user"].email, world["task"], {"title": "Call again", "notes": "Secret passport A123", "due_at": new_due.isoformat()})
    assert response.status_code == 200, response.text
    body = response.json()["task"]
    assert (body["title"], body["notes"], body["status"]) == ("Call again", "Secret passport A123", "open")
    row = await db_session.get(AgentTask, world["task"].id, populate_existing=True)
    assert row.updated_by_user_id == world["staff"]["user"].id and row.due_at == new_due
    [audit] = await _audits(db_session, world["task"], "agent_student.task_update")
    assert audit.metadata_json["fields"] == ["due_at", "notes", "title"]
    assert "passport" not in str(audit.metadata_json).lower()


@pytest.mark.asyncio
async def test_no_op_and_empty_patches_audit_nothing(db_session, world):
    for body in ({}, {"title": "Call"}, {"notes": "Old notes"}):
        assert (await _patch(world["master"].email, world["task"], body)).status_code == 200
    assert await _audits(db_session, world["task"], "agent_student.task_update") == []


@pytest.mark.asyncio
async def test_null_notes_clear_them(db_session, world):  # Review Focus 4
    response = await _patch(world["master"].email, world["task"], {"notes": None})
    assert response.status_code == 200 and response.json()["task"]["notes"] is None
    [audit] = await _audits(db_session, world["task"], "agent_student.task_update")
    assert audit.metadata_json["fields"] == ["notes"]


@pytest.mark.asyncio
async def test_application_relink_rules(db_session, world):
    own = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"])
    sibling = await mk_record(db_session, agent=world["master"], full_name="Sibling")
    theirs = await mk_application(db_session, agent=world["master"], university=world["university"], record=sibling)
    assert (await _patch(world["master"].email, world["task"], {"application_id": str(own.id)})).json()["task"]["application"]["id"] == str(own.id)
    response = await _patch(world["master"].email, world["task"], {"application_id": str(theirs.id)})
    assert (response.status_code, response.json()["detail"]) == (422, service.APPLICATION_REFUSED)
    assert (await _patch(world["master"].email, world["task"], {"application_id": None})).json()["task"]["application"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "action"), [("done", "agent_student.task_complete"), ("cancelled", "agent_student.task_cancel")])
async def test_closing_stamps_who_and_when(db_session, world, status, action):
    response = await _patch(world["staff"]["user"].email, world["task"], {"status": status})
    assert response.status_code == 200, response.text
    body = response.json()["task"]
    assert (body["status"], body["closed_by"], body["overdue"]) == (status, world["staff"]["user"].full_name, False)
    assert body["closed_at"] is not None
    row = await db_session.get(AgentTask, world["task"].id, populate_existing=True)
    assert row.closed_by_user_id == world["staff"]["user"].id
    [audit] = await _audits(db_session, world["task"], action)
    assert audit.metadata_json == {"task_id": str(world["task"].id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"status": "done"}, {"status": "cancelled"}, {"title": "Reopen by edit"}])
async def test_a_closed_task_is_read_only(db_session, world, body):
    closed = await mk_task(db_session, record=world["record"], author=world["master"], title="Closed", status="done")
    response = await _patch(world["master"].email, closed, body)
    assert (response.status_code, response.json()["detail"]) == (409, service.CLOSED)
    row = await db_session.get(AgentTask, closed.id, populate_existing=True)
    assert (row.status, row.title) == ("done", "Closed")


@pytest.mark.asyncio
async def test_an_archived_students_task_is_read_only(db_session, world):
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived", status="archived")
    task = await mk_task(db_session, record=archived, author=world["master"])
    for body in ({"title": "Edit"}, {"status": "done"}):
        response = await _patch(world["master"].email, task, body)
        assert (response.status_code, response.json()["detail"]) == (409, "Unarchive this student first")
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{TASKS}/{task.id}")).status_code == 200  # reads still work


@pytest.mark.asyncio
async def test_out_of_scope_writes_are_404_and_other_roles_403(db_session, world):
    for email in (world["other_staff"]["user"].email, world["other"]["master"].email):
        response = await _patch(email, world["task"], {"status": "done"})
        assert (response.status_code, response.json()["detail"]) == (404, service.NOT_FOUND)
    counselor = await mk_user(db_session, role="counselor")
    assert (await _patch(counselor.email, world["task"], {"status": "done"})).status_code == 403
    assert (await db_session.get(AgentTask, world["task"].id, populate_existing=True)).status == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"status": "done", "title": "x"}, {"agent_student_id": "x"}, {"status": "open"}, {"title": None}])
async def test_invalid_patch_is_422(world, body):
    assert (await _patch(world["master"].email, world["task"], body)).status_code == 422


@pytest.mark.asyncio
async def test_reassigned_students_tasks_follow_the_new_owner(db_session, world):  # AC03, Review Focus 1
    before = await db_session.get(AgentTask, world["task"].id, populate_existing=True)
    updated_at = before.updated_at
    async with client_for(world["master"].email) as c:
        assert (await c.post(f"{RECORDS}/{world['record'].id}/assign", json={"member_id": str(world["other_staff"]["member"].id)})).status_code == 200
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.get(f"{TASKS}/{world['task'].id}")).status_code == 404
        assert (await c.patch(f"{TASKS}/{world['task'].id}", json={"status": "done"})).status_code == 404
        assert str(world["task"].id) not in {t["id"] for t in (await c.get(TASKS)).json()["items"]}
    async with client_for(world["other_staff"]["user"].email) as c:
        listed = (await c.get(TASKS)).json()["items"]
    assert [t["id"] for t in listed] == [str(world["task"].id)]
    assert listed[0]["assigned_to"]["code"] == world["other_staff"]["member"].code
    after = await db_session.get(AgentTask, world["task"].id, populate_existing=True)
    assert (after.status, after.updated_at) == ("open", updated_at)  # nothing was written to the task
