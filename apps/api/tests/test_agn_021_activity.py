"""AGN-021 -- a Master views one staff member's student-journey activity (spec §4-§5, §7; DEC-SCOPE-046 A1-A5)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import AgentOrg, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import DOC_VERIFY, agency_document, mk_university
from tests.agn004_helpers import RECORDS

MASTER_ONLY = "Only an agency Master can manage the team"
NOT_FOUND = "Staff member not found"


def activity(member_id) -> str:
    return f"{STAFF}/{member_id}/activity"


async def _agency(db, name: str) -> dict:
    ctx = await mk_active_org(db, name=f"{name} {uniq()}")
    staff = await mk_staff(db, ctx["org"], full_name=f"{name} Staff", can_verify_documents=True)
    return ctx | {"staff": staff}


async def _row(db, user_id, action: str, *, entity_type: str = "agent_student", entity_id=None, metadata=None, at=None) -> AuditLog:
    row = AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=str(entity_id or uuid.uuid4()), metadata_json=metadata or {})
    if at is not None:
        row.created_at = at
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_staff_work_appears_on_the_next_request(db_session):  # AC01, AC04; Review Focus 5
    a = await _agency(db_session, "Activity Work")
    world = await agency_document(db_session, a, assigned_to=a["staff"]["member"])
    uni2 = await mk_university(db_session)  # a second university: the world's application already exists for the first
    linkable = await mk_user(db_session, role="overseas_student", full_name="Linkable Student")
    email = f"asha-{uniq()}@example.local"
    async with client_for(a["master"].email) as m, client_for(a["staff"]["user"].email) as s:
        url = activity(a["staff"]["member"].id)
        assert (await m.get(url)).json()["total"] == 0
        created = await s.post(RECORDS, json={"full_name": "Asha Rao", "email": email})
        assert created.status_code == 201, created.text
        record_id = created.json()["student"]["id"]
        first = (await m.get(url)).json()  # the next request already shows it
        assert [(i["action"], i["subject"]) for i in first["items"]] == [("agent_student.create", "Asha Rao")]
        assert (await s.patch(f"{RECORDS}/{record_id}", json={"phone": "+91 98765 43210"})).status_code == 200
        assert (await s.post(RECORDS, json={"full_name": "Asha Again", "email": email, "confirm_duplicate": True})).status_code == 201
        assert (await s.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(linkable.id)})).status_code == 201
        app = await s.post("/api/v1/workflows/overseas/applications", json={"student_id": str(world["student"].id), "university_id": str(uni2.id), "intake": "Jan 2028"})
        assert app.status_code == 201, app.text
        upload = await s.post("/api/v1/workflows/overseas/documents", json={"student_id": str(world["student"].id), "application_id": str(world["application"].id), "document_type": "Transcript", "file_url": "uploads/agn021.pdf"})
        assert upload.status_code == 201, upload.text
        verify = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified", "notes": "Secret reviewer note"})
        assert verify.status_code == 200, verify.text
        page = await m.get(url)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 8 and body["limit"] == 25 and body["offset"] == 0
    got = {(i["action"], i["subject"], tuple(i["fields"] or ())) for i in body["items"]}
    assert got == {
        ("agent_student.create", "Asha Rao", ()),
        ("agent_student.update", "Asha Rao", ("phone",)),
        ("agent_student.create", "Asha Again", ()),
        ("agent_student.duplicate_override", "Asha Again", ()),
        ("agent.student_link", "Linkable Student", ()),
        ("overseas.application.create", "Agency Student — AGN003 University", ()),
        ("document.upload", "Transcript — Agency Student", ()),
        ("document.verify", "Passport — Agency Student", ()),
    }
    ats = [i["at"] for i in body["items"]]
    assert ats == sorted(ats, reverse=True)
    assert set(body["items"][0]) == {"id", "at", "action", "subject", "fields"}
    for secret in ("Secret reviewer note", email, "98765", "43210"):
        assert secret not in page.text


@pytest.mark.asyncio
async def test_other_agency_master_and_unknown_ids_are_404(db_session):  # AC02; Review Focus 4
    a = await _agency(db_session, "Activity Owner")
    b = await _agency(db_session, "Activity Other")
    async with client_for(b["master"].email) as other, client_for(a["master"].email) as m:
        cross = await other.get(activity(a["staff"]["member"].id))
        own_master = await m.get(activity(a["member"].id))
        unknown = await m.get(activity(uuid.uuid4()))
    for response in (cross, own_master, unknown):
        assert response.status_code == 404 and response.json()["detail"] == NOT_FOUND


@pytest.mark.asyncio
async def test_staff_and_inactive_agencies_are_refused(db_session):  # AC02
    a = await _agency(db_session, "Activity Refused")
    async with client_for(a["staff"]["user"].email) as s:
        own = await s.get(activity(a["staff"]["member"].id))
    assert own.status_code == 403 and own.json()["detail"] == MASTER_ONLY
    org = await db_session.get(AgentOrg, a["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(a["master"].email) as m:
        assert (await m.get(activity(a["staff"]["member"].id))).status_code == 403


@pytest.mark.asyncio
async def test_only_allow_listed_rows_of_this_staff_member_appear(db_session):  # AC03
    a = await _agency(db_session, "Activity Filter")
    other_staff = await mk_staff(db_session, a["org"], full_name="Other Staff")
    staff_id = a["staff"]["user"].id
    for action in ("auth.login", "auth.change_password", "profile.update", "message.send", "lookup.agent_link_search", "support.create", "agent_student.archive"):
        await _row(db_session, staff_id, action)
    await _row(db_session, other_staff["user"].id, "agent_student.create")
    async with client_for(a["master"].email) as m:
        body = (await m.get(activity(a["staff"]["member"].id))).json()
    assert body["total"] == 0 and body["items"] == []


@pytest.mark.asyncio
async def test_unresolvable_subjects_read_no_longer_available(db_session):  # AC04; Review Focus 2
    a = await _agency(db_session, "Activity Gone")
    staff_id = a["staff"]["user"].id
    await _row(db_session, staff_id, "agent_student.create")  # entity deleted / never existed
    await _row(db_session, staff_id, "overseas.application.create", entity_type="overseas_application")
    await _row(db_session, staff_id, "document.upload", entity_type="student_document")
    bad = AuditLog(user_id=staff_id, action="agent_student.update", entity_type="agent_student", entity_id="not-a-uuid", metadata_json={"fields": "phone"})
    db_session.add(bad)
    await db_session.commit()
    async with client_for(a["master"].email) as m:
        response = await m.get(activity(a["staff"]["member"].id))
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 4
    assert {i["subject"] for i in items} == {"No longer available"}
    assert next(i for i in items if i["action"] == "agent_student.update")["fields"] is None  # not a list -> None


@pytest.mark.asyncio
async def test_paging_is_stable_on_equal_timestamps(db_session):  # AC05; Review Focus 1
    a = await _agency(db_session, "Activity Paging")
    same = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    rows = [await _row(db_session, a["staff"]["user"].id, "document.upload", entity_type="student_document", at=same) for _ in range(3)]
    async with client_for(a["master"].email) as m:
        one = (await m.get(activity(a["staff"]["member"].id), params={"limit": 2, "offset": 0})).json()
        two = (await m.get(activity(a["staff"]["member"].id), params={"limit": 2, "offset": 2})).json()
    ids = [i["id"] for i in one["items"]] + [i["id"] for i in two["items"]]
    assert sorted(ids) == sorted(str(r.id) for r in rows) and len(set(ids)) == 3
    assert ids == sorted(ids, reverse=True)  # id DESC tiebreak
    assert (one["total"], one["limit"], two["offset"]) == (3, 2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}])
async def test_paging_bounds_are_422(db_session, params):  # AC05
    a = await _agency(db_session, "Activity Bounds")
    async with client_for(a["master"].email) as m:
        assert (await m.get(activity(a["staff"]["member"].id), params=params)).status_code == 422
        assert (await m.get(f"{STAFF}/not-a-uuid/activity")).status_code == 422


@pytest.mark.asyncio
async def test_deactivated_staff_stay_viewable(db_session):  # AC06
    a = await _agency(db_session, "Activity Deactivated")
    gone = await mk_staff(db_session, a["org"], full_name="Gone Staff", active=False)
    await _row(db_session, gone["user"].id, "agent_student.create")
    async with client_for(a["master"].email) as m:
        response = await m.get(activity(gone["member"].id))
    assert response.status_code == 200 and response.json()["total"] == 1


@pytest.mark.asyncio
async def test_agent_application_actions_appear_with_the_no_login_student(db_session):
    from tests.agn008_helpers import APPS, agency_world, mk_application  # noqa: PLC0415

    w = await agency_world(db_session)
    app = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    async with client_for(w["staff"]["user"].email) as s:
        await s.patch(f"{APPS}/{app.id}", json={"intake": "Spring 2028"})
        await s.post(f"{APPS}/{app.id}/status", json={"to_status": "offer"})
        await s.post(f"{APPS}/{app.id}/status", json={"to_status": "withdrawn"})
    async with client_for(w["master"].email) as m:
        items = (await m.get(f"/api/v1/workflows/overseas/agent/team/staff/{w['staff']['member'].id}/activity")).json()["items"]
    got = [(i["action"], i["subject"]) for i in items[:3]]
    subject = f"{w['record'].full_name} — {w['university'].name}"
    assert got == [("overseas.application.withdraw", subject), ("overseas.application.advance", subject), ("overseas.application.update", subject)]
