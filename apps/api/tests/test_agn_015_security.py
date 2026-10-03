"""AGN-015 (DEC-SCOPE-061 §6) -- authentication, role, scope and cross-agency isolation for both read routes."""

import pytest

from app.models import AgentStudent
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn015_helpers import journey_url, mk_history, timeline_url

UNKNOWN = "00000000-0000-0000-0000-000000000000"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_out_of_scope_is_the_same_404(db_session, url):
    w = await world(db_session)
    async with client_for(w["plain"]["user"].email) as c:  # staff, not assigned this student
        unassigned = await c.get(url(w["record"].id))
        unknown = await c.get(url(UNKNOWN))
    async with client_for(w["other"]["master"].email) as c:
        other = await c.get(url(w["record"].id))
    assert unassigned.status_code == unknown.status_code == other.status_code == 404
    assert unassigned.json() == unknown.json() == other.json() == {"detail": "Student not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_non_agent_roles_are_refused(db_session, url):
    w = await world(db_session)
    counselor = await mk_user(db_session, role="counselor")
    async with client_for(counselor.email) as c:
        assert (await c.get(url(w["record"].id))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_no_session_is_401(client, url):
    assert (await client.get(url(UNKNOWN))).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_malformed_id_is_422(db_session, url):
    w = await world(db_session)
    async with client_for(w["master"].email) as c:
        assert (await c.get(url("not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_another_agencys_application_for_the_same_login_is_invisible(db_session):
    w = await world(db_session)
    other_record = AgentStudent(agent_id=w["other"]["master"].id, student_id=w["linked_user"].id, status="active")
    db_session.add(other_record)
    await db_session.commit()
    theirs = await mk_application(db_session, agent=w["other"]["master"], university=w["university"], record=other_record)
    await mk_history(db_session, theirs, to_status="enquiry", by=w["other"]["master"])
    await mk_doc(db_session, record=other_record)
    async with client_for(w["staff"]["user"].email) as c:
        j = (await c.get(journey_url(w["linked_record"].id))).json()
        t = (await c.get(timeline_url(w["linked_record"].id))).json()
    assert j["applications"] == [] and j["student"]["full_name"] == w["linked_user"].full_name
    assert j["steps"][3] == {"key": "documents", "state": "not_started"}
    assert [i["kind"] for i in t["items"]] == ["student_created"]


@pytest.mark.asyncio
async def test_staff_sees_their_assigned_students_journey(db_session):
    w = await world(db_session)
    app = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    async with client_for(w["staff"]["user"].email) as c:
        assert [a["id"] for a in (await c.get(journey_url(w["record"].id))).json()["applications"]] == [str(app.id)]


@pytest.mark.asyncio
async def test_archived_student_is_readable(db_session):
    w = await world(db_session)
    w["record"].status = "archived"
    await db_session.commit()
    async with client_for(w["master"].email) as c:
        assert (await c.get(journey_url(w["record"].id))).json()["student"]["status"] == "archived"
        assert (await c.get(timeline_url(w["record"].id))).status_code == 200
