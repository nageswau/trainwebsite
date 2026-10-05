"""AGN-009 -- the existing document routes with an agency-only document (`student_id` NULL) and their additive history rows
(spec §4.3). Response shapes and status codes of these routes are unchanged (AC7)."""

import pytest
import pytest_asyncio

from app.models import OverseasApplication, StudentDocument
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn009_helpers import DOWNLOAD, OLD_UPLOAD, VERIFY, audit_actions, events_of, mk_doc, world


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "code"), [("master", 200), ("staff", 200), ("plain", 403), ("other", 403)])
async def test_agency_only_document_download_is_scoped(db_session, w, who, code):
    doc = await mk_doc(db_session, record=w["record"])
    email = {"master": w["master"].email, "staff": w["staff"]["user"].email, "plain": w["plain"]["user"].email, "other": w["other"]["master"].email}[who]
    async with client_for(email) as c:
        response = await c.get(DOWNLOAD.format(doc.id))
    assert response.status_code == code, response.text
    if code == 200:
        assert set(response.json()) == {"url", "expires_in"}
        assert [e.event for e in await events_of(db_session, doc.id)] == ["downloaded"]
        assert "document.download" in await audit_actions(db_session, doc.id)
    else:
        assert await events_of(db_session, doc.id) == []


@pytest.mark.asyncio
async def test_another_no_login_student_does_not_open_the_document(db_session, w):
    """`AgentStudent.student_id == None` compiles to IS NULL: a staff member assigned *any* no-login student must not reach another
    no-login student's document through it."""
    await mk_record(db_session, agent=w["master"], full_name="Plain's own", assigned_member=w["plain"]["member"])
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["plain"]["user"].email) as c:
        assert (await c.get(DOWNLOAD.format(doc.id))).status_code == 403
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "verified"})).status_code == 403
    assert (await db_session.get(StudentDocument, doc.id, populate_existing=True)).verification_status == "pending"


@pytest.mark.asyncio
async def test_student_download_keeps_its_shape_and_is_recorded(db_session, w):
    doc = await mk_doc(db_session, student=w["linked_user"], key="uploads/own.pdf")
    async with client_for(w["linked_user"].email) as c:
        response = await c.get(DOWNLOAD.format(doc.id))
    assert response.status_code == 200
    assert response.json() == {"url": "/local-files/uploads/own.pdf", "expires_in": None}
    events = await events_of(db_session, doc.id)
    assert [(e.event, e.actor_user_id) for e in events] == [("downloaded", w["linked_user"].id)]


@pytest.mark.asyncio
async def test_old_upload_route_records_the_uploader_and_an_event(db_session, w):
    async with client_for(w["master"].email) as c:
        response = await c.post(OLD_UPLOAD, json={"student_id": str(w["linked_user"].id), "document_type": "Passport", "file_url": "uploads/x.pdf"})
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "verification_status"}
    doc = await db_session.get(StudentDocument, response.json()["id"])
    assert doc.uploaded_by_user_id == w["master"].id
    assert [(e.event, e.to_status) for e in await events_of(db_session, doc.id)] == [("uploaded", "pending")]


@pytest.mark.asyncio
async def test_counselor_review_unchanged_but_recorded(db_session, w):
    counselor = await mk_user(db_session, role="counselor", full_name="Docs Counselor")
    app = OverseasApplication(student_id=w["linked_user"].id, university_id=w["university"].id, counselor_id=counselor.id, intake="Fall 2027", status="enquiry")
    db_session.add(app)
    await db_session.commit()
    doc = await mk_doc(db_session, student=w["linked_user"], application=app)
    async with client_for(counselor.email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected"})  # a reason stays optional (G1)
    assert response.status_code == 200
    assert response.json() == {"id": str(doc.id), "verification_status": "rejected"}
    assert [(e.event, e.from_status, e.to_status, e.actor_user_id) for e in await events_of(db_session, doc.id)] == [("rejected", "pending", "rejected", counselor.id)]


@pytest.mark.asyncio
async def test_master_reviews_an_agency_only_document(db_session, w):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["master"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": "verified"})
    assert response.status_code == 200, response.text
    assert [(e.event, e.to_status) for e in await events_of(db_session, doc.id)] == [("verified", "verified")]


@pytest.mark.asyncio
async def test_existing_readers_survive_an_agency_only_document(db_session, w):
    counselor = await mk_user(db_session, role="counselor", full_name="Docs Counselor")
    app = OverseasApplication(agent_id=w["master"].id, agent_student_id=w["record"].id, university_id=w["university"].id, counselor_id=counselor.id, intake="Fall 2027", status="enquiry")
    db_session.add(app)
    await db_session.commit()
    await mk_doc(db_session, record=w["record"], application=app)
    async with client_for(counselor.email) as c:
        assert (await c.get("/api/v1/portal/overseas/counselor/documents")).status_code == 200
        assert (await c.get(f"/api/v1/workflows/overseas/applications/{app.id}/visa-checklist")).status_code in {200, 404}
    async with client_for(w["master"].email) as c:
        assert (await c.get("/api/v1/portal/overseas/agent/documents")).status_code == 200
        assert (await c.get("/api/v1/portal/overseas/agent/dashboard")).status_code == 200
    admin = await mk_user(db_session, role="overseas_admin", full_name="Docs Admin")
    async with client_for(admin.email) as c:
        assert (await c.get("/api/v1/portal/overseas/admin/dashboard")).status_code == 200
