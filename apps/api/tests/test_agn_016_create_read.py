"""AGN-016 AC01, AC02, AC06, AC07, AC13 -- creating and reading a task: scope, gate, application link, archived student, cap."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentTask, AuditLog
from app.services import agent_tasks as service
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn016_helpers import TASK_KEYS, TASKS, due, mk_task, task_world


@pytest_asyncio.fixture
async def world(db_session):
    return await task_world(db_session)


def _body(record, **over):
    return {"agent_student_id": str(record.id), "title": "Call about the offer", "due_at": due().isoformat(), **over}


async def _tasks_of(db, record) -> int:
    return await db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.agent_student_id == record.id))


@pytest.mark.asyncio
async def test_master_creates_a_task_for_a_student_with_no_login(db_session, world):
    async with client_for(world["master"].email) as c:
        response = await c.post(TASKS, json=_body(world["record"], notes="Ask for the CAS letter"))
    assert response.status_code == 201, response.text
    task = response.json()["task"]
    assert set(task) == TASK_KEYS
    assert (task["status"], task["overdue"], task["notes"], task["application"], task["closed_by"]) == ("open", False, "Ask for the CAS letter", None, None)
    assert task["student"] == {"id": str(world["record"].id), "full_name": world["record"].full_name, "status": "active"}
    assert task["assigned_to"]["code"] == world["staff"]["member"].code
    assert task["created_by"] == world["master"].full_name
    row = await db_session.get(AgentTask, uuid.UUID(task["id"]), populate_existing=True)
    assert (row.created_by_user_id, row.updated_by_user_id, row.closed_at) == (world["master"].id, world["master"].id, None)
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "agent_student.task_add", AuditLog.entity_id == str(world["record"].id)))).all()
    assert len(audits) == 1 and audits[0].entity_type == "agent_student"
    assert audits[0].metadata_json["task_id"] == task["id"]
    assert "Call about the offer" not in str(audits[0].metadata_json) and "CAS" not in str(audits[0].metadata_json)  # AC11


@pytest.mark.asyncio
async def test_assigned_staff_creates_for_a_linked_student(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.post(TASKS, json=_body(world["linked_record"]))
    assert response.status_code == 201, response.text
    assert response.json()["task"]["student"]["full_name"] == world["linked_user"].full_name  # a linked student's name is their account's


@pytest.mark.asyncio
async def test_staff_cannot_create_for_an_unassigned_another_staffs_or_foreign_student(db_session, world):
    unassigned = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    theirs = await mk_record(db_session, agent=world["master"], full_name="Theirs", assigned_member=world["other_staff"]["member"])
    foreign = await mk_record(db_session, agent=world["other"]["master"], full_name="Foreign")
    async with client_for(world["staff"]["user"].email) as c:
        for record in (unassigned, theirs, foreign):
            response = await c.post(TASKS, json=_body(record))
            assert (response.status_code, response.json()["detail"]) == (404, "Student not found")
    for record in (unassigned, theirs, foreign):
        assert await _tasks_of(db_session, record) == 0


@pytest.mark.asyncio
async def test_read_is_scoped_to_the_students_owner(db_session, world):
    task = await mk_task(db_session, record=world["record"], author=world["master"])
    for email in (world["master"].email, world["staff"]["user"].email):
        async with client_for(email) as c:
            response = await c.get(f"{TASKS}/{task.id}")
        assert response.status_code == 200 and set(response.json()["task"]) == TASK_KEYS
    for email in (world["other_staff"]["user"].email, world["other"]["master"].email):
        async with client_for(email) as c:
            response = await c.get(f"{TASKS}/{task.id}")
        assert (response.status_code, response.json()["detail"]) == (404, "Task not found")
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{TASKS}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_admin", "overseas"), ("super_admin", "global")])
async def test_other_roles_are_refused(db_session, world, role, division):
    task = await mk_task(db_session, record=world["record"], author=world["master"])
    user = await mk_user(db_session, role=role, division=division)
    async with client_for(user.email) as c:
        assert (await c.get(f"{TASKS}/{task.id}")).status_code == 403
        assert (await c.post(TASKS, json=_body(world["record"]))).status_code == 403
    assert await _tasks_of(db_session, world["record"]) == 1


@pytest.mark.asyncio
async def test_suspended_agency_is_refused(db_session, world):
    world["org"].status = "suspended"
    await db_session.commit()
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.post(TASKS, json=_body(world["record"]))).status_code == 403
    assert await _tasks_of(db_session, world["record"]) == 0


@pytest.mark.asyncio
async def test_links_an_application_of_the_same_student(db_session, world):
    app = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"])
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.post(TASKS, json=_body(world["record"], application_id=str(app.id)))
    assert response.status_code == 201, response.text
    assert response.json()["task"]["application"] == {"id": str(app.id), "university": world["university"].name}


@pytest.mark.asyncio
async def test_links_a_pre_agn008_application_of_a_linked_student(db_session, world):
    legacy = await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"])
    async with client_for(world["master"].email) as c:
        response = await c.post(TASKS, json=_body(world["linked_record"], application_id=str(legacy.id)))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_refuses_an_application_that_is_not_this_students(db_session, world):
    other_record = await mk_record(db_session, agent=world["master"], full_name="Sibling", assigned_member=world["staff"]["member"])
    foreign_record = await mk_record(db_session, agent=world["other"]["master"], full_name="Foreign")
    apps = [
        await mk_application(db_session, agent=world["master"], university=world["university"], record=other_record),
        await mk_application(db_session, agent=world["other"]["master"], university=world["university"], record=foreign_record),
        await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="withdrawn"),
        await mk_application(db_session, agent=world["master"], university=world["university"], school_student=await mk_school_student(db_session)),
    ]
    async with client_for(world["master"].email) as c:
        for app in (*apps, None):
            application_id = str(app.id) if app else str(uuid.uuid4())
            response = await c.post(TASKS, json=_body(world["record"], application_id=application_id))
            assert (response.status_code, response.json()["detail"]) == (422, service.APPLICATION_REFUSED)
    assert await _tasks_of(db_session, world["record"]) == 0


@pytest.mark.asyncio
async def test_archived_student_takes_no_new_task(db_session, world):
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived", status="archived", assigned_member=world["staff"]["member"])
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.post(TASKS, json=_body(archived))
    assert (response.status_code, response.json()["detail"]) == (409, "Unarchive this student first")
    assert await _tasks_of(db_session, archived) == 0


@pytest.mark.asyncio
async def test_a_past_due_time_is_allowed_and_reads_as_overdue(db_session, world):
    async with client_for(world["master"].email) as c:
        response = await c.post(TASKS, json=_body(world["record"], due_at=due(hours=-2).isoformat()))
    assert response.status_code == 201 and response.json()["task"]["overdue"] is True


@pytest.mark.asyncio
async def test_open_task_cap_per_student(db_session, world):  # AC13
    for _ in range(service.OPEN_TASK_CAP - 1):
        db_session.add(AgentTask(agent_student_id=world["record"].id, title="Bulk", due_at=due(), created_by_user_id=world["master"].id, updated_by_user_id=world["master"].id))
    await db_session.commit()
    await mk_task(db_session, record=world["record"], author=world["master"], status="done")  # a closed task does not count
    async with client_for(world["master"].email) as c:
        assert (await c.post(TASKS, json=_body(world["record"]))).status_code == 201
        response = await c.post(TASKS, json=_body(world["record"]))
    assert (response.status_code, response.json()["detail"]) == (409, service.CAP_REACHED)
    assert await _tasks_of(db_session, world["record"]) == service.OPEN_TASK_CAP + 1
