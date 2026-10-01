"""AGN-004 -- edit, archive, unarchive, assign (spec §5.4; AC03, AC04, AC09, AC11)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentOrgMember, AgentStudent, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import RECORDS, mk_record, mk_staff


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Actions Agency")
    other = await mk_active_org(db_session, name="Actions Other")
    s1 = await mk_staff(db_session, ctx["org"], full_name="Act One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="Act Two")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Edit Me", email=f"edit-{uuid.uuid4().hex[:8]}@example.local", assigned_member=s1["member"])
    return ctx | {"other": other, "s1": s1, "s2": s2, "row": row}


async def _audits(db, action: str, sid) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(sid)))).all())


@pytest.mark.asyncio
async def test_assigned_staff_edit_changed_fields_only(db_session, agency):
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"preferred_country": "Ireland", "phone": None, "full_name": "Edit Me"})
    assert response.status_code == 200 and response.json()["student"]["preferred_country"] == "Ireland"
    [audit] = await _audits(db_session, "agent_student.update", agency["row"].id)
    assert audit.metadata_json == {"fields": ["preferred_country"]}  # phone was already empty and the name unchanged


@pytest.mark.asyncio
async def test_no_op_patch_writes_no_audit_row(db_session, agency):
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"full_name": "Edit Me"})
    assert response.status_code == 200
    assert await _audits(db_session, "agent_student.update", agency["row"].id) == []


@pytest.mark.asyncio
async def test_invalid_edit_writes_nothing(db_session, agency):
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"preferred_country": "Chile", "graduation_year": 1800})
    assert response.status_code == 422
    row = await db_session.get(AgentStudent, agency["row"].id, populate_existing=True)
    assert row.preferred_country is None


@pytest.mark.asyncio
async def test_other_staff_get_404_on_every_action(agency):
    sid = agency["row"].id
    async with client_for(agency["s2"]["user"].email) as c:
        codes = [
            (await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})).status_code,
            (await c.post(f"{RECORDS}/{sid}/archive")).status_code,
            (await c.post(f"{RECORDS}/{sid}/unarchive")).status_code,
            (await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})).status_code,
        ]
    assert codes == [404, 404, 404, 404]


@pytest.mark.asyncio
async def test_other_agency_master_gets_404_on_every_action(agency):
    sid = agency["row"].id
    async with client_for(agency["other"]["master"].email) as c:
        codes = [
            (await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})).status_code,
            (await c.post(f"{RECORDS}/{sid}/archive")).status_code,
            (await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})).status_code,
        ]
    assert codes == [404, 404, 404]


@pytest.mark.asyncio
async def test_assigned_staff_cannot_archive_or_assign(agency):
    sid = agency["row"].id
    async with client_for(agency["s1"]["user"].email) as c:
        archive = await c.post(f"{RECORDS}/{sid}/archive")
        assign = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})
    assert archive.status_code == 403 and archive.json()["detail"] == "Only an agency Master can archive students"
    assert assign.status_code == 403 and assign.json()["detail"] == "Only an agency Master can assign students"


@pytest.mark.asyncio
async def test_master_archives_and_unarchives(db_session, agency):
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        archived = await c.post(f"{RECORDS}/{sid}/archive")
        again = await c.post(f"{RECORDS}/{sid}/archive")
        edit = await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})
        listed = {i["id"] for i in (await c.get(RECORDS, params={"q": "Edit Me"})).json()["items"]}
        detail = await c.get(f"{RECORDS}/{sid}")
        restored = await c.post(f"{RECORDS}/{sid}/unarchive")
        restored_again = await c.post(f"{RECORDS}/{sid}/unarchive")
    body = archived.json()["student"]
    assert archived.status_code == 200 and body["status"] == "archived" and body["archived_by"] and body["archived_at"]
    assert again.status_code == 409 and edit.status_code == 409 and edit.json()["detail"] == "Unarchive this student first"
    assert str(sid) not in listed and detail.status_code == 200
    assert restored.status_code == 200 and restored.json()["student"]["status"] == "active" and restored.json()["student"]["archived_by"] is None
    assert restored_again.status_code == 409
    assert len(await _audits(db_session, "agent_student.archive", sid)) == 1 and len(await _audits(db_session, "agent_student.unarchive", sid)) == 1


@pytest.mark.asyncio
async def test_assigned_staff_still_see_an_archived_student_by_id_but_not_in_their_list(agency):
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        await c.post(f"{RECORDS}/{sid}/archive")
    async with client_for(agency["s1"]["user"].email) as c:
        assert str(sid) not in {i["id"] for i in (await c.get(RECORDS)).json()["items"]}
        assert (await c.get(f"{RECORDS}/{sid}")).status_code == 200


@pytest.mark.asyncio
async def test_linked_students_cannot_be_edited_here_but_can_be_archived(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Has Account")
    link = AgentStudent(agent_id=agency["master"].id, student_id=student.id, status="active")
    db_session.add(link)
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{link.id}", json={"notes": "x"})
        archive = await c.post(f"{RECORDS}/{link.id}/archive")
    assert response.status_code == 409 and response.json()["detail"] == "Linked students are edited in their own account"
    assert archive.status_code == 200 and archive.json()["student"]["has_login"] is True


@pytest.mark.asyncio
async def test_assign_targets_only_active_staff_of_the_same_agency(db_session, agency):
    sid = agency["row"].id
    foreign = await mk_staff(db_session, agency["other"]["org"], full_name="Foreign Staff")
    gone = await mk_staff(db_session, agency["org"], full_name="Gone Staff", active=False)
    async with client_for(agency["master"].email) as c:
        codes = [(await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(m)})).status_code for m in (foreign["member"].id, gone["member"].id, agency["member"].id, uuid.uuid4())]
        moved = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(agency["s2"]["member"].id)})
        same = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(agency["s2"]["member"].id)})
        cleared = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})
    assert codes == [422, 422, 422, 422]
    assert moved.json()["student"]["assigned_to"]["code"] == agency["s2"]["member"].code
    assert same.status_code == 200 and cleared.json()["student"]["assigned_to"] is None
    assert len(await _audits(db_session, "agent_student.assign", sid)) == 2  # the repeat assignment wrote nothing


@pytest.mark.asyncio
async def test_assigning_an_archived_student_is_refused(agency):
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        await c.post(f"{RECORDS}/{sid}/archive")
        response = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_deactivated_staff_keep_their_students(db_session, agency):
    member = await db_session.get(AgentOrgMember, agency["s1"]["member"].id, populate_existing=True)
    member.status = "deactivated"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        item = next(i for i in (await c.get(RECORDS, params={"q": "Edit Me"})).json()["items"] if i["id"] == str(agency["row"].id))
    assert item["assigned_to"]["id"] == str(member.id) and item["assigned_to"]["status"] == "deactivated"


@pytest.mark.asyncio
async def test_edit_reruns_the_duplicate_check(db_session, agency):
    taken = f"taken-{uuid.uuid4().hex[:8]}@example.local"
    await mk_record(db_session, agent=agency["master"], full_name="Owner Of Email", email=taken)
    async with client_for(agency["master"].email) as c:
        warned = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"email": taken})
        forced = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"email": taken, "confirm_duplicate": True})
    assert warned.status_code == 409 and warned.json()["detail"]["code"] == "possible_duplicate"
    assert forced.status_code == 200 and forced.json()["student"]["email"] == taken
    assert len(await _audits(db_session, "agent_student.duplicate_override", agency["row"].id)) == 1
