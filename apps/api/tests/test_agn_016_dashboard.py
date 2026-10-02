"""AGN-016 AC10, AC11 -- the agent dashboard's "Pending actions" metric, the Tasks portal section, and AGN-021 activity."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world
from tests.agn016_helpers import TASKS, due, mk_task

DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    m = w["master"]
    unassigned = await mk_record(db_session, agent=m, full_name="Unassigned")
    archived = await mk_record(db_session, agent=m, full_name="Archived", status="archived", assigned_member=w["staff"]["member"])
    await mk_task(db_session, record=w["record"], author=m)  # staff's student, open
    await mk_task(db_session, record=w["linked_record"], author=m, due_at=due(hours=-3))  # staff's student, open and overdue
    await mk_task(db_session, record=unassigned, author=m)  # Master only
    await mk_task(db_session, record=w["record"], author=m, status="done")  # closed: not pending
    await mk_task(db_session, record=archived, author=m)  # archived student: not pending
    other_record = await mk_record(db_session, agent=w["other"]["master"], full_name="Other agency")
    await mk_task(db_session, record=other_record, author=w["other"]["master"])  # another agency
    return w


async def _metrics(email) -> list[dict]:
    async with client_for(email) as c:
        response = await c.get(DASHBOARD)
    assert response.status_code == 200, response.text
    return response.json()["metrics"]


@pytest.mark.asyncio
async def test_master_sees_the_agencys_pending_actions_after_applications(world):
    metrics = await _metrics(world["master"].email)
    labels = [m["label"] for m in metrics]
    assert labels[:3] == ["Students", "Applications", "Pending actions"]
    assert {m["label"]: m["value"] for m in metrics}["Pending actions"] == 3


@pytest.mark.asyncio
async def test_staff_see_only_their_students_pending_actions(world):
    stats = {m["label"]: m["value"] for m in await _metrics(world["staff"]["user"].email)}
    assert stats["Pending actions"] == 2
    assert {m["label"]: m["value"] for m in await _metrics(world["other_staff"]["user"].email)}["Pending actions"] == 0


@pytest.mark.asyncio
async def test_tasks_portal_section_is_a_header_for_both_roles(world):
    for email in (world["master"].email, world["staff"]["user"].email):
        async with client_for(email) as c:
            response = await c.get("/api/v1/portal/overseas/agent/tasks")
        assert response.status_code == 200, response.text
        assert response.json()["title"] == "Tasks & follow-ups"


@pytest.mark.asyncio
async def test_staff_task_work_appears_in_activity_with_field_names_only(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        created = (await c.post(TASKS, json={"agent_student_id": str(world["record"].id), "title": "Ring the bank", "due_at": due().isoformat()})).json()["task"]
        assert (await c.patch(f"{TASKS}/{created['id']}", json={"notes": "Private"})).status_code == 200
        assert (await c.patch(f"{TASKS}/{created['id']}", json={"status": "done"})).status_code == 200
    async with client_for(world["master"].email) as m:
        items = (await m.get(f"/api/v1/workflows/overseas/agent/team/staff/{world['staff']['member'].id}/activity")).json()["items"]
    got = [(i["action"], i["subject"], i["fields"]) for i in items[:3]]
    name = world["record"].full_name
    assert got == [("agent_student.task_complete", name, None), ("agent_student.task_update", name, ["notes"]), ("agent_student.task_add", name, None)]
