"""AGN-017 AC1-AC3, AC7 -- each agency event creates exactly one notice per recipient, in the request's transaction; refused or no-op
writes create none; bodies carry no names or user-typed text."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn004_helpers import RECORDS
from tests.agn008_helpers import agency_world
from tests.agn016_helpers import mk_task
from tests.agn017_helpers import channels_of, notices, titled

ASSIGNED = "Student assigned to you"


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


# --- assignment (N1, N9) ---------------------------------------------------------------------------------------------------------


async def _assign(world, member_id):
    async with client_for(world["master"].email) as c:
        return await c.post(f"{RECORDS}/{world['record'].id}/assign", json={"member_id": str(member_id) if member_id else None})


@pytest.mark.asyncio
async def test_reassigning_tells_only_the_new_assignee_with_the_open_tasks_that_moved(db_session, world):
    for status in ("open", "open", "done"):
        await mk_task(db_session, record=world["record"], author=world["master"], status=status)
    response = await _assign(world, world["other_staff"]["member"].id)
    assert response.status_code == 200, response.text
    [item] = await notices(db_session, world["other_staff"]["user"])
    assert (item.title, item.action_url) == (ASSIGNED, "/overseas/agent/students")
    assert item.body == "A student is now assigned to you. 2 open tasks moved with them."
    assert world["record"].full_name not in item.body
    assert await channels_of(db_session, item) == ["email"]
    assert await notices(db_session, world["staff"]["user"]) == []  # N9: the previous assignee is not told
    assert await notices(db_session, world["master"]) == []  # the actor


@pytest.mark.asyncio
async def test_assigning_a_student_without_open_tasks_omits_the_count(db_session, world):
    await _assign(world, world["other_staff"]["member"].id)
    [item] = await notices(db_session, world["other_staff"]["user"])
    assert item.body == "A student is now assigned to you."


@pytest.mark.asyncio
async def test_reassigning_the_current_assignee_or_unassigning_notifies_nobody(db_session, world):
    assert (await _assign(world, world["staff"]["member"].id)).status_code == 200
    assert (await _assign(world, None)).status_code == 200
    for user in (world["staff"]["user"], world["other_staff"]["user"], world["master"]):
        assert await titled(db_session, user, ASSIGNED) == []
