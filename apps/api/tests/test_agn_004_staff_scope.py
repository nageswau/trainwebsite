"""AGN-004 G4 -- staff see only their assigned students on every existing agent path; Masters unchanged (spec §5.3; AC02, AC04, AC06)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentStudent, Country, OverseasApplication, StudentDocument, University
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


async def _university(db) -> University:
    country = Country(
        slug=f"a4-c-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[]
    )
    db.add(country)
    await db.flush()
    uni = University(
        country_id=country.id, slug=f"a4-u-{uuid.uuid4().hex[:8]}", name=f"A4 Uni {uuid.uuid4().hex[:6]}", city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[]
    )
    db.add(uni)
    await db.commit()
    return uni


async def _linked(db, *, master, member, name: str, university) -> dict:
    student = await mk_user(db, role="overseas_student", full_name=name)
    link = AgentStudent(agent_id=master.id, student_id=student.id, status="active", assigned_member_id=member.id if member else None)
    db.add(link)
    app = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=master.id, intake="Sep 2027", status="submitted")
    db.add(app)
    await db.flush()
    doc = StudentDocument(student_id=student.id, application_id=app.id, document_type="passport", file_url="local/a4.pdf")
    db.add(doc)
    await db.commit()
    return {"student": student, "link": link, "application": app, "document": doc}


@pytest_asyncio.fixture
async def agency(db_session):
    tag = uuid.uuid4().hex[:6]
    ctx = await mk_active_org(db_session, name="Scope Agency")
    uni = await _university(db_session)
    s1 = await mk_staff(db_session, ctx["org"], full_name="Staff One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="Staff Two")
    mine = await _linked(db_session, master=ctx["master"], member=s1["member"], name=f"Mine Student {tag}", university=uni)
    theirs = await _linked(db_session, master=ctx["master"], member=s2["member"], name=f"Theirs Student {tag}", university=uni)
    unassigned = await _linked(db_session, master=ctx["master"], member=None, name=f"Nobody Student {tag}", university=uni)
    return ctx | {"s1": s1, "s2": s2, "mine": mine, "theirs": theirs, "unassigned": unassigned, "uni": uni, "tag": tag}


LISTS = [
    ("/api/v1/workflows/overseas/agent/students", "student_id", "student"),
    ("/api/v1/workflows/overseas/applications", "id", "application"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), LISTS)
async def test_staff_lists_hold_only_their_assigned_students(agency, url, key, kind):
    async with client_for(agency["s1"]["user"].email) as c:
        ids = {str(r[key]) for r in (await c.get(url)).json()}
    assert str(agency["mine"][kind].id) in ids
    assert str(agency["theirs"][kind].id) not in ids and str(agency["unassigned"][kind].id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), LISTS)
async def test_master_lists_are_unchanged(agency, url, key, kind):
    async with client_for(agency["master"].email) as c:
        ids = {str(r[key]) for r in (await c.get(url)).json()}
    assert {str(agency[x][kind].id) for x in ("mine", "theirs", "unassigned")} <= ids


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "students", "applications", "documents", "reports"])
async def test_staff_portal_pages_never_mention_another_staff_members_student(agency, section):
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.get(f"/api/v1/portal/overseas/agent/{section}")
    assert response.status_code == 200
    for other in ("theirs", "unassigned"):
        assert agency[other]["student"].full_name not in response.text
        assert str(agency[other]["document"].id) not in response.text


@pytest.mark.asyncio
async def test_staff_dashboard_counts_only_their_students(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        stats = {s["label"]: s["value"] for s in (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()["metrics"]}
    assert stats["Students"] == 1 and stats["Applications"] == 1


@pytest.mark.asyncio
async def test_staff_cannot_reach_another_staff_members_application_or_document(agency):
    theirs = agency["theirs"]
    async with client_for(agency["s1"]["user"].email) as c:
        upload = await c.post(
            "/api/v1/workflows/overseas/documents",
            json={"student_id": str(theirs["student"].id), "application_id": str(theirs["application"].id), "document_type": "transcript", "file_url": "local/x.pdf"},
        )
        upload_no_app = await c.post("/api/v1/workflows/overseas/documents", json={"student_id": str(theirs["student"].id), "document_type": "transcript", "file_url": "local/x.pdf"})
        download = await c.get(f"/api/v1/workflows/overseas/documents/{theirs['document'].id}/download")
        create = await c.post("/api/v1/workflows/overseas/applications", json={"student_id": str(theirs["student"].id), "university_id": str(agency["uni"].id), "intake": "Jan 2028"})
    assert [upload.status_code, upload_no_app.status_code, download.status_code, create.status_code] == [403, 403, 403, 403]


@pytest.mark.asyncio
async def test_staff_lookups_are_narrowed(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        students = (await c.get("/api/v1/lookups/overseas-students")).json()["items"]
        apps = (await c.get("/api/v1/lookups/overseas-applications")).json()["items"]
    assert {i["id"] for i in students} == {str(agency["mine"]["student"].id)}
    assert {i["id"] for i in apps} == {str(agency["mine"]["application"].id)}


@pytest.mark.asyncio
async def test_link_search_still_finds_students_when_the_agency_has_a_student_with_no_login(db_session, agency):
    """`NOT IN (subquery)` matches nothing once the subquery holds a NULL student_id -- the exclusion must skip rows with no login."""
    from tests.agn004_helpers import mk_record

    await mk_record(db_session, agent=agency["master"], full_name="No Login Yet")
    target = await mk_user(db_session, role="overseas_student", full_name=f"Findable {agency['tag']}")
    async with client_for(agency["master"].email) as c:
        response = await c.get("/api/v1/lookups/overseas-students", params={"purpose": "link", "q": f"Findable {agency['tag']}"})
    assert response.status_code == 200
    assert str(target.id) in {i["id"] for i in response.json()["items"]}


@pytest.mark.asyncio
async def test_a_staff_link_is_assigned_to_them(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Linked By Staff")
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(student.id)})
    assert response.status_code == 201
    link = await db_session.scalar(select(AgentStudent).where(AgentStudent.student_id == student.id).execution_options(populate_existing=True))
    assert link.assigned_member_id == agency["s1"]["member"].id


@pytest.mark.asyncio
async def test_a_master_link_starts_unassigned(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Linked By Master")
    async with client_for(agency["master"].email) as c:
        assert (await c.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(student.id)})).status_code == 201
    link = await db_session.scalar(select(AgentStudent).where(AgentStudent.student_id == student.id).execution_options(populate_existing=True))
    assert link.assigned_member_id is None


@pytest.mark.asyncio
async def test_archived_link_leaves_the_roster_and_cannot_be_relinked(db_session, agency):
    link = await db_session.get(AgentStudent, agency["unassigned"]["link"].id, populate_existing=True)
    link.status = "archived"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        roster = {r["student_id"] for r in (await c.get("/api/v1/workflows/overseas/agent/students")).json()}
        relink = await c.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(agency["unassigned"]["student"].id)})
    assert str(agency["unassigned"]["student"].id) not in roster
    assert relink.status_code == 409 and relink.json()["detail"] == "This student is archived — unarchive them first"


@pytest.mark.asyncio
async def test_archived_link_keeps_its_applications_visible(db_session, agency):
    link = await db_session.get(AgentStudent, agency["unassigned"]["link"].id, populate_existing=True)
    link.status = "archived"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        apps = {r["id"] for r in (await c.get("/api/v1/workflows/overseas/applications")).json()}
        docs_page = (await c.get("/api/v1/portal/overseas/agent/documents")).text
        students_page = (await c.get("/api/v1/portal/overseas/agent/students")).text
    assert str(agency["unassigned"]["application"].id) in apps
    assert str(agency["unassigned"]["document"].id) in docs_page
    assert agency["unassigned"]["student"].full_name not in students_page
