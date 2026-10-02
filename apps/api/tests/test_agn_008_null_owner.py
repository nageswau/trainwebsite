"""AGN-008 AC08/AC09 -- applications of students with no login appear, with their owner, in every shared list; School-bridged rows
stay out exactly where they were out before (spec §5.6, A6, A12)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world, mk_application, mk_school_student


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["no_login_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    w["linked_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"])
    w["school_app"] = await mk_application(db_session, agent=None, university=w["university"], school_student=await mk_school_student(db_session))
    w["rep"] = await mk_user(db_session, role="university_rep", full_name="Rep", profile={"university_id": str(w["university"].id)})
    w["admin"] = await mk_user(db_session, role="overseas_admin", full_name="Admin")
    return w


def _by_id(rows, key="id"):
    return {str(r[key]): r for r in rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["rep", "admin", "master"])
async def test_workflows_list_shows_the_no_login_owner(world, who):
    user = world[who]
    async with client_for(user.email) as c:
        response = await c.get("/api/v1/workflows/overseas/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    no_login = rows[str(world["no_login_app"].id)]
    assert no_login["student"] == world["record"].full_name and no_login["student_id"] is None
    assert rows[str(world["linked_app"].id)]["student"] == world["linked_user"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_admin_applications_shows_the_no_login_owner(world):
    async with client_for(world["admin"].email) as c:
        response = await c.get("/api/v1/admin/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    assert rows[str(world["no_login_app"].id)]["student"] == world["record"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_staff_see_their_assigned_no_login_application_and_not_others(db_session, world):
    unassigned = await mk_application(db_session, agent=world["master"], university=world["university"], record=await mk_record(db_session, agent=world["master"], full_name="Unassigned"))
    async with client_for(world["staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) in rows and str(world["linked_app"].id) in rows
    assert str(unassigned.id) not in rows
    async with client_for(world["other_staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) not in rows


@pytest.mark.asyncio
async def test_school_bridged_rows_stay_out_of_the_lists(world):
    for who in ("admin", "rep"):
        async with client_for(world[who].email) as c:
            ids = {str(r["id"]) for r in (await c.get("/api/v1/workflows/overseas/applications")).json()}
        assert str(world["school_app"].id) not in ids
