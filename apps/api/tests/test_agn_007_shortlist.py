"""AGN-007 -- a student's university shortlist (spec §5.2, §5.4; AC01, AC02, AC03, AC07, AC08, AC11, Review Focus 1)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudent, AgentStudentShortlistEntry, AuditLog
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES, mk_catalogue, shortlist


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_active_org(db_session, name="List Agency")
    s1 = await mk_staff(db_session, ctx["org"], full_name="List Staff One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="List Staff Two")
    mine = await mk_record(db_session, agent=ctx["master"], full_name="Assigned To S1", assigned_member=s1["member"])
    theirs = await mk_record(db_session, agent=ctx["master"], full_name="Assigned To S2", assigned_member=s2["member"])
    cat = await mk_catalogue(db_session)
    async with client_for(ctx["master"].email) as m:
        agency_uni = (await m.post(UNIVERSITIES, json={"name": f"Agency U {uuid.uuid4().hex[:6]}", "country": "Malta", "entry_requirements": "Interview"})).json()["university"]
    return ctx | {"s1": s1, "s2": s2, "mine": mine, "theirs": theirs, "cat": cat, "agency_uni": agency_uni}


def _catalogue_body(w) -> dict:
    return {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["course"].id), "intake": "Sep 2027", "tuition_fee": "EUR 20,000", "entry_requirements": "IELTS 6.5"}


@pytest.mark.asyncio
async def test_catalogue_entry_saves(world):  # AGN-007-AC01
    async with client_for(world["s1"]["user"].email) as s:
        response = await s.post(shortlist(world["mine"].id), json=_catalogue_body(world))
        assert response.status_code == 201, response.text
        entry = response.json()["entry"]
        listed = (await s.get(shortlist(world["mine"].id))).json()
    assert entry["university"] == {"source": "catalogue", "id": str(world["cat"]["university"].id), "name": world["cat"]["university"].name, "slug": world["cat"]["university"].slug, "country": world["cat"]["country"].name}
    assert entry["course"] == {"id": str(world["cat"]["course"].id), "title": world["cat"]["course"].title}
    assert (entry["intake"], entry["tuition_fee"], entry["entry_requirements"]) == ("Sep 2027", "EUR 20,000", "IELTS 6.5")
    assert entry["created_by"] == "List Staff One"
    assert listed["total"] == 1 and listed["items"][0]["id"] == entry["id"]


@pytest.mark.asyncio
async def test_free_text_entry_saves(world):  # AGN-007-AC02
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json={"agent_university_id": world["agency_uni"]["id"], "course_title": "BA Typed", "intake": "Feb 2028"})
    assert response.status_code == 201, response.text
    entry = response.json()["entry"]
    assert entry["university"] == {"source": "agency", "id": world["agency_uni"]["id"], "name": world["agency_uni"]["name"], "slug": None, "country": "Malta"}
    assert entry["course"] == {"id": None, "title": "BA Typed"}


@pytest.mark.asyncio
async def test_catalogue_university_with_typed_course_saves(world):  # D4
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json={"university_id": str(world["cat"]["university"].id), "course_title": "Not in catalogue"})
    assert response.status_code == 201 and response.json()["entry"]["course"] == {"id": None, "title": "Not in catalogue"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("make_body", "detail"),
    [
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["other_course"].id)}, "Course does not belong to selected university"),
        (lambda w: {"agent_university_id": w["agency_uni"]["id"], "course_id": str(w["cat"]["course"].id)}, "Catalogue courses can only be chosen with a catalogue university"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "agent_university_id": w["agency_uni"]["id"]}, "Choose a catalogue university or one of your agency's universities"),
        (lambda w: {"intake": "Sep"}, "Choose a catalogue university or one of your agency's universities"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["course"].id), "course_title": "Both"}, "Choose a catalogue course or type a course, not both"),
        (lambda w: {"university_id": str(uuid.uuid4())}, "University not found"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(uuid.uuid4())}, "Course does not belong to selected university"),
    ],
)
async def test_invalid_entries_are_422_and_write_nothing(db_session, world, make_body, detail):  # AGN-007-AC03
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json=make_body(world))
    assert response.status_code == 422 and response.json()["detail"] == detail
    assert await db_session.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == world["mine"].id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(world["mine"].id))) == 0


@pytest.mark.asyncio
async def test_edit_and_remove_with_audit(db_session, world):  # AGN-007-AC07 (+ AC12 shape)
    async with client_for(world["s1"]["user"].email) as s:
        eid = (await s.post(shortlist(world["mine"].id), json=_catalogue_body(world))).json()["entry"]["id"]
        edited = await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "Jan 2028", "tuition_fee": None})
        assert edited.status_code == 200 and (edited.json()["entry"]["intake"], edited.json()["entry"]["tuition_fee"]) == ("Jan 2028", None)
        same = await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "Jan 2028"})
        assert same.status_code == 200
        assert (await s.delete(f"{shortlist(world['mine'].id)}/{eid}")).status_code == 204
        assert (await s.delete(f"{shortlist(world['mine'].id)}/{eid}")).status_code == 404
    rows = (await db_session.execute(select(AuditLog.action, AuditLog.metadata_json).where(AuditLog.entity_id == str(world["mine"].id)).order_by(AuditLog.created_at))).all()
    assert [a for a, _ in rows] == ["agent_student.shortlist_add", "agent_student.shortlist_update", "agent_student.shortlist_remove"]
    assert rows[0][1] == {"entry_id": eid, "university_source": "catalogue", "fields": ["course_id", "entry_requirements", "intake", "tuition_fee", "university_id"]}
    assert rows[1][1] == {"entry_id": eid, "fields": ["intake", "tuition_fee"]}
    assert rows[2][1] == {"entry_id": eid}


@pytest.mark.asyncio
async def test_patch_switching_university_with_a_stale_course_is_422(world):  # Review Focus 1
    async with client_for(world["master"].email) as m:
        eid = (await m.post(shortlist(world["mine"].id), json=_catalogue_body(world))).json()["entry"]["id"]
        url = f"{shortlist(world['mine'].id)}/{eid}"
        stale = await m.patch(url, json={"university_id": str(world["cat"]["other_university"].id)})
        assert stale.status_code == 422 and stale.json()["detail"] == "Course does not belong to selected university"
        to_agency = await m.patch(url, json={"university_id": None, "agent_university_id": world["agency_uni"]["id"], "course_id": None, "course_title": "Typed"})
        assert to_agency.status_code == 200 and to_agency.json()["entry"]["university"]["source"] == "agency"


@pytest.mark.asyncio
async def test_staff_scope_is_404_before_any_role_check(world):  # AGN-007-AC07
    async with client_for(world["master"].email) as m:
        eid = (await m.post(shortlist(world["theirs"].id), json={"agent_university_id": world["agency_uni"]["id"]})).json()["entry"]["id"]
    async with client_for(world["s1"]["user"].email) as s:
        for response in (
            await s.get(shortlist(world["theirs"].id)),
            await s.post(shortlist(world["theirs"].id), json={"agent_university_id": world["agency_uni"]["id"]}),
            await s.patch(f"{shortlist(world['theirs'].id)}/{eid}", json={"intake": "X"}),
            await s.delete(f"{shortlist(world['theirs'].id)}/{eid}"),
        ):
            assert response.status_code == 404 and response.json()["detail"] == "Student not found"
        # an entry id of another student, under my own student, is not found
        assert (await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_archived_is_read_only_and_linked_is_writable(db_session, world):  # AGN-007-AC08
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived One", status="archived")
    student_user = await mk_user(db_session, role="overseas_student")
    linked = AgentStudent(agent_id=world["master"].id, student_id=student_user.id, status="active")
    db_session.add(linked)
    await db_session.commit()
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        assert (await m.get(shortlist(archived.id))).status_code == 200
        refused = await m.post(shortlist(archived.id), json=body)
        assert refused.status_code == 409 and refused.json()["detail"] == "Unarchive this student first"
        assert (await m.post(shortlist(linked.id), json=body)).status_code == 201


@pytest.mark.asyncio
async def test_entry_cap_is_422(world, monkeypatch):  # AGN-007-AC10
    monkeypatch.setattr(service, "MAX_ENTRIES_PER_STUDENT", 2)
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        assert [(await m.post(shortlist(world["mine"].id), json=body)).status_code for _ in range(2)] == [201, 201]
        third = await m.post(shortlist(world["mine"].id), json=body)
    assert third.status_code == 422 and third.json()["detail"] == "This student's shortlist is full (2 entries)"


@pytest.mark.asyncio
async def test_paging_is_stable_and_bounded(world):  # AGN-007-AC11
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        ids = [(await m.post(shortlist(world["mine"].id), json=body | {"intake": str(i)})).json()["entry"]["id"] for i in range(3)]
        first = (await m.get(shortlist(world["mine"].id), params={"limit": 2})).json()
        second = (await m.get(shortlist(world["mine"].id), params={"limit": 2, "offset": 2})).json()
        assert [e["id"] for e in first["items"] + second["items"]] == ids and first["total"] == 3
        assert (await m.get(shortlist(world["mine"].id), params={"offset": 10})).json() == {"items": [], "total": 3, "limit": 20, "offset": 10}
        for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            assert (await m.get(shortlist(world["mine"].id), params=bad)).status_code == 422
