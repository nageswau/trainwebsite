"""AGN-007 -- invisible to other agencies and to /public; races; staff activity (AC04, AC05, AC10 race, AC12; Review Focus 2, 3)."""

import asyncio
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AgentStudentShortlistEntry, AgentUniversity
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES, mk_catalogue, shortlist

ACTIVITY = "/api/v1/workflows/overseas/agent/team/staff/{member}/activity"  # AGN-021 (api/agent_team.py; items carry "action")


@pytest_asyncio.fixture
async def two(db_session):
    a = await mk_active_org(db_session, name="Iso A")
    b = await mk_active_org(db_session, name="Iso B")
    tag = uuid.uuid4().hex[:8]
    async with client_for(a["master"].email) as m:
        uni = (await m.post(UNIVERSITIES, json={"name": f"Secret Uni {tag}", "country": "Atlantis"})).json()["university"]
    student_a = await mk_record(db_session, agent=a["master"], full_name="Iso Student A")
    student_b = await mk_record(db_session, agent=b["master"], full_name="Iso Student B")
    async with client_for(a["master"].email) as m:
        entry = (await m.post(shortlist(student_a.id), json={"agent_university_id": uni["id"], "course_title": f"Secret Course {tag}"})).json()["entry"]
    return {"a": a, "b": b, "tag": tag, "uni": uni, "student_a": student_a, "student_b": student_b, "entry": entry}


@pytest.mark.asyncio
async def test_other_agencys_university_id_reads_as_not_found(two):  # AGN-007-AC04, Review Focus 2
    async with client_for(two["b"]["master"].email) as o:
        used = await o.post(shortlist(two["student_b"].id), json={"agent_university_id": two["uni"]["id"]})
        unknown = await o.post(shortlist(two["student_b"].id), json={"agent_university_id": str(uuid.uuid4())})
        assert (used.status_code, used.json()) == (unknown.status_code, unknown.json()) == (422, {"detail": "University not found"})
        assert (await o.get(shortlist(two["student_a"].id))).status_code == 404
        assert (await o.delete(f"{shortlist(two['student_a'].id)}/{two['entry']['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_public_never_shows_agency_universities_or_entries(db_session, two):  # AGN-007-AC05
    cat = await mk_catalogue(db_session)
    secret = two["tag"]
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:  # no login: the public site
        bodies = [
            (await anon.get("/api/v1/public/universities")).text,
            (await anon.get("/api/v1/public/universities", params={"q": "Secret"})).text,
            (await anon.get(f"/api/v1/public/universities/{cat['university'].slug}")).text,
            (await anon.get(f"/api/v1/public/countries/{cat['country'].slug}")).text,
            (await anon.get("/api/v1/public/overseas-courses")).text,
            (await anon.get("/api/v1/public/countries")).text,
        ]
        by_id = await anon.get(f"/api/v1/public/universities/{two['uni']['id']}")  # an agency id is not a catalogue slug
    for body in bodies:
        assert secret not in body and "Atlantis" not in body
    assert by_id.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_adds_never_pass_the_cap(db_session, two, monkeypatch):  # AGN-007-AC10 (race)
    monkeypatch.setattr(service, "MAX_ENTRIES_PER_STUDENT", 2)  # one entry exists from the fixture
    body = {"agent_university_id": two["uni"]["id"]}
    async with client_for(two["a"]["master"].email) as c1, client_for(two["a"]["master"].email) as c2:
        results = await asyncio.gather(c1.post(shortlist(two["student_a"].id), json=body), c2.post(shortlist(two["student_a"].id), json=body))
    assert sorted(r.status_code for r in results) == [201, 422]
    assert await db_session.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == two["student_a"].id)) == 2


@pytest.mark.asyncio
async def test_delete_university_racing_an_add_never_orphans(db_session, two):  # Review Focus 3
    async with client_for(two["a"]["master"].email) as m:
        fresh = (await m.post(UNIVERSITIES, json={"name": f"Racy {two['tag']}", "country": "Nowhere"})).json()["university"]
    async with client_for(two["a"]["master"].email) as c1, client_for(two["a"]["master"].email) as c2:
        add, delete = await asyncio.gather(
            c1.post(shortlist(two["student_a"].id), json={"agent_university_id": fresh["id"]}),
            c2.delete(f"{UNIVERSITIES}/{fresh['id']}"),
        )
    still_there = await db_session.get(AgentUniversity, uuid.UUID(fresh["id"]), populate_existing=True)
    if add.status_code == 201:
        assert delete.status_code == 409 and still_there is not None
    else:
        assert (add.status_code, delete.status_code) == (422, 204) and still_there is None


@pytest.mark.asyncio
async def test_shortlist_work_shows_in_staff_activity(db_session):  # AGN-007-AC12
    ctx = await mk_active_org(db_session, name="Activity Agency")
    staff = await mk_staff(db_session, ctx["org"], full_name="Activity Staff")
    student = await mk_record(db_session, agent=ctx["master"], full_name="Activity Student", assigned_member=staff["member"])
    async with client_for(ctx["master"].email) as m:
        uni = (await m.post(UNIVERSITIES, json={"name": f"Act {uuid.uuid4().hex[:6]}", "country": "Peru"})).json()["university"]
    async with client_for(staff["user"].email) as s:
        eid = (await s.post(shortlist(student.id), json={"agent_university_id": uni["id"]})).json()["entry"]["id"]
        await s.patch(f"{shortlist(student.id)}/{eid}", json={"intake": "Sep"})
        await s.delete(f"{shortlist(student.id)}/{eid}")
    async with client_for(ctx["master"].email) as m:
        items = (await m.get(ACTIVITY.format(member=staff["member"].id))).json()["items"]
    actions = [i["action"] for i in items]
    assert {"agent_student.shortlist_add", "agent_student.shortlist_update", "agent_student.shortlist_remove"} <= set(actions)
    assert not any(a.startswith("agent_university.") for a in actions)
